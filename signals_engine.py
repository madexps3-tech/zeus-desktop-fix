"""Manual signals. 15-minute place, 1-minute fill. TRADE only at 1.5R or more."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

PAIRS = ("XAUUSD", "XAGUSD", "NAS100", "BTCUSD", "EURUSD", "USDJPY", "WTI")
CHARTS = ("M1", "M5", "M15", "M30", "H1", "H4", "D1")
MIN_R = 0.5
TRADE_R = 0.5
MANUAL = {"PULLBACK", "BREAK", "RANGE", "SWING", "ICEBERG", "CHOCH"}
# A 1-minute wick wider than this is not a scalp. Price units, not pips.
MAX_WICK = {
    "XAUUSD": 8.0,
    "XAGUSD": 0.20,
    "NAS100": 80.0,
    "WTI": 0.40,
    "EURUSD": 0.0012,
    "USDJPY": 0.20,
    "BTCUSD": 200.0,
}
# One price step past an iceberg. The spread rule can still block it.
ICE_TICK = {
    "XAUUSD": 0.1,
    "XAGUSD": 0.005,
    "NAS100": 1.0,
    "WTI": 0.01,
    "EURUSD": 0.0001,
    "USDJPY": 0.01,
    "BTCUSD": 1.0,
}
WING = 2
LOG = Path("signal_research_v2.jsonl")
STATE = Path("signal_research_state_v2.json")
FLOW_PAIRS = {"XAUUSD", "NAS100", "WTI"}
# How far price must move before the second score puts the stop at the entry.
BE_MOVE = {
    "XAUUSD": 2.0,
    "XAGUSD": 0.20,
    "NAS100": 20.0,
    "WTI": 0.20,
    "EURUSD": 0.0020,
    "USDJPY": 0.20,
    "BTCUSD": 20.0,
}
# A futures price this far from the CFD is not drawn. The gap is measured live.
MAX_BASIS = {
    "XAUUSD": 80.0,
    "XAGUSD": 2.0,
    "NAS100": 400.0,
    "WTI": 5.0,
    "EURUSD": 0.02,
    "USDJPY": 2.0,
    "BTCUSD": 2000.0,
}
POSITION_NAMES = {
    "XAUUSD": ("XAUUSD", "XAU"),
    "XAGUSD": ("XAGUSD", "XAG"),
    "NAS100": ("NAS100", "NAS", "US100", "USTEC"),
    "BTCUSD": ("BTCUSD", "BTC"),
    "EURUSD": ("EURUSD",),
    "USDJPY": ("USDJPY",),
    "WTI": ("WTI", "USOIL", "USOUSD", "XTIUSD", "XTI", "CL"),
}
# The file the new study can write. Bitcoin is checked under both names.
FUTURES_ROOTS = {
    "XAUUSD": ("GC",),
    "XAGUSD": ("SI",),
    "NAS100": ("NQ",),
    "WTI": ("CL",),
    "EURUSD": ("6E",),
    "USDJPY": ("6J",),
    "BTCUSD": ("BTC", "MBT"),
}


def _num(bar: dict[str, Any], name: str) -> float:
    return float(bar[name])


def _time(bar: dict[str, Any]) -> str:
    return str(bar.get("time") or "")


def _when(stamp: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def swings(bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A swing is confirmed only after two bars on each side."""
    found: list[dict[str, Any]] = []
    for index in range(WING, len(bars) - WING):
        high = _num(bars[index], "high")
        low = _num(bars[index], "low")
        left = bars[index - WING : index]
        right = bars[index + 1 : index + 1 + WING]
        if high > max(_num(bar, "high") for bar in left + right):
            found.append({"kind": "HIGH", "index": index, "price": high, "time": _time(bars[index])})
        if low < min(_num(bar, "low") for bar in left + right):
            found.append({"kind": "LOW", "index": index, "price": low, "time": _time(bars[index])})
    return found


def _trend(points: list[dict[str, Any]]) -> str:
    highs = [point for point in points if point["kind"] == "HIGH"][-2:]
    lows = [point for point in points if point["kind"] == "LOW"][-2:]
    if len(highs) < 2 or len(lows) < 2:
        return "RANGE"
    higher_high = highs[1]["price"] > highs[0]["price"]
    higher_low = lows[1]["price"] > lows[0]["price"]
    lower_high = highs[1]["price"] < highs[0]["price"]
    lower_low = lows[1]["price"] < lows[0]["price"]
    if higher_high and higher_low:
        return "UP"
    if lower_high and lower_low:
        return "DOWN"
    return "RANGE"


def market_state(points: list[dict[str, Any]]) -> str:
    """A label only. It does not hide a row."""
    trend = _trend(points)
    if trend == "UP":
        return "TREND UP"
    if trend == "DOWN":
        return "TREND DOWN"
    recent = points[-6:]
    if len(recent) >= 4:
        span = max(point["price"] for point in recent) - min(point["price"] for point in recent)
        kinds = [point["kind"] for point in recent[-4:]]
        flipping = all(kinds[index] != kinds[index - 1] for index in range(1, len(kinds)))
        earlier = points[-12:-6]
        if earlier and flipping:
            wider = max(point["price"] for point in earlier) - min(point["price"] for point in earlier)
            if wider > 0 and span < wider * 0.6:
                return "CHOP"
    return "RANGE"


def _session_name(moment: datetime) -> str:
    hour = moment.hour
    if hour < 7:
        return "ASIA"
    if hour < 12:
        return "LONDON"
    if hour < 21:
        return "NEW_YORK"
    return "LATE"


def _session(stamp: str) -> str:
    moment = _when(stamp)
    if moment is None:
        return "UNKNOWN"
    return _session_name(moment)


def _row(
    chart: str,
    side: str,
    reason: str,
    entry: float,
    stop: float,
    target: float,
    when: str,
    ready: bool,
    *,
    tradeable: bool = True,
) -> dict[str, Any] | None:
    risk = abs(entry - stop)
    reward = (target - entry) if side == "BUY" else (entry - target)
    if risk <= 0 or reward <= 0:
        return None
    ratio = reward / risk
    if ratio < MIN_R:
        return None
    return {
        "chart": chart,
        "side": side,
        "reason": reason,
        "entry": round(entry, 5),
        "stop": round(stop, 5),
        "target": round(target, 5),
        "r": round(ratio, 2),
        "time": when,
        "ready": ready,
        "tradeable": bool(tradeable),
        "session": _session(when),
    }


