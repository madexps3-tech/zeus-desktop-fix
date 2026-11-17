"""Send a ready Zeus trade to Telegram, and place it only after CONFIRM.

The bot token stays in telegram.txt next to this install. A coming-into line is not a message.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from pathlib import Path
from secrets import token_hex
from time import monotonic, time
from typing import Any

_LOCK = threading.Lock()
_STARTED = False
_HOST: Any = None
_OFFSET = 0
_SENT: dict[str, float] = {}
_OFFERS: dict[str, dict[str, Any]] = {}
_FOCUS = ""
_LABELS = {
    "XAUUSD": "GOLD",
    "XAGUSD": "SILVER",
    "NAS100": "NASDAQ",
    "BTCUSD": "BITCOIN",
    "EURUSD": "EURO",
    "USDJPY": "USDJPY",
    "WTI": "OIL",
}


def _file() -> Path:
    return Path.cwd() / "telegram.txt"


def _read() -> tuple[str, str, float, bool]:
    path = _file()
    if not path.is_file():
        return "", "", 2.0, False
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    token = lines[0] if lines else ""
    chat = lines[1] if len(lines) > 1 else ""
    risk = 2.0
    if len(lines) > 2:
        try:
            risk = float(lines[2])
        except ValueError:
            risk = 2.0
    if not 0 < risk <= 100:
        risk = 2.0
    auto = len(lines) > 3 and lines[3].lower() == "on"
    return token, chat, risk, auto


def _write(token: str, chat: str, risk: float, auto: bool) -> None:
    _file().write_text(f"{token}\n{chat}\n{risk}\n{'on' if auto else 'off'}\n", encoding="utf-8")


def _api(token: str, method: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/{method}",
        data=body,
        headers={"content-type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))
    return data if isinstance(data, dict) else {}


def _send(token: str, chat: str, text: str, buttons: list[tuple[str, str]] | None = None) -> None:
    payload: dict[str, Any] = {"chat_id": chat, "text": text[:4000]}
    if buttons:
        payload["reply_markup"] = {
            "inline_keyboard": [[{"text": label, "callback_data": data}] for label, data in buttons]
        }
    _api(token, "sendMessage", payload)


def start(host: Any) -> None:
    global _STARTED, _HOST
    _HOST = host
    token, _, _, _ = _read()
    if not token or _STARTED:
        return
    _STARTED = True
    threading.Thread(target=_poll, name="zeus-telegram", daemon=True).start()


def announce(payload: dict[str, Any]) -> None:
    """A tradeable row gets one message with TRADE. A scalp with auto on is sent without the tap."""
    global _FOCUS
    token, chat, risk, auto = _read()
    if not token or not chat or not payload.get("ok"):
        return
    symbol = str(payload.get("symbol") or "")
    _FOCUS = symbol
    label = _LABELS.get(symbol, payload.get("label") or symbol)
    for row in payload.get("rows") or []:
        if not isinstance(row, dict) or not row.get("side") or row.get("entry") is None or row.get("stop") is None:
            continue
        chart = str(row.get("chart") or "")
        if chart not in {"INTRADAY", "INTERDAY", "SCALP", "SWING"}:
            continue
        target = row.get("target")
        targets = row.get("targets") if isinstance(row.get("targets"), list) else []
        if target is None and targets:
            target = targets[0]
        if target is None:
            continue
        guide = str(row.get("guide") or "").strip()
        key = f"T|{symbol}|{chart}|{row.get('side')}|{row.get('entry')}|{row.get('stop')}|{target}"
        if row.get("tradeable") and _fresh(key):
            offer = token_hex(4)
            with _LOCK:
                _OFFERS[offer] = {
                    "symbol": symbol,
                    "chart": chart,
                    "side": str(row.get("side")),
                    "stop": float(row["stop"]),
                    "target": float(target),
                    "reason": str(row.get("reason") or ""),
                    "risk": risk,
                    "at": time(),
                }
            text = (
                f"{label} {chart} {row.get('side')}\n"
                f"Entry {row.get('entry')}\n"
                f"Stop {row.get('stop')}\n"
                f"Next {target}\n"
                f"Risk {risk:g}%"
            )
            if guide:
                text += f"\n{guide}"
                _mark(f"G|{symbol}|{chart}|{row.get('side')}|{guide}")
            if chart == "SCALP" and auto:
                with _LOCK:
                    row_offer = _OFFERS.pop(offer)
                _submit(token, chat, row_offer, "Scalp auto. ")
                continue
            try:
                _send(token, chat, text, [("TRADE", f"t{offer}")])
            except Exception:
                with _LOCK:
                    _OFFERS.pop(offer, None)
                _SENT.pop(key, None)
        if guide and _fresh(f"G|{symbol}|{chart}|{row.get('side')}|{guide}"):
            text = f"{label} {chart} {row.get('side')}\n{guide}"
            buttons = _manage_buttons(symbol, str(row.get("side") or ""))
            if buttons:
                text += "\nBE moves the stop to the entry. 50% banks half. Or send /sl, /tp, or /r."
            try:
                _send(token, chat, text, buttons or None)
            except Exception:
                _SENT.pop(f"G|{symbol}|{chart}|{row.get('side')}|{guide}", None)


def _mark(key: str) -> None:
    with _LOCK:
        _SENT[key] = monotonic()


def _fresh(key: str) -> bool:
    now = monotonic()
    with _LOCK:
        if now - _SENT.get(key, 0.0) < 6 * 3600:
            return False
        _SENT[key] = now
        if len(_SENT) > 400:
            oldest = sorted(_SENT, key=_SENT.get)[:100]
            for item in oldest:
                _SENT.pop(item, None)
    return True


def _poll() -> None:
    global _OFFSET
    while True:
        token, chat, risk, auto = _read()
        if not token:
            return
        try:
            data = _api(token, "getUpdates", {"timeout": 25, "offset": _OFFSET, "allowed_updates": ["message", "callback_query"]})
        except Exception:
            threading.Event().wait(3)
            continue
        for update in data.get("result") or []:
            if not isinstance(update, dict):
                continue
            _OFFSET = int(update.get("update_id") or _OFFSET) + 1
            try:
                _handle(token, chat, risk, auto, update)
            except Exception:
                continue


def _handle(token: str, chat: str, risk: float, auto: bool, update: dict[str, Any]) -> None:
    message = update.get("message") if isinstance(update.get("message"), dict) else None
    if message is not None:
        incoming = str(message.get("chat", {}).get("id") or "")
        text = str(message.get("text") or "").strip()
        if text.startswith("/start") and incoming:
            if not chat:
                _write(token, incoming, risk, auto)
                chat = incoming
            if incoming != chat:
                return
            state = "on" if auto else "off"
            _send(token, chat, f"Zeus will message this chat when a row is a trade. Tap TRADE, then CONFIRM. Scalp auto is {state}. Send /scalp on to send a scalp without the tap. /risk sets the percent. /sl, /tp, and /r edit the open trade. A price walking toward a zone is not a message.")
            return
        if incoming != chat:
            return
        lower = text.lower()
        if lower.startswith("/scalp"):
            parts = lower.split()
            if len(parts) != 2 or parts[1] not in {"on", "off"}:
                _send(token, chat, f"Scalp auto is {'on' if auto else 'off'}. Send /scalp on or /scalp off.")
                return
            nxt = parts[1] == "on"
            _write(token, chat, risk, nxt)
            if nxt:
                _send(token, chat, "Scalp auto is on. A scalp that is already a trade is sent. Intraday, interday, and swing still need a tap.")
            else:
                _send(token, chat, "Scalp auto is off. A scalp needs a tap again.")
            return
        if not lower.startswith("/risk"):
            if _command(token, chat, text):
                return
            return
        parts = text.split()
        if len(parts) != 2:
            _send(token, chat, "Send /risk and the percent. The next order uses that. Up to 100.")
            return
        try:
            nxt_risk = float(parts[1])
        except ValueError:
            nxt_risk = 0
        if not 0 < nxt_risk <= 100:
            _send(token, chat, "Risk must be above 0 and no more than 100.")
            return
        _write(token, chat, nxt_risk, auto)
        _send(token, chat, f"Next Telegram order risks {nxt_risk:g} percent.")
        return
    query = update.get("callback_query") if isinstance(update.get("callback_query"), dict) else None
    if query is None:
        return
    incoming = str(query.get("message", {}).get("chat", {}).get("id") or query.get("from", {}).get("id") or "")
    if incoming != chat:
        _api(token, "answerCallbackQuery", {"callback_query_id": query.get("id"), "text": "This chat is not the one Zeus is using."})
        return
    data = str(query.get("data") or "")
    _api(token, "answerCallbackQuery", {"callback_query_id": query.get("id")})
    if data.startswith("t"):
        _confirm(token, chat, data[1:])
    elif data.startswith("y"):
        _place(token, chat, data[1:])
    elif data.startswith("n"):
        with _LOCK:
            _OFFERS.pop(data[1:], None)
        _send(token, chat, "Not sent.")
    elif data[:1] in {"e", "h", "x", "H", "X"}:
        _manage_tap(token, chat, data[:1], data[1:])


def _positions(symbol: str) -> list[dict[str, Any]]:
    host = _HOST
    if host is None or not symbol:
        return []
    try:
        from zeus3.v19.signals_page import _positions as listed
    except Exception:
        return []
    try:
        return [row for row in listed(host, symbol) if int(row.get("ticket") or 0) > 0]
    except Exception:
        return []


def _one_position(symbol: str, side: str = "") -> dict[str, Any] | None:
    rows = _positions(symbol)
    if side:
        same = [row for row in rows if row.get("side") == side]
        if len(same) == 1:
            return same[0]
    return rows[0] if len(rows) == 1 else None


def _manage_buttons(symbol: str, side: str) -> list[tuple[str, str]]:
    position = _one_position(symbol, side)
    if position is None:
        return []
    offer = token_hex(4)
    with _LOCK:
        _OFFERS[offer] = {
            "kind": "manage",
            "ticket": int(position["ticket"]),
            "entry": float(position.get("price_open") or 0),
            "at": time(),
        }
    return [("BE", f"e{offer}"), ("50%", f"h{offer}"), ("CLOSE", f"x{offer}")]


def _parse_edit(text: str) -> tuple[str, str, float] | None:
    parts = text.split()
    if not parts or not parts[0].startswith("/"):
        return None
    cmd = parts[0].lower()
    if cmd not in {"/sl", "/tp", "/r"}:
        return None
    names = {name.lower(): key for key, name in _LABELS.items()}
    names.update({key.lower(): key for key in _LABELS})
    if len(parts) == 3 and parts[1].lower() in names:
        try:
            return cmd, names[parts[1].lower()], float(parts[2])
        except ValueError:
            return None
    if len(parts) == 2 and _FOCUS:
        try:
            return cmd, _FOCUS, float(parts[1])
        except ValueError:
            return None
    return None


def _command(token: str, chat: str, text: str) -> bool:
    parsed = _parse_edit(text)
    if parsed is None:
        lower = text.lower()
        if lower.startswith("/sl") or lower.startswith("/tp") or lower.startswith("/r"):
            _send(token, chat, "Send /sl 3832.46, /tp 3881.1, or /r 2. Add the pair if more than one trade is open, for example /sl GOLD 3832.46.")
            return True
        return False
    cmd, symbol, number = parsed
    if number <= 0:
        _send(token, chat, "That number has to be above 0.")
        return True
    position = _one_position(symbol)
    if position is None:
        rows = _positions(symbol)
        if not rows:
            _send(token, chat, f"No open {_LABELS.get(symbol, symbol)} trade to edit.")
        else:
            listed = ", ".join(f"{row['side']} {row['ticket']}" for row in rows)
            _send(token, chat, f"More than one {_LABELS.get(symbol, symbol)} trade is open ({listed}). Close one on the desk first.")
        return True
    entry = float(position.get("price_open") or 0)
    stop = float(position.get("stop_loss") or 0)
    if cmd == "/sl":
        _apply(token, chat, int(position["ticket"]), "MODIFY_POSITION", stop_loss=number)
    elif cmd == "/tp":
        _apply(token, chat, int(position["ticket"]), "MODIFY_POSITION", take_profits=(number,))
    else:
        risk = abs(entry - stop)
        if entry <= 0 or stop <= 0 or risk <= 0:
            _send(token, chat, "No R. The open trade has no stop, so send /tp and the price.")
            return True
        price = entry + risk * number if position.get("side") == "BUY" else entry - risk * number
        _apply(token, chat, int(position["ticket"]), "MODIFY_POSITION", take_profits=(price,))
    return True


def _manage_tap(token: str, chat: str, kind: str, offer_id: str) -> None:
    with _LOCK:
        offer = _OFFERS.get(offer_id)
    if not offer or offer.get("kind") != "manage" or time() - float(offer.get("at") or 0) > 3600:
        _send(token, chat, "That management button has expired.")
        return
    ticket = int(offer["ticket"])
    if kind == "e":
        entry = float(offer.get("entry") or 0)
        if entry <= 0:
            _send(token, chat, "Not moved. The entry price is missing.")
            return
        _apply(token, chat, ticket, "BREAK_EVEN", stop_loss=entry)
    elif kind == "h":
        _send(token, chat, f"Close 50% of ticket {ticket}?", [("CONFIRM", f"H{offer_id}"), ("CANCEL", f"n{offer_id}")])
    elif kind == "x":
        _send(token, chat, f"Close ticket {ticket} at the market?", [("CONFIRM", f"X{offer_id}"), ("CANCEL", f"n{offer_id}")])
    elif kind == "H":
        _apply(token, chat, ticket, "PARTIAL", partial_pct=50)
    elif kind == "X":
        _apply(token, chat, ticket, "CLOSE")


def _apply(token: str, chat: str, ticket: int, action: str, **kwargs: Any) -> None:
    host = _HOST
    if host is None:
        _send(token, chat, "Not sent. Zeus is not ready.")
        return
    try:
        result = host.runtime.manage_physical_trade(
            ticket=ticket,
            action=action,
            partial_pct=kwargs.get("partial_pct"),
            stop_loss=kwargs.get("stop_loss"),
            take_profits=tuple(kwargs.get("take_profits") or ()),
            reason="TELEGRAM",
            include_physical_snapshot=False,
        )
    except Exception as exc:
        _send(token, chat, f"Not changed. {exc}")
        return
    management = result.get("management") if isinstance(result, dict) and isinstance(result.get("management"), dict) else {}
    if management.get("ok") is False:
        _send(token, chat, "Not changed. " + str(management.get("reason") or "the broker did not accept"))
        return
    done = {"BREAK_EVEN": "Stop moved to the entry.", "PARTIAL": "50% closed.", "CLOSE": "Closed.", "MODIFY_POSITION": "Sent to MT5."}
    _send(token, chat, done.get(action, "Sent to MT5."))


def _confirm(token: str, chat: str, offer_id: str) -> None:
    with _LOCK:
        offer = _OFFERS.get(offer_id)
    if not offer or time() - float(offer["at"]) > 600:
        _send(token, chat, "That trade has expired. Wait for the next one.")
        return
    label = _LABELS.get(offer["symbol"], offer["symbol"])
    _send(
        token,
        chat,
        (
            f"Send a MARKET {offer['side']} on {label}?\n"
            f"Stop {offer['stop']}\n"
            f"Target {offer['target']}\n"
            f"Risk {float(offer['risk']):g}%\n"
            "This goes to the MT5 account that is logged in."
        ),
        [("CONFIRM", f"y{offer_id}"), ("CANCEL", f"n{offer_id}")],
    )


def _quote(symbol: str) -> tuple[float, float] | None:
    host = _HOST
    if host is None:
        return None
    try:
        quote = host.runtime.projection.market_data.quote(symbol)
    except Exception:
        return None
    try:
        return float(quote.bid), float(quote.ask)
    except (AttributeError, TypeError, ValueError):
        return None


def _place(token: str, chat: str, offer_id: str) -> None:
    with _LOCK:
        offer = _OFFERS.pop(offer_id, None)
    if not offer or time() - float(offer["at"]) > 600:
        _send(token, chat, "Not sent. That trade has expired.")
        return
    _submit(token, chat, offer, "")


def _submit(token: str, chat: str, offer: dict[str, Any], prefix: str) -> None:
    live = _quote(str(offer["symbol"]))
    if live is not None:
        bid, ask = live
        if offer["side"] == "BUY" and not (offer["stop"] < bid and offer["target"] > ask):
            _send(token, chat, prefix + "Not sent. Price has already gone through this buy.")
            return
        if offer["side"] == "SELL" and not (offer["stop"] > ask and offer["target"] < bid):
            _send(token, chat, prefix + "Not sent. Price has already gone through this sell.")
            return
    host = _HOST
    if host is None:
        _send(token, chat, prefix + "Not sent. Zeus is not ready.")
        return
    try:
        from zeus3.contracts.market_data import Timeframe

        result = host.runtime.execute_owner_order_clean(
            symbol=str(offer["symbol"]),
            timeframe=Timeframe("H4" if offer["chart"] == "SWING" else "M1"),
            order_type="MARKET_BUY" if offer["side"] == "BUY" else "MARKET_SELL",
            requested_entry=None,
            stop=float(offer["stop"]),
            targets=(float(offer["target"]),),
            target_specs=(),
            requested_risk_pct=float(offer["risk"]),
            horizon_lane="INTRADAY",
            owner_note=f"TELEGRAM {offer['chart']} {offer['reason']}",
        )
    except Exception as exc:
        _send(token, chat, prefix + f"Not sent. {exc}")
        return
    label = _LABELS.get(offer["symbol"], offer["symbol"])
    if not isinstance(result, dict):
        _send(token, chat, prefix + f"Sent. {offer['side']} {label}.")
        return
    execution = result.get("execution") if isinstance(result.get("execution"), dict) else result
    blockers = [str(item) for item in (execution.get("blockers") or result.get("blockers") or []) if item]
    if result.get("ok") is False or execution.get("submitted") is False or result.get("submitted") is False:
        _send(token, chat, prefix + "Not sent. " + (" · ".join(blockers) or str(result.get("message") or "the broker did not accept")))
        return
    _send(token, chat, prefix + f"Sent. {offer['side']} {label} is on its way to MT5.")
