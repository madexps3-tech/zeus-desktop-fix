"""Send a ready Zeus trade to Telegram, and place it only after CONFIRM.

The bot token stays in telegram.txt next to this install. A coming-into line is not a message.
"""

from __future__ import annotations

import json
import re
import struct
import threading
import urllib.request
import zlib
from contextlib import contextmanager
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
_REPLIES: dict[int, str] = {}
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


def _read() -> tuple[str, str, float, bool, bool]:
    path = _file()
    if not path.is_file():
        return "", "", 2.0, False, False
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    token = lines[0] if lines else ""
    chat = lines[1] if len(lines) > 1 else ""
    risk = 2.0
    if len(lines) > 2:
        try:
            risk = float(lines[2])
        except ValueError:
            risk = 2.0
    if not 0 < risk:
        risk = 2.0
    auto = len(lines) > 3 and lines[3].lower() == "on"
    ice = len(lines) > 4 and lines[4].lower() == "on"
    return token, chat, risk, auto, ice


def _write(token: str, chat: str, risk: float, auto: bool, ice: bool = False) -> None:
    _file().write_text(f"{token}\n{chat}\n{risk}\n{'on' if auto else 'off'}\n{'on' if ice else 'off'}\n", encoding="utf-8")


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


def _send(
    token: str,
    chat: str,
    text: str,
    buttons: list[tuple[str, str]] | None = None,
    *,
    one_row: bool = False,
    reply: bool = False,
    photo: bytes | None = None,
) -> int | None:
    if photo:
        try:
            return _send_photo(token, chat, photo, text, buttons, one_row=one_row)
        except Exception:
            pass
    payload: dict[str, Any] = {"chat_id": chat, "text": text[:4000]}
    if buttons:
        cells = [{"text": label, "callback_data": data} for label, data in buttons]
        rows = [cells] if one_row else [[cell] for cell in cells]
        payload["reply_markup"] = {"inline_keyboard": rows}
    elif reply:
        payload["reply_markup"] = {
            "force_reply": True,
            "selective": True,
            "input_field_placeholder": "risk 1, tp 63400, sl 64600",
        }
    data = _api(token, "sendMessage", payload)
    try:
        return int(data["result"]["message_id"])
    except (KeyError, TypeError, ValueError):
        return None