def _swept(bars: list[dict[str, Any]], level: float, kind: str) -> bool:
    for bar in bars:
        if kind == "HIGH" and _num(bar, "high") > level and _num(bar, "close") < level:
            return True
        if kind == "LOW" and _num(bar, "low") < level and _num(bar, "close") > level:
            return True
    return False


def _aim(side: str, entry: float, stop: float, candidate: float | None) -> float:
    """The next swing when it is at least 0.5R. Otherwise one times the risk."""
    risk = abs(entry - stop)
    if risk <= 0:
        return entry
    one_r = entry + risk if side == "BUY" else entry - risk
    if side == "BUY" and candidate is not None and candidate >= entry + risk * MIN_R:
        return candidate
    if side == "SELL" and candidate is not None and candidate <= entry - risk * MIN_R:
        return candidate
    return one_r


ABOVE = {
    "M1": ("M5", "M15"),
    "M5": ("M15", "H1"),
    "M15": ("H1", "H4"),
    "M30": ("H1", "H4"),
    "H1": ("H4", "D1"),
    "H4": ("D1",),
    "D1": (),
}


def signal_for_chart(chart: str, bars: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The latest structure event on this chart. Below 0.5R is not a signal."""
    if len(bars) < 20:
        return None
    closed = bars[:-1]
    points = swings(closed)
    if len(points) < 4:
        return None
    trend = _trend(points)
    last = closed[-1]
    close = _num(last, "close")
    highs = [point for point in points if point["kind"] == "HIGH"]
    lows = [point for point in points if point["kind"] == "LOW"]
    if not highs or not lows:
        return None
    last_high = highs[-1]
    last_low = lows[-1]
    prior_high = highs[-2]["price"] if len(highs) > 1 else last_high["price"]
    prior_low = lows[-2]["price"] if len(lows) > 1 else last_low["price"]
    earlier = closed[-8:-1]

    swept_high = _num(last, "high") > last_high["price"] and close < last_high["price"]
    swept_low = _num(last, "low") < last_low["price"] and close > last_low["price"]
    if swept_high:
        stop = _num(last, "high")
        return _row(chart, "SELL", "SWEEP", close, stop, _aim("SELL", close, stop, last_low["price"]), _time(last), True)
    if swept_low:
        stop = _num(last, "low")
        return _row(chart, "BUY", "SWEEP", close, stop, _aim("BUY", close, stop, last_high["price"]), _time(last), True)

    if trend == "UP" and close < last_low["price"] and _swept(earlier, last_low["price"], "LOW"):
        stop = _num(last, "high")
        return _row(chart, "SELL", "MSS", close, stop, _aim("SELL", close, stop, prior_low), _time(last), True)
    if trend == "DOWN" and close > last_high["price"] and _swept(earlier, last_high["price"], "HIGH"):
        stop = _num(last, "low")
        return _row(chart, "BUY", "MSS", close, stop, _aim("BUY", close, stop, prior_high), _time(last), True)

    if trend == "UP" and close > last_high["price"]:
        ready = _num(last, "low") <= last_high["price"] and close > last_high["price"]
        entry = last_high["price"]
        stop = last_low["price"]
        return _row(chart, "BUY", "BOS", entry, stop, _aim("BUY", entry, stop, None), _time(last), ready)
    if trend == "DOWN" and close < last_low["price"]:
        ready = _num(last, "high") >= last_low["price"] and close < last_low["price"]
        entry = last_low["price"]
        stop = last_high["price"]
        return _row(chart, "SELL", "BOS", entry, stop, _aim("SELL", entry, stop, None), _time(last), ready)
    if trend == "UP" and close < last_low["price"]:
        stop = last_high["price"]
        return _row(chart, "SELL", "CHoCH", close, stop, _aim("SELL", close, stop, prior_low), _time(last), True)
    if trend == "DOWN" and close > last_high["price"]:
        stop = last_low["price"]
        return _row(chart, "BUY", "CHoCH", close, stop, _aim("BUY", close, stop, prior_high), _time(last), True)
    if trend == "RANGE":
        span = last_high["price"] - last_low["price"]
        if span <= 0:
            return None
        if close >= last_high["price"] - span * 0.2:
            return _row(
                chart, "SELL", "RANGE", last_high["price"], last_high["price"] + span * 0.1,
                last_low["price"], _time(last), close >= last_high["price"],
            )
        if close <= last_low["price"] + span * 0.2:
            return _row(
                chart, "BUY", "RANGE", last_low["price"], last_low["price"] - span * 0.1,
                last_high["price"], _time(last), close <= last_low["price"],
            )
    return None


def session_levels(bars: list[dict[str, Any]]) -> dict[str, Any]:
    """Today's session highs and lows, plus yesterday. Lines only."""
    parsed: list[tuple[datetime, dict[str, Any]]] = []
    for bar in bars:
        moment = _when(_time(bar))
        if moment is not None:
            parsed.append((moment, bar))
    if not parsed:
        return {"current": "UNKNOWN", "levels": []}
    latest = parsed[-1][0]
    today = latest.date()
    yesterday = today - timedelta(days=1)
    buckets: dict[str, list[dict[str, Any]]] = {}
    yday: list[dict[str, Any]] = []
    for moment, bar in parsed:
        if moment.date() == yesterday:
            yday.append(bar)
        elif moment.date() == today:
            buckets.setdefault(_session_name(moment), []).append(bar)
    levels = []
    if yday:
        levels.append({
            "name": "YESTERDAY",
            "high": max(_num(bar, "high") for bar in yday),
            "low": min(_num(bar, "low") for bar in yday),
        })
    for name in ("ASIA", "LONDON", "NEW_YORK", "LATE"):
        group = buckets.get(name) or []
        if not group:
            continue
        levels.append({
            "name": name,
            "high": max(_num(bar, "high") for bar in group),
            "low": min(_num(bar, "low") for bar in group),
        })
    return {"current": _session_name(latest), "levels": levels}


def _tight(bars: list[dict[str, Any]]) -> bool:
    if len(bars) < 16:
        return False
    recent = bars[-8:]
    earlier = bars[-16:-8]
    recent_span = max(_num(bar, "high") for bar in recent) - min(_num(bar, "low") for bar in recent)
    earlier_span = max(_num(bar, "high") for bar in earlier) - min(_num(bar, "low") for bar in earlier)
    return earlier_span > 0 and recent_span <= earlier_span * 0.7


def breakout_watch(chart: str, bars: list[dict[str, Any]], levels: dict[str, Any]) -> dict[str, Any] | None:
    """A tight range pressing the session extreme. Through the high is a buy."""
    closed = bars[:-1]
    if len(closed) < 17:
        return None
    current = next((level for level in levels.get("levels") or [] if level["name"] == levels.get("current")), None)
    if current is None:
        return None
    span = float(current["high"]) - float(current["low"])
    if span <= 0 or not _tight(closed[:-1]):
        return None
    last = closed[-1]
    close = _num(last, "close")
    near = span * 0.15
    stop = _num(last, "low") if close >= float(current["high"]) - near else _num(last, "high")
    if close > float(current["high"]):
        risk = abs(float(current["high"]) - stop)
        row = _row(chart, "BUY", "BOS", float(current["high"]), stop, float(current["high"]) + risk, _time(last), True)
        return row
    if close < float(current["low"]):
        risk = abs(stop - float(current["low"]))
        row = _row(chart, "SELL", "BOS", float(current["low"]), stop, float(current["low"]) - risk, _time(last), True)
        return row
    if float(current["high"]) - close <= near and _num(last, "high") <= float(current["high"]):
        return {
            "chart": chart, "side": "BUY", "reason": "POTENTIAL", "ready": False, "tradeable": False,
            "entry": None, "stop": None, "target": None, "r": None, "time": _time(last),
            "session": levels.get("current"),
            "note": "POTENTIAL BUY. The range is tight and price is pressing the session high. The candle has not closed through.",
        }
    if close - float(current["low"]) <= near and _num(last, "low") >= float(current["low"]):
        return {
            "chart": chart, "side": "SELL", "reason": "POTENTIAL", "ready": False, "tradeable": False,
            "entry": None, "stop": None, "target": None, "r": None, "time": _time(last),
            "session": levels.get("current"),
            "note": "POTENTIAL SELL. The range is tight and price is pressing the session low. The candle has not closed through.",
        }
    return None


def pair_flow(symbol: str, book: dict[str, Any] | None, ready: bool) -> tuple[str, str]:
    """The pair state. No price in the file, so this never says the book is at the entry."""
    book = book or {}
    if not ready:
        return "WAIT", "The candle has not closed back yet."
    delta = book.get("delta_5s")
    ice = book.get("iceberg")
    if not (isinstance(ice, dict) and ice.get("price") is not None) and book.get("iceberg_refresh"):
        return "ICEBERG SOMEWHERE", "An iceberg flag is on for this pair. The file has no price, so this is not an entry."
    if book.get("size_pulled"):
        return "PULLED", "Orders were pulled on this pair. The file does not say at which price."
    if book.get("sweep_consumed"):
        return "SWEEP ON THE BOOK", "The book shows a sweep. The file has no price."
    if isinstance(delta, (int, float)) and not isinstance(delta, bool):
        if delta > 0:
            return "BUYERS STEPPING IN", "More buying than selling in the last 5 seconds."
        if delta < 0:
            return "SELLERS STEPPING IN", "More selling than buying in the last 5 seconds."
    if book.get("fresh"):
        return "BOOK LIVE", "The book is live. Nothing is stepping in."
    if symbol not in FLOW_PAIRS:
        return "NO_BOOK", "This pair has no live book. The structure is still shown."
    return "NO_BOOK", str(book.get("reason") or "The live book is not fresh.")


def align_ladder(symbol: str, book: dict[str, Any] | None, bid: float, ask: float) -> dict[str, Any]:
    """Shift a future ladder onto the CFD. An empty file stays empty. Not an entry."""
    book = book or {}
    levels = list(book.get("levels") or [])
    icebergs = list(book.get("icebergs") or [])
    if not levels and not icebergs:
        return {"shown": False, "reason": "NO_LADDER", "levels": [], "icebergs": []}
    try:
        futures = (float(book.get("futures_bid")) + float(book.get("futures_ask"))) / 2.0
    except (TypeError, ValueError):
        return {"shown": False, "reason": "NO_FUTURES_QUOTE", "levels": [], "icebergs": []}
    shift = ((bid + ask) / 2.0) - futures
    if abs(shift) > MAX_BASIS.get(symbol, 0.0):
        return {"shown": False, "reason": "BASIS_TOO_WIDE", "shift": round(shift, 5), "levels": [], "icebergs": []}
    moved_levels = []
    for level in levels:
        try:
            moved_levels.append({
                "price": round(float(level.get("price")) + shift, 5),
                "bid_contracts": level.get("bid_contracts"),
                "ask_contracts": level.get("ask_contracts"),
            })
        except (TypeError, ValueError):
            continue
    moved_ice = []
    for item in icebergs:
        try:
            moved_ice.append({
                "side": str(item.get("side") or ""),
                "price": round(float(item.get("price")) + shift, 5),
                "executed": item.get("executed"),
                "hidden": item.get("hidden"),
                "shown": item.get("shown"),
            })
        except (TypeError, ValueError):
            continue
    return {
        "shown": bool(moved_levels or moved_ice),
        "reason": "ALIGNED",
        "shift": round(shift, 5),
        "levels": moved_levels[:40],
        "icebergs": moved_ice[:8],
    }


def _closed(bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return bars[:-1] if len(bars) > 1 else []


def _ends(bars: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    closed = _closed(bars)
    if len(closed) < 20:
        return [], [], []
    points = swings(closed)
    highs = [point for point in points if point["kind"] == "HIGH"]
    lows = [point for point in points if point["kind"] == "LOW"]
    return points, highs, lows


def _nearest(side: str, entry: float, prices: list[float]) -> float | None:
    if side == "BUY":
        above = [price for price in prices if price > entry]
        return min(above) if above else None
    below = [price for price in prices if price < entry]
    return max(below) if below else None


def _offer(
    chart: str,
    side: str,
    reason: str,
    entry: float,
    stop: float,
    target: float | None,
    when: str,
    spread: float,
    symbol: str,
    *,
    wick_limit: bool,
) -> dict[str, Any]:
    """Show the R that is on offer. The button exists only at 1.5R with a stop the spread can live behind."""
    risk = abs(entry - stop)
    reward = None if target is None else ((target - entry) if side == "BUY" else (entry - target))
    notes: list[str] = []
    tradeable = True
    ratio = None
    if risk <= 0 or reward is None or reward <= 0:
        tradeable = False
        notes.append("No next level in the trade direction, so this is not an order.")
    else:
        ratio = reward / risk
        if ratio < TRADE_R:
            tradeable = False
            notes.append(f"On offer {ratio:.2f}R. Below {TRADE_R:.1f}R is shown, not sent.")
    if wick_limit and risk > float(MAX_WICK.get(symbol, risk or 0.0)):
        tradeable = False
        notes.append("The 1-minute wick is wider than this pair allows.")
    if spread > 0 and risk > 0 and spread > risk * 0.1 + 1e-9:
        tradeable = False
        notes.append("The spread is more than a tenth of the stop.")
    if tradeable:
        notes.append("Manual entry. Nothing is sent until TRADE is pressed.")
    return {
        "chart": chart,
        "side": side,
        "reason": reason,
        "entry": round(entry, 5),
        "stop": round(stop, 5),
        "target": None if target is None or reward is None or reward <= 0 else round(target, 5),
        "r": None if ratio is None else round(ratio, 2),
        "time": when,
        "ready": True,
        "tradeable": tradeable,
        "state": "READY" if tradeable else "SHOWN",
        "session": _session(when),
        "note": " ".join(notes),
        "spread_eats_target": bool(spread > 0 and risk > 0 and spread > risk * 0.1 + 1e-9),
    }


def _pullback(symbol: str, m15: list[dict[str, Any]], m5: list[dict[str, Any]], m1: list[dict[str, Any]], spread: float) -> dict[str, Any] | None:
    points, highs, lows = _ends(m15)
    if len(highs) < 2 or len(lows) < 2:
        return None
    trend = _trend(points)
    if trend not in ("UP", "DOWN"):
        return None
    _, highs5, lows5 = _ends(m5)
    closed = _closed(m1)
    if not highs5 or not lows5 or not closed:
        return None
    last = closed[-1]
    if trend == "UP":
        dip = lows5[-1]
        if highs5[-1]["index"] > dip["index"]:
            return None
        if not (_num(last, "low") <= dip["price"] and _num(last, "close") > dip["price"] and _num(last, "close") > _num(last, "open")):
            return None
        target = _nearest("BUY", _num(last, "close"), [point["price"] for point in highs5 + highs])
        return _offer("M15", "BUY", "PULLBACK", _num(last, "close"), _num(last, "low"), target, _time(last), spread, symbol, wick_limit=True)
    peak = highs5[-1]
    if lows5[-1]["index"] > peak["index"]:
        return None
    if not (_num(last, "high") >= peak["price"] and _num(last, "close") < peak["price"] and _num(last, "close") < _num(last, "open")):
        return None
    target = _nearest("SELL", _num(last, "close"), [point["price"] for point in lows5 + lows])
    return _offer("M15", "SELL", "PULLBACK", _num(last, "close"), _num(last, "high"), target, _time(last), spread, symbol, wick_limit=True)


def _break_side(closed: list[dict[str, Any]], level: float, side: str) -> bool:
    """A close through the level, then the next close still outside. A wick back inside is not this."""
    for index in range(len(closed) - 2, max(len(closed) - 6, 1), -1):
        previous = closed[index - 1]
        broke = closed[index]
        held = closed[index + 1]
        if side == "BUY":
            through = _num(previous, "close") <= level and _num(broke, "close") > level and _num(held, "close") > level
        else:
            through = _num(previous, "close") >= level and _num(broke, "close") < level and _num(held, "close") < level
        if through and index >= len(closed) - 4:
            return True
    return False


def _break(symbol: str, m15: list[dict[str, Any]], m1: list[dict[str, Any]], spread: float) -> dict[str, Any] | None:
    closed15 = _closed(m15)
    _, highs, lows = _ends(m15)
    closed1 = _closed(m1)
    if len(closed15) < 6 or not closed1 or not (highs or lows):
        return None
    last = closed1[-1]
    if highs and _break_side(closed15, highs[-1]["price"], "BUY") and _num(last, "low") <= highs[-1]["price"] and _num(last, "close") > highs[-1]["price"]:
        level = highs[-1]["price"]
        target = _nearest("BUY", _num(last, "close"), [point["price"] for point in highs if point["price"] > level])
        return _offer("M15", "BUY", "BREAK", _num(last, "close"), _num(last, "low"), target, _time(last), spread, symbol, wick_limit=True)
    if lows and _break_side(closed15, lows[-1]["price"], "SELL") and _num(last, "high") >= lows[-1]["price"] and _num(last, "close") < lows[-1]["price"]:
        level = lows[-1]["price"]
        target = _nearest("SELL", _num(last, "close"), [point["price"] for point in lows if point["price"] < level])
        return _offer("M15", "SELL", "BREAK", _num(last, "close"), _num(last, "high"), target, _time(last), spread, symbol, wick_limit=True)
    return None


def _range(symbol: str, m15: list[dict[str, Any]], m1: list[dict[str, Any]], spread: float) -> dict[str, Any] | None:
    points, highs, lows = _ends(m15)
    if not points or _trend(points) != "RANGE" or not highs or not lows:
        return None
    high = highs[-1]["price"]
    low = lows[-1]["price"]
    span = high - low
    closed = _closed(m1)
    if span <= 0 or not closed:
        return None
    last = closed[-1]
    if _num(last, "low") <= low + span * 0.1 and _num(last, "close") > low and _num(last, "close") >= _num(last, "open"):
        return _offer("M15", "BUY", "RANGE", _num(last, "close"), _num(last, "low"), high, _time(last), spread, symbol, wick_limit=True)
    if _num(last, "high") >= high - span * 0.1 and _num(last, "close") < high and _num(last, "close") <= _num(last, "open"):
        return _offer("M15", "SELL", "RANGE", _num(last, "close"), _num(last, "high"), low, _time(last), spread, symbol, wick_limit=True)
    return None


def _m3(bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Three-minute candles built from the one-minute feed. The broker has no 3-minute chart."""
    groups: list[dict[str, Any]] = []
    bucket: dict[str, Any] | None = None
    key = ""
    for bar in _closed(bars):
        moment = _when(_time(bar))
        if moment is None:
            continue
        stamp = moment.replace(minute=(moment.minute // 3) * 3, second=0, microsecond=0)
        stamp_key = stamp.isoformat()
        if bucket is None or stamp_key != key:
            if bucket is not None:
                groups.append(bucket)
            key = stamp_key
            bucket = {
                "time": stamp_key,
                "open": _num(bar, "open"),
                "high": _num(bar, "high"),
                "low": _num(bar, "low"),
                "close": _num(bar, "close"),
            }
        else:
            bucket["high"] = max(float(bucket["high"]), _num(bar, "high"))
            bucket["low"] = min(float(bucket["low"]), _num(bar, "low"))
            bucket["close"] = _num(bar, "close")
    if bucket is not None:
        groups.append(bucket)
    return groups


def _choch(symbol: str, m15: list[dict[str, Any]], m1: list[dict[str, Any]], spread: float) -> dict[str, Any] | None:
    """15-minute body close through a swing, then a 3-minute order block retest and a 3-minute sweep."""
    closed15 = _closed(m15)
    _, highs, lows = _ends(m15)
    three = _m3(m1)
    if len(closed15) < 6 or len(three) < 8 or not highs or not lows:
        return None
    last15 = closed15[-1]
    body_down = _num(last15, "close") < _num(last15, "open") and _num(last15, "close") < lows[-1]["price"]
    body_up = _num(last15, "close") > _num(last15, "open") and _num(last15, "close") > highs[-1]["price"]
    if not body_down and not body_up:
        return None
    side = "SELL" if body_down else "BUY"
    level = lows[-1]["price"] if side == "SELL" else highs[-1]["price"]
    # The order block is the last 3-minute candle in the old direction, before the close through.
    opposite = [bar for bar in three if (_num(bar, "close") > _num(bar, "open") if side == "SELL" else _num(bar, "close") < _num(bar, "open"))]
    if not opposite:
        return None
    block = opposite[-1]
    block_high = _num(block, "high")
    block_low = _num(block, "low")
    later = [bar for bar in three if _time(bar) > _time(block)]
    if len(later) < 2:
        return None
    retested = False
    for bar in later[:-1]:
        touched = _num(bar, "high") >= block_low and _num(bar, "low") <= block_high
        rejected = _num(bar, "close") < block_low if side == "SELL" else _num(bar, "close") > block_high
        if touched and rejected:
            retested = True
            break
    if not retested:
        return None
    sweep = later[-1]
    if side == "SELL":
        swept = _num(sweep, "high") > block_high and _num(sweep, "close") < block_high and _num(sweep, "close") < _num(sweep, "open")
        if not swept:
            return None
        target = _nearest("SELL", _num(sweep, "close"), [point["price"] for point in lows if point["price"] < level])
        return _offer("M15", "SELL", "CHOCH", _num(sweep, "close"), _num(sweep, "high"), target, _time(sweep), spread, symbol, wick_limit=True)
    swept = _num(sweep, "low") < block_low and _num(sweep, "close") > block_low and _num(sweep, "close") > _num(sweep, "open")
    if not swept:
        return None
    target = _nearest("BUY", _num(sweep, "close"), [point["price"] for point in highs if point["price"] > level])
    return _offer("M15", "BUY", "CHOCH", _num(sweep, "close"), _num(sweep, "low"), target, _time(sweep), spread, symbol, wick_limit=True)


def _intraday(symbol: str, bars_by_chart: dict[str, list[dict[str, Any]]], spread: float) -> dict[str, Any] | None:
    m15 = bars_by_chart.get("M15") or []
    m5 = bars_by_chart.get("M5") or []
    m1 = bars_by_chart.get("M1") or []
    return _choch(symbol, m15, m1, spread) or _break(symbol, m15, m1, spread) or _pullback(symbol, m15, m5, m1, spread) or _range(symbol, m15, m1, spread)


def _swing(symbol: str, bars_by_chart: dict[str, list[dict[str, Any]]], spread: float) -> dict[str, Any] | None:
    """The same pullback or break, read on the 4-hour chart. The stop is the 4-hour swing."""
    h4 = bars_by_chart.get("H4") or []
    h1 = bars_by_chart.get("H1") or []
    points, highs, lows = _ends(h4)
    closed_h4 = _closed(h4)
    closed_h1 = _closed(h1)
    if len(highs) < 2 or len(lows) < 2 or len(closed_h4) < 6 or not closed_h1:
        return None
    last = closed_h1[-1]
    trend = _trend(points)
    if _break_side(closed_h4, highs[-1]["price"], "BUY"):
        entry = _num(closed_h4[-1], "close")
        stop = min(_num(bar, "low") for bar in closed_h4[-2:])
        target = _nearest("BUY", entry, [point["price"] for point in highs if point["price"] > highs[-1]["price"]])
        row = _offer("H4", "BUY", "SWING", entry, stop, target, _time(closed_h4[-1]), spread, symbol, wick_limit=False)
        if row["target"] is not None:
            return row
    if _break_side(closed_h4, lows[-1]["price"], "SELL"):
        entry = _num(closed_h4[-1], "close")
        stop = max(_num(bar, "high") for bar in closed_h4[-2:])
        target = _nearest("SELL", entry, [point["price"] for point in lows if point["price"] < lows[-1]["price"]])
        row = _offer("H4", "SELL", "SWING", entry, stop, target, _time(closed_h4[-1]), spread, symbol, wick_limit=False)
        if row["target"] is not None:
            return row
    if trend == "UP" and lows[-1]["index"] > highs[-1]["index"]:
        dip = lows[-1]["price"]
        if _num(last, "low") <= dip and _num(last, "close") > dip and _num(last, "close") > _num(last, "open"):
            target = _nearest("BUY", _num(last, "close"), [point["price"] for point in highs])
            return _offer("H4", "BUY", "SWING", _num(last, "close"), dip, target, _time(last), spread, symbol, wick_limit=False)
    if trend == "DOWN" and highs[-1]["index"] > lows[-1]["index"]:
        peak = highs[-1]["price"]
        if _num(last, "high") >= peak and _num(last, "close") < peak and _num(last, "close") < _num(last, "open"):
            target = _nearest("SELL", _num(last, "close"), [point["price"] for point in lows])
            return _offer("H4", "SELL", "SWING", _num(last, "close"), peak, target, _time(last), spread, symbol, wick_limit=False)
    return None


def _iceberg(symbol: str, bars_by_chart: dict[str, list[dict[str, Any]]], book: dict[str, Any] | None, spread: float) -> dict[str, Any] | None:
    ice = (book or {}).get("iceberg")
    if not isinstance(ice, dict) or ice.get("price") is None:
        return None
    side_name = str(ice.get("side") or "").lower()
    if side_name not in ("bid", "ask"):
        return None
    side = "BUY" if side_name == "bid" else "SELL"
    price = float(ice["price"])
    tick = float(ICE_TICK.get(symbol, 0.0))
    if tick <= 0:
        return None
    stop = price - tick if side == "BUY" else price + tick
    _, highs, lows = _ends(bars_by_chart.get("M15") or [])
    _, highs5, lows5 = _ends(bars_by_chart.get("M5") or [])
    pool = [point["price"] for point in (highs + highs5 if side == "BUY" else lows + lows5)]
    target = _nearest(side, price, pool)
    stamp = ice.get("time")
    when = ""
    try:
        when = datetime.fromtimestamp(float(stamp), timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        when = datetime.now(timezone.utc).isoformat()
    row = _offer("M1", side, "ICEBERG", price, stop, target, when, spread, symbol, wick_limit=False)
    if not (book or {}).get("fresh"):
        row["tradeable"] = False
        row["state"] = "SHOWN"
        row["note"] = "The iceberg file is stale. " + str(row.get("note") or "")
    if int(ice.get("refills") or 0) < 1:
        row["tradeable"] = False
        row["state"] = "SHOWN"
        row["note"] = "The size has not refilled, so this is not an iceberg yet. " + str(row.get("note") or "")
    return row


def _wait(chart: str, note: str, trend: str) -> dict[str, Any]:
    return {
        "chart": chart, "side": "", "reason": "NO_SIGNAL", "r": None,
        "decision": "—", "note": note, "state": "WAIT", "trend": trend, "tradeable": False,
    }


def _live_stop(row: dict[str, Any], bid: float | None, ask: float | None) -> None:
    """A market order uses the live price. A stop already through that price cannot be sent."""
    if not row.get("side") or row.get("stop") is None:
        return
    stop = float(row["stop"])
    target = row.get("target")
    if row["side"] == "SELL":
        dead = ask is not None and stop <= float(ask)
        passed = bid is not None and target is not None and float(target) >= float(bid)
    else:
        dead = bid is not None and stop >= float(bid)
        passed = ask is not None and target is not None and float(target) <= float(ask)
    if dead or passed:
        row["tradeable"] = False
        row["state"] = "SHOWN"
        reason = "Price is already through this stop, so the broker will not take it." if dead else "Price is already through this target."
        row["note"] = reason + " " + str(row.get("note") or "")


def build_rows(
    symbol: str,
    bars_by_chart: dict[str, list[dict[str, Any]]],
    book: dict[str, Any] | None,
    spread: float,
    levels: dict[str, Any],
    bid: float | None = None,
    ask: float | None = None,
) -> list[dict[str, Any]]:
    """One manual row on M15, one swing on H4, and the iceberg on M1 when the file has a price."""
    del levels
    intraday = _intraday(symbol, bars_by_chart, spread)
    swing = _swing(symbol, bars_by_chart, spread)
    iceberg = _iceberg(symbol, bars_by_chart, book, spread)
    notes = {
        "M1": "The 1-minute chart is the fill. No iceberg price in the file.",
        "M5": "No separate signal. The 5-minute chart is only the dip.",
        "M15": "No pullback, break, or range on the 15-minute chart.",
        "M30": "No separate signal.",
        "H1": "No separate signal. The 1-hour chart is not an entry.",
        "H4": "No 4-hour swing.",
        "D1": "No separate signal.",
    }
    rows: list[dict[str, Any]] = []
    for chart in CHARTS:
        bars = bars_by_chart.get(chart) or []
        closed = bars[:-1]
        points = swings(closed) if len(closed) >= 20 else []
        trend = market_state(points) if points else "RANGE"
        chosen = {"M15": intraday, "H4": swing, "M1": iceberg}.get(chart)
        if chosen is None:
            row = _wait(chart, notes[chart], trend)
        else:
            row = dict(chosen)
            row["trend"] = trend
            decision, flow_note = pair_flow(symbol, book, True)
            if row["reason"] == "ICEBERG":
                decision = "ICEBERG"
            row["decision"] = decision
            if flow_note and row["reason"] != "ICEBERG":
                row["note"] = (str(row.get("note") or "") + " " + flow_note).strip()
            row["spread"] = spread
            _live_stop(row, bid, ask)
        rows.append(row)
    _retain(symbol, rows, bars_by_chart)
    by_chart = {row["chart"]: row for row in rows}
    for row in rows:
        if not row.get("side"):
            row["higher"] = "—"
            row["next_vote"] = "NONE"
            continue
        labels = []
        vote = "NONE"
        first = True
        for chart in ABOVE.get(str(row.get("chart")), ()):
            state_word = str((by_chart.get(chart) or {}).get("trend") or (by_chart.get(chart) or {}).get("state") or "")
            if state_word == "TREND UP":
                word = "WITH" if row["side"] == "BUY" else "AGAINST"
            elif state_word == "TREND DOWN":
                word = "WITH" if row["side"] == "SELL" else "AGAINST"
            else:
                continue
            labels.append(word + " " + chart)
            if first:
                vote = word
                first = False
        row["higher"] = ", ".join(labels) or "—"
        row["next_vote"] = vote
        _live_stop(row, bid, ask)
    return rows


def _retain(symbol: str, rows: list[dict[str, Any]], bars_by_chart: dict[str, list[dict[str, Any]]]) -> None:
    """Keep a priced signal until its stop or its target. A quiet candle does not erase it."""
    state = _load_state()
    active: dict[str, dict[str, Any]] = state.setdefault("active", {})
    changed = False
    for row in rows:
        chart = str(row.get("chart"))
        key = symbol + "|" + chart
        if row.get("reason") in MANUAL and row.get("entry") is not None:
            if row.get("tradeable"):
                active[key] = {**row, "symbol": symbol}
            else:
                active.pop(key, None)
            changed = True
            continue
        held = active.get(key)
        if not held or held.get("reason") not in MANUAL:
            if held:
                active.pop(key, None)
                changed = True
            continue
        result, _be, mfe = _score_path(held, bars_by_chart.get(chart) or [], float(BE_MOVE.get(symbol, 0.0)))
        if result in ("WIN", "LOSS"):
            active.pop(key, None)
            changed = True
            continue
        note = "Held until the stop or the target."
        row.clear()
        row.update(held)
        row["mfe"] = mfe
        row["tradeable"] = bool(held.get("tradeable")) and float(held.get("r") or 0) >= TRADE_R
        row["state"] = "READY" if row["tradeable"] else "SHOWN"
        row["note"] = note
        row["decision"] = held.get("decision") or "HELD"
    if changed:
        _save_state(state)


def liquidity(levels: dict[str, Any], bars_by_chart: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Pools the candles can prove. Not the resting book."""
    pools: list[dict[str, Any]] = []
    names = [str(level.get("name")) for level in levels.get("levels") or []]
    current = str(levels.get("current") or "")
    previous = ""
    order = ["ASIA", "LONDON", "NEW_YORK", "LATE"]
    if current in order:
        index = order.index(current)
        previous = order[index - 1] if index else "YESTERDAY"
    for level in levels.get("levels") or []:
        name = str(level.get("name"))
        label = "PREVIOUS " + name if name == previous else name
        pools.append({"name": label + " HIGH", "price": float(level["high"]), "kind": "HIGH"})
        pools.append({"name": label + " LOW", "price": float(level["low"]), "kind": "LOW"})
    for chart in ("H4", "D1"):
        bars = bars_by_chart.get(chart) or []
        if len(bars) < 20:
            continue
        points = swings(bars[:-1])
        highs = [point for point in points if point["kind"] == "HIGH"]
        lows = [point for point in points if point["kind"] == "LOW"]
        if highs:
            pools.append({"name": chart + " SWING HIGH", "price": float(highs[-1]["price"]), "kind": "HIGH"})
        if lows:
            pools.append({"name": chart + " SWING LOW", "price": float(lows[-1]["price"]), "kind": "LOW"})
    return pools


def reaction(bars: list[dict[str, Any]], pools: list[dict[str, Any]]) -> dict[str, Any]:
    """A wick through a pool that closes back inside is taken. The next pool is only a target."""
    closed = bars[:-1] if len(bars) > 1 else []
    if not closed or not pools:
        return {"taken": None, "next": None}
    last = closed[-1]
    close = _num(last, "close")
    taken = None
    for pool in pools:
        price = float(pool["price"])
        if pool["kind"] == "HIGH" and _num(last, "high") > price and close < price:
            if taken is None or abs(price - close) < abs(float(taken["price"]) - close):
                taken = pool
        if pool["kind"] == "LOW" and _num(last, "low") < price and close > price:
            if taken is None or abs(price - close) < abs(float(taken["price"]) - close):
                taken = pool
    nxt = None
    if taken and taken["kind"] == "HIGH":
        below = [pool for pool in pools if float(pool["price"]) < close]
        nxt = max(below, key=lambda pool: float(pool["price"])) if below else None
    elif taken and taken["kind"] == "LOW":
        above = [pool for pool in pools if float(pool["price"]) > close]
        nxt = min(above, key=lambda pool: float(pool["price"])) if above else None
    return {"taken": taken, "next": nxt}


def _load_state() -> dict[str, Any]:
    try:
        state = json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        state = {}
    state.setdefault("if_open", {})
    state.setdefault("taken_open", {})
    state.setdefault("if_taken", {})
    state.setdefault("taken", {})
    state.setdefault("active", {})
    state.setdefault("alignment", {})
    return state


def _save_state(state: dict[str, Any]) -> None:
    STATE.write_text(json.dumps(state), encoding="utf-8")


def _append(row: dict[str, Any]) -> None:
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")


def _empty_bucket() -> dict[str, int]:
    return {"wins": 0, "losses": 0, "expired": 0, "open": 0, "be_wins": 0, "be_scratches": 0, "be_losses": 0}


def _score_path(row: dict[str, Any], bars: list[dict[str, Any]], be_move: float) -> tuple[str, str, float]:
    later = [bar for bar in bars if _time(bar) > str(row.get("time"))]
    entry = float(row["entry"])
    stop = float(row["stop"])
    target = float(row["target"])
    buy = row["side"] == "BUY"
    mfe = 0.0
    armed = False
    result = ""
    be_result = ""
    for bar in later:
        favorable = (_num(bar, "high") - entry) if buy else (entry - _num(bar, "low"))
        mfe = max(mfe, favorable)
        hit_stop = _num(bar, "low") <= stop if buy else _num(bar, "high") >= stop
        hit_target = _num(bar, "high") >= target if buy else _num(bar, "low") <= target
        if hit_stop:
            result = "LOSS"
            if not armed:
                be_result = "LOSS"
            break
        if not armed and favorable >= be_move:
            armed = True
        if armed:
            back = _num(bar, "low") <= entry if buy else _num(bar, "high") >= entry
            if back and favorable < (target - entry if buy else entry - target):
                be_result = "SCRATCH"
        if hit_target:
            result = "WIN"
            if not be_result:
                be_result = "WIN"
            break
    if not result and len(later) >= 40:
        result = "EXPIRED"
        if not be_result:
            be_result = "EXPIRED"
    return result, be_result, round(mfe, 5)


def _apply(bucket: dict[str, int], result: str, be_result: str) -> None:
    bucket["open"] = max(0, int(bucket.get("open") or 0) - 1)
    if result == "WIN":
        bucket["wins"] = int(bucket.get("wins") or 0) + 1
    elif result == "LOSS":
        bucket["losses"] = int(bucket.get("losses") or 0) + 1
    elif result == "EXPIRED":
        bucket["expired"] = int(bucket.get("expired") or 0) + 1
    if be_result == "WIN":
        bucket["be_wins"] = int(bucket.get("be_wins") or 0) + 1
    elif be_result == "SCRATCH":
        bucket["be_scratches"] = int(bucket.get("be_scratches") or 0) + 1
    elif be_result == "LOSS":
        bucket["be_losses"] = int(bucket.get("be_losses") or 0) + 1


def _finish(state: dict[str, Any], store: str, summary_name: str, bars_by_chart: dict[str, list[dict[str, Any]]], symbol: str, now: str) -> None:
    summary: dict[str, dict[str, int]] = state.setdefault(summary_name, {})
    open_rows: dict[str, dict[str, Any]] = state.setdefault(store, {})
    done = []
    for key, row in open_rows.items():
        if str(row.get("symbol")) != symbol:
            continue
        result, be_result, mfe = _score_path(row, bars_by_chart.get(str(row.get("chart"))) or [], float(BE_MOVE.get(symbol, 0.0)))
        if not result:
            row["mfe"] = mfe
            continue
        chart = str(row.get("chart"))
        bucket = summary.setdefault(chart, _empty_bucket())
        _apply(bucket, result, be_result)
        vote = str(row.get("next_vote") or "NONE")
        if vote not in ("WITH", "AGAINST"):
            vote = "NONE"
        align = state.setdefault("alignment", {}).setdefault(vote, _empty_bucket())
        if result == "WIN":
            align["wins"] = int(align.get("wins") or 0) + 1
        elif result == "LOSS":
            align["losses"] = int(align.get("losses") or 0) + 1
        _append({
            "event": result, "book": summary_name, "symbol": symbol, "at": now,
            "chart": chart, "reason": row.get("reason"), "side": row.get("side"),
            "r": row.get("r"), "be": be_result, "mfe": mfe, "next_vote": vote,
        })
        done.append(key)
    for key in done:
        open_rows.pop(key, None)


def record(symbol: str, rows: list[dict[str, Any]], bars_by_chart: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Score a sent trade for real. Score every other ready row only as IF TAKEN."""
    state = _load_state()
    if_open: dict[str, dict[str, Any]] = state.setdefault("if_open", {})
    if_summary: dict[str, dict[str, int]] = state.setdefault("if_taken", {})
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    for row in rows:
        if not row.get("side") or not row.get("tradeable"):
            continue
        if row.get("entry") is None:
            continue
        key = "|".join((symbol, row["chart"], row["reason"], row["side"], str(row["entry"]), str(row["time"])))
        if key in if_open:
            continue
        if_open[key] = {**row, "symbol": symbol, "opened": now}
        bucket = if_summary.setdefault(row["chart"], _empty_bucket())
        bucket["open"] = int(bucket.get("open") or 0) + 1
        _append({"event": "IF_TAKEN", "symbol": symbol, "at": now, **{k: row[k] for k in row if k != "note"}})
    _finish(state, "if_open", "if_taken", bars_by_chart, symbol, now)
    _finish(state, "taken_open", "taken", bars_by_chart, symbol, now)
    _save_state(state)
    open_detail = [
        {
            "chart": row.get("chart"),
            "side": row.get("side"),
            "reason": row.get("reason"),
            "mfe": row.get("mfe"),
            "entry": row.get("entry"),
            "next_vote": row.get("next_vote") or "NONE",
        }
        for row in (state.get("if_open") or {}).values()
        if str(row.get("symbol")) == symbol
    ]
    return {
        "taken": state.get("taken") or {},
        "if_taken": state.get("if_taken") or {},
        "alignment": state.get("alignment") or {},
        "open": open_detail,
    }


def mark_taken(row: dict[str, Any]) -> dict[str, Any]:
    """A broker-accepted order. This is the only row that counts as taken."""
    symbol = str(row.get("symbol") or "").upper()
    if symbol not in PAIRS or row.get("side") not in ("BUY", "SELL"):
        raise ValueError("unknown pair or side")
    if row.get("entry") is None or row.get("stop") is None or row.get("target") is None:
        raise ValueError("missing prices")
    state = _load_state()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    key = "|".join((symbol, str(row.get("chart")), str(row.get("reason")), str(row.get("side")), str(row.get("entry")), str(row.get("time")), now))
    state.setdefault("taken_open", {})[key] = {
        "symbol": symbol,
        "chart": row.get("chart"),
        "reason": row.get("reason"),
        "side": row.get("side"),
        "entry": float(row["entry"]),
        "stop": float(row["stop"]),
        "target": float(row["target"]),
        "r": row.get("r"),
        "time": str(row.get("time") or now),
        "opened": now,
    }
    bucket = state.setdefault("taken", {}).setdefault(str(row.get("chart")), _empty_bucket())
    bucket["open"] = int(bucket.get("open") or 0) + 1
    _append({"event": "TAKEN", "symbol": symbol, "at": now, "chart": row.get("chart"), "side": row.get("side"), "reason": row.get("reason")})
    _save_state(state)
    return {"taken": state.get("taken") or {}, "if_taken": state.get("if_taken") or {}}
