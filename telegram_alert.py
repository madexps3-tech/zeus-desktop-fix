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
    if not 0 < risk <= 5:
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
    token, chat, risk, auto = _read()
    if not token or not chat or not payload.get("ok"):
        return
    symbol = str(payload.get("symbol") or "")
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
            try:
                _send(token, chat, f"{label} {chart} {row.get('side')}\n{guide}")
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
            _send(token, chat, f"Zeus will message this chat when a row is a trade. Tap TRADE, then CONFIRM. Scalp auto is {state}. Send /scalp on to send a scalp without the tap. A price walking toward a zone is not a message.")
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
            return
        parts = text.split()
        if len(parts) != 2:
            _send(token, chat, "Send /risk 2 to risk 2 percent of the account on the next order.")
            return
        try:
            nxt_risk = float(parts[1])
        except ValueError:
            nxt_risk = 0
        if not 0 < nxt_risk <= 5:
            _send(token, chat, "Risk must be above 0 and no more than 5.")
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