def _send_photo(
    token: str,
    chat: str,
    photo: bytes,
    caption: str,
    buttons: list[tuple[str, str]] | None,
    *,
    one_row: bool,
) -> int | None:
    fields = {"chat_id": chat, "caption": caption[:1024]}
    if buttons:
        cells = [{"text": label, "callback_data": data} for label, data in buttons]
        rows = [cells] if one_row else [[cell] for cell in cells]
        fields["reply_markup"] = json.dumps({"inline_keyboard": rows})
    boundary = "----ZeusShot"
    body = bytearray()
    for key, value in fields.items():
        body.extend(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"\r\n\r\n{value}\r\n".encode()
        )
    body.extend(
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"photo\"; filename=\"chart.png\"\r\nContent-Type: image/png\r\n\r\n".encode()
    )
    body.extend(photo)
    body.extend(f"\r\n--{boundary}--\r\n".encode())
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendPhoto",
        data=bytes(body),
        headers={"content-type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))
    try:
        return int(data["result"]["message_id"])
    except (KeyError, TypeError, ValueError):
        return None


_FONT = {
    " ": (0, 0, 0, 0, 0, 0, 0),
    "-": (0, 0, 0, 31, 0, 0, 0),
    ".": (0, 0, 0, 0, 0, 12, 12),
    "0": (14, 17, 19, 21, 25, 17, 14),
    "1": (4, 12, 4, 4, 4, 4, 14),
    "2": (14, 17, 1, 6, 8, 16, 31),
    "3": (14, 17, 1, 6, 1, 17, 14),
    "4": (2, 6, 10, 18, 31, 2, 2),
    "5": (31, 16, 30, 1, 1, 17, 14),
    "6": (14, 16, 16, 30, 17, 17, 14),
    "7": (31, 1, 2, 4, 8, 8, 8),
    "8": (14, 17, 17, 14, 17, 17, 14),
    "9": (14, 17, 17, 15, 1, 1, 14),
    "A": (14, 17, 17, 31, 17, 17, 17),
    "B": (30, 17, 17, 30, 17, 17, 30),
    "C": (14, 17, 16, 16, 16, 17, 14),
    "D": (30, 17, 17, 17, 17, 17, 30),
    "E": (31, 16, 16, 30, 16, 16, 31),
    "F": (31, 16, 16, 30, 16, 16, 16),
    "G": (14, 17, 16, 23, 17, 17, 14),
    "H": (17, 17, 17, 31, 17, 17, 17),
    "I": (14, 4, 4, 4, 4, 4, 14),
    "J": (7, 2, 2, 2, 2, 18, 12),
    "K": (17, 18, 20, 24, 20, 18, 17),
    "L": (16, 16, 16, 16, 16, 16, 31),
    "M": (17, 27, 21, 21, 17, 17, 17),
    "N": (17, 25, 21, 19, 17, 17, 17),
    "O": (14, 17, 17, 17, 17, 17, 14),
    "P": (30, 17, 17, 30, 16, 16, 16),
    "Q": (14, 17, 17, 17, 21, 18, 13),
    "R": (30, 17, 17, 30, 20, 18, 17),
    "S": (14, 17, 16, 14, 1, 17, 14),
    "T": (31, 4, 4, 4, 4, 4, 4),
    "U": (17, 17, 17, 17, 17, 17, 14),
    "V": (17, 17, 17, 17, 10, 10, 4),
    "W": (17, 17, 17, 21, 21, 27, 17),
    "X": (17, 17, 10, 4, 10, 17, 17),
    "Y": (17, 17, 10, 4, 4, 4, 4),
    "Z": (31, 1, 2, 4, 8, 16, 31),
}


def _png(width: int, height: int, rgb: bytearray) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    raw = bytearray()
    stride = width * 3
    for y in range(height):
        raw.append(0)
        raw.extend(rgb[y * stride:(y + 1) * stride])
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(bytes(raw), 6)) + chunk(b"IEND", b"")


def _dot(rgb: bytearray, width: int, height: int, x: int, y: int, color: tuple[int, int, int]) -> None:
    if 0 <= x < width and 0 <= y < height:
        i = (y * width + x) * 3
        rgb[i:i + 3] = bytes(color)


def _text(rgb: bytearray, width: int, height: int, x: int, y: int, text: str, color: tuple[int, int, int]) -> None:
    for ch in text.upper():
        glyph = _FONT.get(ch, _FONT[" "])
        for row, bits in enumerate(glyph):
            for col in range(5):
                if bits & (1 << (4 - col)):
                    for dy in (0, 1):
                        for dx in (0, 1):
                            _dot(rgb, width, height, x + col * 2 + dx, y + row * 2 + dy, color)
        x += 12


def _price_text(price: float) -> str:
    size = abs(price)
    digits = 2 if size >= 100 else 3 if size >= 10 else 5
    return f"{price:.{digits}f}"


def chart_png(candles: list[dict[str, Any]], title: str, side: str, entry: float, stop: float, targets: list[float]) -> bytes | None:
    """One phone-sized chart. Candles, the entry, the stop, and the targets."""
    bars = []
    for bar in candles[-70:]:
        if not isinstance(bar, dict):
            continue
        try:
            bars.append((float(bar.get("o", bar.get("open"))), float(bar.get("h", bar.get("high"))), float(bar.get("l", bar.get("low"))), float(bar.get("c", bar.get("close")))))
        except (TypeError, ValueError):
            continue
    if len(bars) < 8:
        return None
    marks = [entry, stop, *[float(price) for price in targets if price is not None]]
    lows = [bar[2] for bar in bars] + marks
    highs = [bar[1] for bar in bars] + marks
    low = min(lows)
    high = max(highs)
    if not high > low:
        return None
    pad = (high - low) * 0.06
    low -= pad
    high += pad
    width, height = 960, 540
    rgb = bytearray(b"\x0e\x16\x20" * (width * height))
    left, right, top, bottom = 24, 820, 46, 500
    span = high - low

    def y_of(price: float) -> int:
        return top + int((high - price) / span * (bottom - top))

    grid = (28, 42, 58)
    for step in range(5):
        y = top + int((bottom - top) * step / 4)
        for x in range(left, right):
            _dot(rgb, width, height, x, y, grid)
    slot = (right - left) / len(bars)
    up = (92, 204, 148)
    down = (214, 96, 104)
    for index, (open_, high_, low_, close) in enumerate(bars):
        x = left + int(index * slot + slot / 2)
        color = up if close >= open_ else down
        y1, y2 = y_of(high_), y_of(low_)
        for y in range(min(y1, y2), max(y1, y2) + 1):
            _dot(rgb, width, height, x, y, color)
        body_top = y_of(max(open_, close))
        body_bot = y_of(min(open_, close))
        if body_bot - body_top < 1:
            body_bot = body_top + 1
        half = max(1, int(slot * 0.32))
        for y in range(body_top, body_bot + 1):
            for dx in range(-half, half + 1):
                _dot(rgb, width, height, x + dx, y, color)
    ink = (236, 232, 214)
    lines = [(entry, "ENTRY", (232, 196, 96)), (stop, "STOP", (214, 96, 104))]
    for index, price in enumerate(targets[:4]):
        try:
            lines.append((float(price), f"T{index + 1}", (120, 186, 230)))
        except (TypeError, ValueError):
            continue
    used = []
    for price, name, color in lines:
        y = y_of(price)
        for x in range(left, right):
            if x % 4 < 3:
                _dot(rgb, width, height, x, y, color)
        label_y = y - 8
        for taken in used:
            if abs(label_y - taken) < 16:
                label_y = taken + 16
        used.append(label_y)
        _text(rgb, width, height, right + 12, max(8, min(label_y, height - 20)), f"{name} {_price_text(price)}", color)
    tone = up if side == "BUY" else down
    _text(rgb, width, height, 24, 12, title[:42], tone if side in {"BUY", "SELL"} else ink)
    return _png(width, height, rgb)


def _money(row: dict[str, Any], account: Any, risk: float) -> str:
    """Same line as the desk: each target in R, and the dollar value of that R at the chosen risk."""
    entry = row.get("entry")
    stop = row.get("risk_stop") if row.get("risk_stop") is not None else row.get("stop")
    if entry is None or stop is None:
        return ""
    try:
        risk_dist = abs(float(entry) - float(stop))
    except (TypeError, ValueError):
        return ""
    targets = row.get("targets") if isinstance(row.get("targets"), list) else []
    if not targets and row.get("target") is not None:
        targets = [row.get("target")]
    if risk_dist <= 0 or not targets:
        return ""
    balance = 0.0
    if isinstance(account, dict):
        raw = account.get("equity") if account.get("equity") not in (None, 0) else account.get("balance")
        try:
            balance = float(raw or 0)
        except (TypeError, ValueError):
            balance = 0.0
    bits = []
    for index, price in enumerate(targets, 1):
        try:
            reward = abs(float(price) - float(entry))
        except (TypeError, ValueError):
            continue
        mult = round(reward / risk_dist, 2)
        cash = f" ${round(balance * risk * mult / 100)}" if risk > 0 and balance > 0 else ""
        bits.append(f"T{index} {mult:.2f}R{cash}")
    return " · ".join(bits)


def _truth() -> Any:
    host = _HOST
    if host is None:
        return None
    try:
        return host.runtime.core.broker_truth.get(host.runtime.worker.profile_id)
    except Exception:
        return None


def _balance_text() -> str:
    account = getattr(_truth(), "account", None)
    if account is None:
        return ""
    bits = []
    balance = getattr(account, "balance", None)
    equity = getattr(account, "equity", None)
    if balance is not None:
        bits.append(f"Balance {balance}")
    if equity is not None:
        bits.append(f"Equity {equity}")
    return " · ".join(bits)


def _rows(symbol: str = "") -> list[dict[str, Any]]:
    truth = _truth()
    if truth is None:
        return []
    try:
        from zeus3.v19.signals_page import PAIRS, _same_pair
    except Exception:
        return []
    found = []
    for row in getattr(truth, "positions", ()) or ():
        broker = str(getattr(row, "broker_symbol", "") or "")
        matched = next((name for name in PAIRS if _same_pair(name, broker)), "")
        if symbol and matched != symbol:
            continue
        if not symbol and not matched:
            continue
        try:
            profit = f"{float(getattr(row, 'profit', None)):.2f}"
        except (TypeError, ValueError):
            profit = "—"
        found.append(
            {
                "label": _LABELS.get(matched, matched or broker),
                "broker": broker or matched,
                "side": "BUY" if int(getattr(row, "type_code", 1) or 1) == 0 else "SELL",
                "volume": getattr(row, "volume", None),
                "price_open": getattr(row, "price_open", None),
                "stop": getattr(row, "stop_loss", None),
                "target": getattr(row, "take_profit", None),
                "profit": profit,
            }
        )
    return found


def _position_text(symbol: str = "", side: str = "") -> str:
    rows = _rows(symbol)
    if side:
        same = [row for row in rows if row["side"] == side]
        if same:
            rows = same
    return "\n".join(
        f"{row['broker']}  {row['side']} {row['volume']} @ {row['price_open']}  P/L {row['profit']}  SL {row['stop']}  TP {row['target']}"
        for row in rows
    )


def _stamp(symbol: str = "", side: str = "") -> str:
    lines = [line for line in (_position_text(symbol, side), _balance_text()) if line]
    return "\n".join(lines)


@contextmanager
def _charts_aside():
    """Keep a chart history from holding MetaTrader while the order is going out."""
    try:
        from zeus3.v19.signals_page import _ORDER_BUSY
    except Exception:
        yield
        return
    _ORDER_BUSY.set()
    try:
        yield
    finally:
        _ORDER_BUSY.clear()


def start(host: Any) -> None:
    global _STARTED, _HOST
    _HOST = host
    token, _, _, _, _ = _read()
    if not token or _STARTED:
        return
    _STARTED = True
    threading.Thread(target=_poll, name="zeus-telegram", daemon=True).start()


def announce(payload: dict[str, Any]) -> None:
    """A tradeable row gets one message with TRADE. A scalp or iceberg with its own auto on is sent without the tap."""
    global _FOCUS
    token, chat, risk, auto, ice = _read()
    if not token or not chat or not payload.get("ok"):
        return
    symbol = str(payload.get("symbol") or "")
    _FOCUS = symbol
    label = _LABELS.get(symbol, payload.get("label") or symbol)
    for row in payload.get("rows") or []:
        if not isinstance(row, dict) or not row.get("side") or row.get("entry") is None or row.get("stop") is None:
            continue
        chart = str(row.get("chart") or "")
        if chart not in {"INTRADAY", "INTERDAY", "SCALP", "SWING", "ICEBERG"}:
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
            money = _money(row, payload.get("account"), risk)
            with _LOCK:
                _OFFERS[offer] = {
                    "symbol": symbol,
                    "chart": chart,
                    "side": str(row.get("side")),
                    "entry": float(row["entry"]),
                    "stop": float(row["stop"]),
                    "target": float(target),
                    "reason": str(row.get("reason") or ""),
                    "risk": risk,
                    "money": money,
                    "at": time(),
                }
            text = (
                f"{label} {chart} {row.get('side')}\n"
                f"Entry {row.get('entry')}\n"
                f"Stop {row.get('stop')}\n"
                f"Next {target}\n"
                f"Risk {risk:g}%"
            )
            if money:
                text += f"\n{money}"
            held = _stamp(symbol, str(row.get("side") or ""))
            if held:
                text += f"\n{held}"
            if guide:
                text += f"\n{guide}"
                _mark(f"G|{symbol}|{chart}|{row.get('side')}|{guide}")
            text += "\nTap EDIT. It shows the risk, target, and stop. Reply with only the line you want to change."
            photo = None
            try:
                shots = payload.get("shots") if isinstance(payload.get("shots"), dict) else {}
                frame = "H1" if chart in {"SWING", "INTERDAY"} else "M5"
                candles = shots.get(frame) or shots.get("M15") or shots.get("M5") or []
                prices = [float(price) for price in targets if price is not None] or [float(target)]
                photo = chart_png(candles, f"{label} {chart} {row.get('side')}", str(row.get("side")), float(row["entry"]), float(row["stop"]), prices)
            except Exception:
                photo = None
            if chart == "SCALP" and auto:
                with _LOCK:
                    row_offer = _OFFERS.pop(offer)
                _submit(token, chat, row_offer, "Scalp auto. ")
                if photo:
                    try:
                        _send(token, chat, text, photo=photo)
                    except Exception:
                        pass
                continue
            if chart == "ICEBERG" and ice:
                with _LOCK:
                    row_offer = _OFFERS.pop(offer)
                _submit(token, chat, row_offer, "Iceberg auto. ")
                if photo:
                    try:
                        _send(token, chat, text, photo=photo)
                    except Exception:
                        pass
                continue
            try:
                _send(token, chat, text, [("TRADE", f"t{offer}"), ("EDIT", f"z{offer}")], one_row=True, photo=photo)
            except Exception:
                with _LOCK:
                    _OFFERS.pop(offer, None)
                _SENT.pop(key, None)
        if guide and _fresh(f"G|{symbol}|{chart}|{row.get('side')}|{guide}"):
            text = f"{label} {chart} {row.get('side')}\n{guide}"
            buttons = _manage_buttons(symbol, str(row.get("side") or ""))
            if buttons:
                text += "\nBE moves the stop to the entry. 50% banks half. Or send /sl, /tp, or /r."
            held = _stamp(symbol, str(row.get("side") or ""))
            if held:
                text += f"\n{held}"
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
        token, chat, risk, auto, ice = _read()
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
                _handle(token, chat, risk, auto, ice, update)
            except Exception:
                continue


def _handle(token: str, chat: str, risk: float, auto: bool, ice: bool, update: dict[str, Any]) -> None:
    message = update.get("message") if isinstance(update.get("message"), dict) else None
    if message is not None:
        incoming = str(message.get("chat", {}).get("id") or "")
        text = str(message.get("text") or "").strip()
        if text.startswith("/start") and incoming:
            if not chat:
                _write(token, incoming, risk, auto, ice)
                chat = incoming
            if incoming != chat:
                return
            state = "on" if auto else "off"
            ice_state = "on" if ice else "off"
            _send(token, chat, f"Zeus will message this chat when a row is a trade. Tap TRADE, then CONFIRM. Scalp auto is {state}. Iceberg auto is {ice_state}. Send /scalp on or /ice on to send that one without the tap. /manage on moves the stop. Banking stays a button. /risk sets the percent. /sl, /tp, and /r edit the open trade. A price walking toward a zone is not a message.")
            return
        if incoming != chat:
            return
        reply_to = message.get("reply_to_message") if isinstance(message.get("reply_to_message"), dict) else None
        reply_id = int(reply_to.get("message_id") or 0) if reply_to else 0
        if reply_id and reply_id in _REPLIES:
            _apply_reply(token, chat, _REPLIES[reply_id], text)
            return
        lower = text.lower()
        if lower in {"/pnl", "/balance"}:
            _send(token, chat, _stamp() or "No broker read yet.")
            return
        if lower.startswith("/scalp"):
            parts = lower.split()
            if len(parts) != 2 or parts[1] not in {"on", "off"}:
                _send(token, chat, f"Scalp auto is {'on' if auto else 'off'}. Send /scalp on or /scalp off.")
                return
            nxt = parts[1] == "on"
            _write(token, chat, risk, nxt, ice)
            if nxt:
                _send(token, chat, "Scalp auto is on. A scalp that is already a trade is sent. Intraday, interday, and swing still need a tap.")
            else:
                _send(token, chat, "Scalp auto is off. A scalp needs a tap again.")
            return
        if lower.startswith("/ice"):
            parts = lower.split()
            if len(parts) != 2 or parts[1] not in {"on", "off"}:
                _send(token, chat, f"Iceberg auto is {'on' if ice else 'off'}. Send /ice on or /ice off.")
                return
            nxt_ice = parts[1] == "on"
            _write(token, chat, risk, auto, nxt_ice)
            if nxt_ice:
                _send(token, chat, "Iceberg auto is on. A gold, oil, or Nasdaq iceberg that has already refilled is sent. The other rows still need a tap.")
            else:
                _send(token, chat, "Iceberg auto is off. An iceberg needs a tap again.")
            return
        if lower.startswith("/manage"):
            parts = lower.split()
            if len(parts) != 2 or parts[1] not in {"on", "off"}:
                from zeus3.v19.signals_page import manage_enabled
                _send(token, chat, f"Manage is {'on' if manage_enabled() else 'off'}. Send /manage on or /manage off.")
                return
            from zeus3.v19.signals_page import set_manage
            set_manage(parts[1] == "on")
            if parts[1] == "on":
                _send(token, chat, "Manage is on. At 1R the stop moves to the entry. Near the first target Zeus tells you to bank. It does not close the trade.")
            else:
                _send(token, chat, "Manage is off. Open tickets are left alone.")
            return
        if not lower.startswith("/risk"):
            if _command(token, chat, text):
                return
            return
        parts = text.split()
        if len(parts) != 2:
            _send(token, chat, "Send /risk and the percent. The next order uses that number.")
            return
        try:
            nxt_risk = float(parts[1])
        except ValueError:
            nxt_risk = 0
        if not 0 < nxt_risk:
            _send(token, chat, "Risk must be above 0.")
            return
        _write(token, chat, nxt_risk, auto, ice)
        pending = _pending()
        if pending is not None:
            _touch(pending[0], risk=nxt_risk)
            _send(token, chat, f"This trade now risks {nxt_risk:g} percent.")
            _confirm(token, chat, pending[0])
            return
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
    elif data.startswith("z"):
        _ask_edit(token, chat, data[1:])
    elif data.startswith("y"):
        _place(token, chat, data[1:])
    elif data.startswith("n"):
        with _LOCK:
            _OFFERS.pop(data[1:], None)
        _send(token, chat, "Not sent.")
    elif data[:1] in {"e", "h", "x", "H", "X"}:
        _manage_tap(token, chat, data[:1], data[1:])


def _ask_edit(token: str, chat: str, offer_id: str) -> None:
    with _LOCK:
        offer = _OFFERS.get(offer_id)
    if not offer or "symbol" not in offer or time() - float(offer.get("at") or 0) > 600:
        _send(token, chat, "That trade has expired. Wait for the next one.")
        return
    label = _LABELS.get(str(offer["symbol"]), str(offer["symbol"]))
    message_id = _send(
        token,
        chat,
        (
            f"{label} {offer['side']}\n"
            f"risk {float(offer.get('risk') or 0):g}\n"
            f"tp {offer.get('target')}\n"
            f"sl {offer.get('stop')}\n"
            "Reply to this message with only the line you want to change.\n"
            "risk 1\n"
            "The other two stay as they are."
        ),
        reply=True,
    )
    if message_id is None:
        return
    _REPLIES[message_id] = offer_id
    if len(_REPLIES) > 40:
        for key in list(_REPLIES)[:10]:
            _REPLIES.pop(key, None)


def _apply_reply(token: str, chat: str, offer_id: str, text: str) -> None:
    with _LOCK:
        offer = _OFFERS.get(offer_id)
    if not offer or "symbol" not in offer or time() - float(offer.get("at") or 0) > 600:
        _send(token, chat, "That trade has expired. Wait for the next one.")
        return
    lower = text.lower()
    found: dict[str, float] = {}
    for key, pattern in (
        ("risk", r"risk\s*[:=]?\s*([0-9]+(?:\.[0-9]+)?)"),
        ("tp", r"(?:tp|target)\s*[:=]?\s*([0-9]+(?:\.[0-9]+)?)"),
        ("sl", r"(?:sl|stop)\s*[:=]?\s*([0-9]+(?:\.[0-9]+)?)"),
        ("r", r"(?<![a-z])r\s*[:=]?\s*([0-9]+(?:\.[0-9]+)?)"),
    ):
        match = re.search(pattern, lower)
        if match:
            found[key] = float(match.group(1))
    if not found:
        _send(token, chat, "Reply to that message with risk 1, tp 63400, or sl 64600.")
        return
    if "risk" in found and not 0 < found["risk"]:
        _send(token, chat, "Risk must be above 0.")
        return
    changes: dict[str, Any] = {}
    if "risk" in found:
        changes["risk"] = found["risk"]
    if "sl" in found:
        changes["stop"] = found["sl"]
    if "tp" in found:
        changes["target"] = found["tp"]
    elif "r" in found:
        entry = float(offer.get("entry") or 0)
        stop = float(changes.get("stop", offer.get("stop") or 0))
        span = abs(entry - stop)
        if entry <= 0 or span <= 0:
            _send(token, chat, "No R on this trade. Reply with tp and the price.")
            return
        changes["target"] = entry + span * found["r"] if offer.get("side") == "BUY" else entry - span * found["r"]
    _touch(offer_id, **changes)
    if "risk" in changes:
        _, _, _, auto, ice = _read()
        _write(token, chat, float(changes["risk"]), auto, ice)
    _send(token, chat, "Updated. Confirm this one.")
    _confirm(token, chat, offer_id)


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


def _pending() -> tuple[str, dict[str, Any]] | None:
    now = time()
    best: tuple[str, dict[str, Any]] | None = None
    with _LOCK:
        for key, offer in _OFFERS.items():
            if offer.get("kind") == "manage" or "symbol" not in offer:
                continue
            if now - float(offer.get("at") or 0) > 600:
                continue
            if best is None or float(offer.get("at") or 0) >= float(best[1].get("at") or 0):
                best = (key, offer)
    return best


def _offer_money(offer: dict[str, Any]) -> str:
    account: dict[str, Any] = {}
    truth = _truth()
    row = getattr(truth, "account", None)
    if row is not None:
        account = {"equity": getattr(row, "equity", None), "balance": getattr(row, "balance", None)}
    return _money(
        {"entry": offer.get("entry"), "stop": offer.get("stop"), "target": offer.get("target"), "targets": [offer.get("target")]},
        account,
        float(offer.get("risk") or 0),
    )


def _touch(offer_id: str, **changes: Any) -> None:
    with _LOCK:
        offer = _OFFERS.get(offer_id)
        if offer is None:
            return
        offer.update(changes)
        offer["at"] = time()
        offer["money"] = _offer_money(offer)


def _command(token: str, chat: str, text: str) -> bool:
    raw = text.strip()
    if raw[:1] != "/":
        raw = "/" + raw
    parsed = _parse_edit(raw)
    if parsed is None:
        lower = raw.lower()
        if lower.startswith("/sl") or lower.startswith("/tp") or lower.startswith("/r"):
            _send(token, chat, "Send /sl 3832.46, /tp 3881.1, or /r 2. That changes the trade waiting for CONFIRM. If none is waiting, it changes the open ticket.")
            return True
        return False
    cmd, symbol, number = parsed
    if number <= 0:
        _send(token, chat, "That number has to be above 0.")
        return True
    pending = _pending()
    named = len(raw.split()) == 3
    if pending is not None and (not named or symbol == pending[1].get("symbol")):
        offer_id, offer = pending
        if cmd == "/sl":
            _touch(offer_id, stop=number)
            _send(token, chat, f"Stop on this {_LABELS.get(offer['symbol'], offer['symbol'])} {offer['side']} is now {number}.")
        elif cmd == "/tp":
            _touch(offer_id, target=number)
            _send(token, chat, f"Target on this {_LABELS.get(offer['symbol'], offer['symbol'])} {offer['side']} is now {number}.")
        else:
            entry = float(offer.get("entry") or 0)
            stop = float(offer.get("stop") or 0)
            span = abs(entry - stop)
            if entry <= 0 or span <= 0:
                _send(token, chat, "No R on this trade. Send /tp and the price.")
                return True
            price = entry + span * number if offer.get("side") == "BUY" else entry - span * number
            _touch(offer_id, target=price)
            _send(token, chat, f"Target is now {price}, which is {number:g}R.")
        _confirm(token, chat, offer_id)
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
        with _charts_aside():
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
    held = _stamp()
    _send(token, chat, done.get(action, "Sent to MT5.") + (("\n" + held) if held else ""))


def announce_manage(symbol: str, text: str, ticket: int, entry: float) -> None:
    """One message when the stop moves or the bank line changes. The half is still a tap."""
    token, chat, _risk, _auto, _ice = _read()
    if not token or not chat or not text:
        return
    key = f"M|{ticket}|{text}"
    if not _fresh(key):
        return
    offer_id = token_hex(4)
    buttons = None
    if text.startswith("Bank half"):
        with _LOCK:
            _OFFERS[offer_id] = {"kind": "manage", "ticket": ticket, "entry": entry, "at": time()}
        buttons = [("BANK HALF", f"h{offer_id}")]
    elif text.startswith("Bank"):
        with _LOCK:
            _OFFERS[offer_id] = {"kind": "manage", "ticket": ticket, "entry": entry, "at": time()}
        buttons = [("BANK", f"x{offer_id}")]
    label = _LABELS.get(symbol, symbol)
    try:
        _send(token, chat, f"{label}\n{text}", buttons)
    except Exception:
        _SENT.pop(key, None)


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
            + (str(offer.get("money") or "") + "\n" if offer.get("money") else "")
            + (_stamp(str(offer.get("symbol") or ""), str(offer.get("side") or "")) + "\n" if _stamp(str(offer.get("symbol") or ""), str(offer.get("side") or "")) else "")
            + "This goes to the MT5 account that is logged in."
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
    entry_ref = float(offer["stop"])
    if live is not None:
        bid, ask = live
        entry_ref = bid if offer["side"] == "SELL" else ask
    try:
        from zeus3.contracts.market_data import Timeframe

        with _charts_aside():
            result = host.runtime.execute_owner_order_fast(
                symbol=str(offer["symbol"]),
                timeframe=Timeframe("H4" if offer["chart"] == "SWING" else "M1"),
                order_type="MARKET_BUY" if offer["side"] == "BUY" else "MARKET_SELL",
                requested_entry=float(entry_ref),
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
        _send(token, chat, prefix + f"Sent. {offer['side']} {label}.\n" + _stamp(str(offer["symbol"]), str(offer["side"])))
        return
    execution = result.get("execution") if isinstance(result.get("execution"), dict) else result
    blockers = [str(item) for item in (execution.get("blockers") or result.get("blockers") or []) if item]
    blocked = " ".join(blockers)
    if (result.get("submitted") is False or execution.get("submitted") is False) and ("CACHE" in blocked or "UNRESOLVED" in blocked):
        try:
            with _charts_aside():
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
        execution = result.get("execution") if isinstance(result, dict) and isinstance(result.get("execution"), dict) else result
        blockers = [str(item) for item in ((execution or {}).get("blockers") or (result or {}).get("blockers") or []) if item]
    if not isinstance(result, dict) or result.get("ok") is False or (execution or {}).get("submitted") is False or result.get("submitted") is False:
        reason = "the broker did not accept"
        if isinstance(result, dict):
            reason = str(result.get("message") or reason)
        _send(token, chat, prefix + "Not sent. " + (" · ".join(blockers) or reason))
        return
    timings = result.get("timings_ms") if isinstance(result.get("timings_ms"), dict) else {}
    ms = f"\n{timings.get('total')} ms" if timings.get("total") is not None else ""
    held = _stamp(str(offer["symbol"]), str(offer["side"]))
    _send(token, chat, prefix + f"Sent. {offer['side']} {label}.\n" + (held + "\n" if held else "") + ms.strip())
