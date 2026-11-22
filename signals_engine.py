"""Confirmed signals. A zone is touched only after a 1-minute close. The stop has to clear the spread."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

PAIRS = ("XAUUSD", "XAGUSD", "NAS100", "BTCUSD", "EURUSD", "USDJPY", "WTI", "NG-C", "GER40")
CHARTS = ("M1", "M5", "M15", "M30", "H1", "H4", "D1")
ROWS = ("ICEBERG", "INTRADAY", "INTERDAY", "SCALP", "SWING")
MIN_R = 0.5
TRADE_R = 0.5
MANUAL = {"PULLBACK", "BREAK", "RANGE", "SWING", "ICEBERG", "CHOCH", "SCALP"}
# One price step. Five of these is close enough to bank the first target.
PIP = {
    "XAUUSD": 0.1,
    "XAGUSD": 0.01,
    "NAS100": 1.0,
    "WTI": 0.01,
    "EURUSD": 0.0001,
    "USDJPY": 0.01,
    "BTCUSD": 10.0,
    "NG-C": 0.01,
    "GER40": 1.0,
}
# A gold stop inside this is not a button, except on the point-of-control scalp.
GOLD_MIN_STOP = 2.0
# A 1-minute wick wider than this is not a scalp. Price units, not pips.
MAX_WICK = {
    "XAUUSD": 8.0,
    "XAGUSD": 0.20,
    "NAS100": 80.0,
    "WTI": 0.40,
    "EURUSD": 0.0012,
    "USDJPY": 0.20,
    "BTCUSD": 200.0,
    "NG-C": 0.10,
    "GER40": 80.0,
}
# Gold and oil stop just past the iceberg. Nasdaq is wider because one tick is run through.
ICE_ONLY = {"XAUUSD", "WTI", "NAS100", "NG-C"}
ICE_STOP = {"XAUUSD": 3.0, "WTI": 0.30, "NAS100": 20.0, "NG-C": 0.05}
ICE_TICK = {
    "XAUUSD": 0.1,
    "XAGUSD": 0.005,
    "NAS100": 1.0,
    "WTI": 0.01,
    "EURUSD": 0.0001,
    "USDJPY": 0.01,
    "BTCUSD": 1.0,
    "NG-C": 0.001,
    "GER40": 1.0,
}
WING = 2
LOG = Path("signal_research_v2.jsonl")
STATE = Path("signal_research_state_v2.json")
FLOW_PAIRS = set(PAIRS)
# How far a zone may sit past the value edge and still be that edge. Not five pips on every pair.
EDGE = {
    "XAUUSD": 5.0,
    "XAGUSD": 0.15,
    "NAS100": 25.0,
    "WTI": 0.15,
    "EURUSD": 0.0006,
    "USDJPY": 0.06,
    "BTCUSD": 150.0,
    "NG-C": 0.05,
    "GER40": 25.0,
}
BE_MOVE = {
    "XAUUSD": 2.0,
    "XAGUSD": 0.20,
    "NAS100": 20.0,
    "WTI": 0.20,
    "EURUSD": 0.0020,
    "USDJPY": 0.20,
    "BTCUSD": 20.0,
    "NG-C": 0.05,
    "GER40": 20.0,
}
# A futures price this far from the CFD is not drawn. The gap is measured live.
MAX_BASIS = {
    "XAUUSD": 80.0,
    "XAGUSD": 2.0,
    "NAS100": 80.0,
    "WTI": 5.0,
    "EURUSD": 0.02,
    "USDJPY": 2.0,
    "BTCUSD": 2000.0,
    "NG-C": 0.50,
    "GER40": 250.0,
}
POSITION_NAMES = {
    "XAUUSD": ("XAUUSD", "XAU"),
    "XAGUSD": ("XAGUSD", "XAG"),
    "NAS100": ("NAS100", "NAS", "US100", "USTEC"),
    "BTCUSD": ("BTCUSD", "BTC"),
    "EURUSD": ("EURUSD",),
    "USDJPY": ("USDJPY",),
    "WTI": ("WTI", "USOIL", "USOUSD", "XTIUSD", "XTI", "CL"),
    "NG-C": ("NG-C", "NATGAS", "NGAS"),
    "GER40": ("GER40", "GER30", "DE40", "DAX"),
}
# The file the new study can write. Bitcoin is checked under both names.
FUTURES_ROOTS = {
    "XAUUSD": ("GC",),
    "XAGUSD": ("SI",),
    "NAS100": ("NQ",),
    "WTI": ("CL",),
    "EURUSD": ("6E",),
    "USDJPY": ("6J",),
    "BTCUSD": ("BTC",),
    "NG-C": ("NG",),
    "GER40": ("DAX",),
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
    if not icebergs:
        for item in (book.get("iceberg"), book.get("other")):
            if not isinstance(item, dict) or item.get("price") is None:
                continue
            side_name = str(item.get("side") or "").lower()
            chart_side = "BUY" if side_name in {"bid", "buy"} else "SELL" if side_name in {"ask", "sell"} else ""
            if chart_side:
                icebergs.append({"price": item.get("price"), "side": chart_side, "shown": item.get("bid_size")})
    if not levels and not icebergs:
        return {"shown": False, "reason": "NO_LADDER", "levels": [], "icebergs": []}
    try:
        futures = (float(book.get("futures_bid")) + float(book.get("futures_ask"))) / 2.0
    except (TypeError, ValueError):
        last = book.get("last")
        if isinstance(last, bool) or not isinstance(last, (int, float)) or float(last) <= 0:
            return {"shown": False, "reason": "NO_FUTURES_QUOTE", "levels": [], "icebergs": []}
        futures = float(last)
    if symbol == "USDJPY":
        futures = _yen_spot(futures)
    shift = ((bid + ask) / 2.0) - futures
    if abs(shift) > MAX_BASIS.get(symbol, 0.0):
        return {"shown": False, "reason": "BASIS_TOO_WIDE", "shift": round(shift, 5), "levels": [], "icebergs": []}
    moved_levels = []
    for level in levels:
        try:
            price = float(level.get("price"))
            if symbol == "USDJPY":
                price = _yen_spot(price)
            moved_levels.append({
                "price": round(price + shift, 5),
                "bid_contracts": level.get("bid_contracts"),
                "ask_contracts": level.get("ask_contracts"),
            })
        except (TypeError, ValueError):
            continue
    moved_ice = []
    for item in icebergs:
        try:
            price = float(item.get("price"))
            if symbol == "USDJPY":
                price = _yen_spot(price)
            moved_ice.append({
                "side": str(item.get("side") or ""),
                "price": round(price + shift, 5),
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


def _on_cfd(symbol: str, price: float, book: dict[str, Any], bid: float | None, ask: float | None) -> float | None:
    """Move a futures iceberg onto the CFD. Too wide a gap is not an entry."""
    try:
        futures = float((book or {}).get("last"))
        mid = (float(bid) + float(ask)) / 2.0
    except (TypeError, ValueError):
        return None
    if futures <= 0 or mid <= 0:
        return None
    shift = mid - futures
    if abs(shift) > float(MAX_BASIS.get(symbol, 0.0)):
        return None
    return price + shift


def _iceberg(symbol: str, bars_by_chart: dict[str, list[dict[str, Any]]], book: dict[str, Any] | None, spread: float, bid: float | None = None, ask: float | None = None) -> dict[str, Any] | None:
    if symbol not in ICE_ONLY:
        return None
    ice = (book or {}).get("iceberg")
    if not isinstance(ice, dict) or ice.get("price") is None:
        return None
    side_name = str(ice.get("side") or "").lower()
    if side_name not in ("bid", "ask"):
        return None
    side = "BUY" if side_name == "bid" else "SELL"
    try:
        raw_price = float(ice["price"])
    except (TypeError, ValueError):
        return None
    price = _on_cfd(symbol, raw_price, book or {}, bid, ask)
    if price is None:
        return None
    stop_dist = max(float(ICE_STOP.get(symbol, 0.0)), spread * 10.0 if spread > 0 else 0.0)
    if stop_dist <= 0:
        return None
    stop = price - stop_dist if side == "BUY" else price + stop_dist
    other = (book or {}).get("other") if isinstance((book or {}).get("other"), dict) else None
    target = None
    bank = "No iceberg the other way yet. The first target is 1R, and it banks early when that iceberg prints."
    if other is not None and other.get("price") is not None:
        try:
            other_price = _on_cfd(symbol, float(other["price"]), book or {}, bid, ask)
        except (TypeError, ValueError):
            other_price = None
        if other_price is not None and ((side == "SELL" and other_price < price) or (side == "BUY" and other_price > price)):
            target = other_price
            bank = "The iceberg the other way is the target. Bank there."
    if target is None:
        target = price + stop_dist if side == "BUY" else price - stop_dist
    stamp = ice.get("time")
    when = ""
    try:
        when = datetime.fromtimestamp(float(stamp), timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        when = datetime.now(timezone.utc).isoformat()
    row = _offer("M1", side, "ICEBERG", price, stop, target, when, spread, symbol, wick_limit=False)
    row["note"] = bank + " " + str(row.get("note") or "")
    if not (book or {}).get("fresh"):
        row["tradeable"] = False
        row["state"] = "SHOWN"
        row["note"] = "The iceberg file is stale. " + str(row.get("note") or "")
    return row


def _wait(chart: str, note: str, trend: str) -> dict[str, Any]:
    return {
        "chart": chart, "side": "", "reason": "NO_SIGNAL", "r": None,
        "decision": "—", "note": note, "state": "WAIT", "trend": trend, "tradeable": False,
    }


def _live_stop(row: dict[str, Any], bid: float | None, ask: float | None, symbol: str = "") -> None:
    """A market order uses the live price. Once the first target is traded, it is late."""
    if not row.get("side") or row.get("stop") is None:
        return
    stop = float(row["stop"])
    targets = [float(price) for price in (row.get("targets") or []) if price is not None]
    target = row.get("target")
    if target is None and targets:
        target = targets[0]
    if row["side"] == "SELL":
        dead = ask is not None and stop <= float(ask)
        passed = bid is not None and target is not None and float(bid) <= float(target) + _band(symbol)
    else:
        dead = bid is not None and stop >= float(bid)
        passed = ask is not None and target is not None and float(ask) >= float(target) - _band(symbol)
    if not (dead or passed):
        return
    chart = str(row.get("chart") or "")
    trend = str(row.get("trend") or "")
    note = (
        "Price is already through this stop. Not a trade."
        if dead
        else "The first target is already reached. Not a new order."
    )
    row.clear()
    row.update(_wait(chart, note, trend))


def _headline(points: list[dict[str, Any]]) -> str:
    """The line on the chart. It does not open a trade."""
    trend = _trend(points)
    if trend == "UP":
        return "BULLISH"
    if trend == "DOWN":
        return "BEARISH"
    return "RANGE"


def _dedupe(zones: list[dict[str, Any]], spread: float) -> list[dict[str, Any]]:
    gap = max(float(spread or 0.0), 0.0) * 2.0
    kept: list[dict[str, Any]] = []
    for zone in sorted(zones, key=lambda item: (item["kind"], float(item["price"]))):
        if kept and kept[-1]["kind"] == zone["kind"] and abs(float(zone["price"]) - float(kept[-1]["price"])) <= gap:
            continue
        kept.append(zone)
    return kept


def _collect_zones(
    levels: dict[str, Any],
    highs: list[float],
    lows: list[float],
    spread: float,
    *,
    high_name: str,
    low_name: str,
) -> list[dict[str, Any]]:
    zones: list[dict[str, Any]] = []
    for level in levels.get("levels") or []:
        name = str(level.get("name") or "LEVEL")
        if level.get("high") is not None:
            zones.append({"name": name + " HIGH", "price": float(level["high"]), "kind": "HIGH"})
        if level.get("low") is not None:
            zones.append({"name": name + " LOW", "price": float(level["low"]), "kind": "LOW"})
    for price in highs:
        zones.append({"name": high_name, "price": float(price), "kind": "HIGH"})
    for price in lows:
        zones.append({"name": low_name, "price": float(price), "kind": "LOW"})
    return _dedupe(zones, spread)


def _harvest(symbol: str, entry: float, target: float) -> str:
    dist = abs(float(target) - float(entry))
    if symbol == "XAUUSD":
        return f"{round(dist / 0.1)} pips"
    if symbol == "EURUSD":
        return f"{round(dist / 0.0001)} pips"
    if symbol == "USDJPY":
        return f"{round(dist / 0.01)} pips"
    if symbol == "NAS100":
        return f"{round(dist)} points"
    if symbol == "BTCUSD":
        return f"${round(dist)}"
    if symbol == "XAGUSD":
        return f"{dist:.3f}"
    if symbol == "WTI" or symbol == "NG-C":
        return f"{dist:.2f}"
    if symbol == "GER40":
        return f"{round(dist)} points"
    return f"{dist:.5f}"


def _nearest_zone(side: str, entry: float, zones: list[dict[str, Any]]) -> float | None:
    ahead = _targets_ahead(side, entry, entry, zones)
    return ahead[0] if ahead else None


def _targets_ahead(side: str, entry: float, stop: float, zones: list[dict[str, Any]]) -> list[float]:
    """Every zone beyond the entry. The first has to be further than the stop."""
    risk = abs(float(entry) - float(stop))
    prices = []
    for zone in zones:
        price = round(float(zone["price"]), 5)
        if side == "BUY" and price <= entry:
            continue
        if side == "SELL" and price >= entry:
            continue
        if any(abs(price - kept) <= max(abs(entry) * 1e-8, 1e-8) for kept in prices):
            continue
        prices.append(price)
    prices.sort(reverse=(side == "SELL"))
    kept: list[float] = []
    for price in prices:
        if not kept and abs(price - entry) <= risk:
            continue
        kept.append(price)
    return kept[:4]


def _beyond(side: str, entry: float, prices: list[float], need: float) -> float | None:
    if side == "BUY":
        cands = [price for price in prices if price <= entry - need]
        return max(cands) if cands else None
    cands = [price for price in prices if price >= entry + need]
    return min(cands) if cands else None


def _stop_price(side: str, entry: float, wick: float, spread: float, beyond: list[float], *, wider: list[float] | None = None) -> float | None:
    """The wick first. If it is inside 10 times the spread, the swing beyond the zone. A higher-timeframe swing is wider."""
    need = float(spread) * 10.0 if spread and spread > 0 else 0.0
    if side == "BUY" and wick >= entry:
        wick = entry - need if need else entry - 1e-9
    if side == "SELL" and wick <= entry:
        wick = entry + need if need else entry + 1e-9
    stop = wick
    if wider:
        further = _beyond(side, entry, wider, max(abs(entry - wick), need))
        if further is not None:
            stop = further
    if need and abs(entry - stop) + 1e-9 < need:
        stop = _beyond(side, entry, list(beyond) + list(wider or []), need)
    if stop is None:
        return None
    if need and abs(entry - stop) + 1e-9 < need:
        return None
    if side == "BUY" and stop >= entry:
        return None
    if side == "SELL" and stop <= entry:
        return None
    return stop


def _turn(last: dict[str, Any], zones: list[dict[str, Any]], side: str) -> dict[str, Any] | None:
    kind = "LOW" if side == "BUY" else "HIGH"
    close = _num(last, "close")
    open_ = _num(last, "open")
    hits = []
    for zone in zones:
        if zone["kind"] != kind:
            continue
        price = float(zone["price"])
        if side == "BUY" and _num(last, "low") <= price and close > price and close >= open_:
            hits.append(zone)
        if side == "SELL" and _num(last, "high") >= price and close < price and close <= open_:
            hits.append(zone)
    if not hits:
        return None
    return min(hits, key=lambda zone: abs(float(zone["price"]) - close))


def _break_confirm(closed: list[dict[str, Any]], zones: list[dict[str, Any]], side: str) -> dict[str, Any] | None:
    if len(closed) < 3:
        return None
    older, broke, held = closed[-3], closed[-2], closed[-1]
    kind = "HIGH" if side == "BUY" else "LOW"
    hits = []
    for zone in zones:
        if zone["kind"] != kind:
            continue
        price = float(zone["price"])
        if side == "BUY":
            ok = _num(older, "close") <= price and _num(broke, "close") > price and _num(held, "close") > price
        else:
            ok = _num(older, "close") >= price and _num(broke, "close") < price and _num(held, "close") < price
        if ok:
            hits.append(zone)
    if not hits:
        return None
    close = _num(held, "close")
    return min(hits, key=lambda zone: abs(float(zone["price"]) - close))


def _sentence(state: str, reason: str, side: str, zone: dict[str, Any], entry: float, stop: float, targets: list[float], symbol: str, clock: str = "1-minute") -> str:
    edge = "buy zone" if side == "BUY" else "sell zone"
    price = round(float(zone["price"]), 5)
    if reason == "SCALP":
        what = f"The {clock} candle closed on the point of control at {price}."
    elif reason == "RANGE":
        what = f"The {clock} candle closed back out of the {edge} at {price}."
    elif reason == "PULLBACK":
        way = "up" if side == "BUY" else "down"
        what = f"The trend is {way}. The {clock} candle closed back {way} from the {edge} at {price}."
    else:
        what = f"Two {clock} candles closed through the {edge} at {price}."
    side_word = "below" if side == "BUY" else "above"
    listed = ", ".join(
        f"T{index} {round(target, 5)} {_harvest(symbol, entry, target)}"
        for index, target in enumerate(targets, 1)
    )
    return (
        f"{reason} {side}. Price is {state.lower()}. {what} "
        f"Stop {side_word} the wick at {round(stop, 5)}. {listed}."
    )


def _pack(
    symbol: str,
    chart: str,
    reason: str,
    side: str,
    state: str,
    zone: dict[str, Any],
    last: dict[str, Any],
    stop: float,
    targets: list[float],
    spread: float,
) -> dict[str, Any] | None:
    entry = _num(last, "close")
    target = targets[0]
    if side == "BUY" and not (target > entry > stop):
        return None
    if side == "SELL" and not (stop > entry > target):
        return None
    if abs(target - entry) <= abs(entry - stop):
        return None
    row = _offer(chart, side, reason, entry, stop, target, _time(last), spread, symbol, wick_limit=False)
    if not row.get("tradeable"):
        return None
    row["targets"] = [round(price, 5) for price in targets]
    row["harvest"] = " · ".join(
        f"T{index} {_harvest(symbol, entry, price)}" for index, price in enumerate(targets, 1)
    )
    row["market"] = state
    row["score_on"] = "M1"
    row["zone"] = float(zone["price"])
    row["note"] = _sentence(state, reason, side, zone, entry, stop, targets, symbol, "4-hour" if chart == "SWING" else "1-minute")
    return row


def _choose(
    symbol: str,
    chart: str,
    state: str,
    closed: list[dict[str, Any]],
    zones: list[dict[str, Any]],
    spread: float,
    beyond: list[float],
    *,
    wider: list[float] | None = None,
    swing_stop: bool = False,
) -> dict[str, Any] | None:
    if len(closed) < 3 or not zones:
        return None
    last = closed[-1]
    found: list[tuple[str, str, dict[str, Any]]] = []
    for side in ("BUY", "SELL"):
        zone = _break_confirm(closed, zones, side)
        if zone is not None:
            found.append(("BREAK", side, zone))
    if not found:
        for side in ("BUY", "SELL"):
            zone = _turn(last, zones, side)
            if zone is None:
                continue
            with_trend = (state == "BULLISH" and side == "BUY") or (state == "BEARISH" and side == "SELL")
            found.append(("PULLBACK" if with_trend else "RANGE", side, zone))
    if not found:
        return None
    close = _num(last, "close")
    reason, side, zone = min(found, key=lambda item: abs(float(item[2]["price"]) - close))
    if swing_stop:
        pad = max(float(spread) * 10.0, PIP.get(symbol, 0.0) or 0.0)
        stop = float(zone["price"]) - pad if side == "BUY" else float(zone["price"]) + pad
        further = _beyond(side, close, list(wider or []), abs(close - stop))
        if further is not None and abs(close - further) > abs(close - stop):
            stop = further
        if spread > 0 and abs(close - stop) + 1e-9 < spread * 10.0:
            return None
        if side == "BUY" and stop >= close:
            return None
        if side == "SELL" and stop <= close:
            return None
    else:
        if reason == "BREAK":
            earlier = closed[-2]
            wick = min(_num(earlier, "low"), _num(last, "low")) if side == "BUY" else max(_num(earlier, "high"), _num(last, "high"))
        else:
            wick = _num(last, "low") if side == "BUY" else _num(last, "high")
        stop = _stop_price(side, close, wick, spread, beyond, wider=wider)
        if stop is None:
            return None
    targets = _targets_ahead(side, close, stop, zones)
    if not targets:
        return None
    return _pack(symbol, chart, reason, side, state, zone, last, stop, targets, spread)


def _prices(points: list[dict[str, Any]], kind: str, count: int = 6) -> list[float]:
    return [float(point["price"]) for point in points if point["kind"] == kind][-count:]


def _bars_for(row: dict[str, Any], bars_by_chart: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    name = str(row.get("score_on") or "M1")
    return bars_by_chart.get(name) or bars_by_chart.get(str(row.get("chart"))) or []


def _two_closes(closed: list[dict[str, Any]], level: float, side: str) -> bool:
    if len(closed) < 2:
        return False
    first, second = closed[-2], closed[-1]
    if side == "BUY":
        return _num(first, "close") > level and _num(second, "close") > level
    return _num(first, "close") < level and _num(second, "close") < level


def _touched(closed: list[dict[str, Any]], level: float, side: str) -> bool:
    if not closed:
        return False
    last = closed[-1]
    if side == "BUY":
        return _num(last, "high") >= level
    return _num(last, "low") <= level


def _reached_target(side: str, price: float, bid: float | None, ask: float | None, closed: list[dict[str, Any]]) -> bool:
    """The bid through a sell target counts. So does the ask through a buy target. Two closes count as well."""
    if side == "SELL" and isinstance(bid, (int, float)) and not isinstance(bid, bool) and float(bid) <= price:
        return True
    if side == "BUY" and isinstance(ask, (int, float)) and not isinstance(ask, bool) and float(ask) >= price:
        return True
    return _two_closes(closed, price, side)


def _r_multiple(entry: float, stop: float, price: float) -> float | None:
    risk = abs(float(entry) - float(stop))
    if risk <= 0:
        return None
    return round(abs(float(price) - float(entry)) / risk, 2)


def _guide(
    row: dict[str, Any],
    book: dict[str, Any] | None,
    closed: list[dict[str, Any]],
    symbol: str,
    bid: float | None = None,
    ask: float | None = None,
) -> str:
    """Hold for the next target unless both clocks are against the trade."""
    if not row.get("side") or row.get("entry") is None:
        return ""
    targets = [float(price) for price in (row.get("targets") or []) if price is not None]
    if not targets and row.get("target") is not None:
        targets = [float(row["target"])]
    if not targets:
        return ""
    side = str(row["side"])
    entry = float(row["entry"])
    stop = float(row["stop"]) if row.get("stop") is not None else entry
    book = book or {}

    def _signed(name: str) -> bool | None:
        value = book.get(name)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return None
        if side == "BUY":
            return value > 0
        return value < 0

    with_60 = _signed("delta_60s")
    with_5 = _signed("delta_5s")
    known = with_60 is not None
    passed = [price for price in targets if _reached_target(side, price, bid, ask, closed)]
    remaining = [price for price in targets if price not in passed]
    at_zone = any(_touched(closed, price, side) for price in remaining or targets)
    absorption = bool(book.get("absorption")) and at_zone
    longer_raw = book.get("delta_60s")
    quiet = isinstance(longer_raw, (int, float)) and not isinstance(longer_raw, bool) and abs(float(longer_raw)) < 10
    both_against = (not quiet) and with_60 is False and with_5 is False
    row["targets"] = [round(price, 5) for price in targets]
    row["legs"] = [
        {"price": round(price, 5), "r": _r_multiple(entry, stop, price)}
        for price in targets
    ]
    row["harvest"] = " · ".join(
        f"T{index} {_r_multiple(entry, stop, price) or 0:.2f}R"
        for index, price in enumerate(targets, 1)
    )
    aim = remaining[0] if remaining else targets[-1]
    if passed and not remaining:
        line = f"The last target {round(passed[-1], 5)} is reached."
    elif not known and passed and remaining:
        line = (
            f"{round(passed[-1], 5)} is reached. No 60-second delta in this book. "
            f"The next target is {round(remaining[0], 5)}. Nothing says hold or bank."
        )
    elif not known:
        line = "No 60-second delta in this book. The targets stay. Nothing says hold or bank."
    elif absorption:
        line = "Absorption at the target. Bank half. Move the stop to the entry."
    elif quiet:
        line = f"Hold for {round(aim, 5)}." if not (passed and remaining) else f"Hold the rest for {round(remaining[0], 5)}."
    elif both_against:
        line = "Both the 5-second and the 60-second book are against the trade. Bank half. Move the stop to the entry."
    elif with_60 is False and with_5 is not False:
        line = f"The 60-second book is against the trade. The last 5 seconds are not. Hold for {round(aim, 5)}."
    elif passed and remaining:
        line = f"Hold the rest for {round(remaining[0], 5)}."
    else:
        line = f"Hold for {round(aim, 5)}."
    row["guide"] = line
    sentence = str(row.get("note") or "").strip()
    row["note"] = (sentence + " " + line).strip()
    return line


def _coming(
    live: dict[str, Any] | None,
    zones: list[dict[str, Any]],
    area: tuple[float, float, float] | None,
    symbol: str,
    spread: float,
    beyond: list[float],
) -> dict[str, Any] | None:
    """The live candle is at the value low or the value high. A swing in the middle stays quiet."""
    if not live or area is None:
        return None
    val, _poc, vah = area
    slack = _band(symbol)
    watched = [dict(zone) for zone in zones if zone.get("price") is not None]
    watched.append({"name": "VALUE LOW", "price": float(val), "kind": "LOW"})
    watched.append({"name": "VALUE HIGH", "price": float(vah), "kind": "HIGH"})
    low = _num(live, "low")
    high = _num(live, "high")
    close = _num(live, "close")
    open_ = _num(live, "open")
    hits: list[tuple[float, str, dict[str, Any], bool]] = []
    for zone in watched:
        price = float(zone["price"])
        if zone.get("kind") == "LOW" and price <= val + slack and low <= price <= high:
            hits.append((abs(price - close), "BUY", zone, close > price and close >= open_))
        if zone.get("kind") == "HIGH" and price >= vah - slack and low <= price <= high:
            hits.append((abs(price - close), "SELL", zone, close < price and close <= open_))
    if not hits:
        return None
    _distance, side, zone, back = min(hits, key=lambda item: item[0])
    price = round(float(zone["price"]), 5)
    entry = float(price)
    wick = low if side == "BUY" else high
    stop = _stop_price(side, entry, wick, spread, beyond)
    if stop is not None:
        targets = _targets_ahead(side, entry, stop, watched)
        preview = {"side": side, "entry": entry, "stop": stop, "targets": targets, "target": targets[0] if targets else None}
        _use_value_target(preview, area)
        targets = [float(level) for level in (preview.get("targets") or [])]
    else:
        ahead = []
        for level in watched:
            level_price = float(level["price"])
            if side == "BUY" and level_price > entry:
                ahead.append(level_price)
            elif side == "SELL" and level_price < entry:
                ahead.append(level_price)
        other = float(vah if side == "BUY" else val)
        if (side == "BUY" and other > entry) or (side == "SELL" and other < entry):
            ahead.append(other)
        targets = []
        for level_price in sorted(ahead, reverse=(side == "SELL")):
            if any(abs(level_price - kept) <= max(abs(entry) * 1e-8, 1e-8) for kept in targets):
                continue
            targets.append(level_price)
            if len(targets) == 4:
                break
    risk = abs(entry - float(stop)) if stop is not None else 0.0
    planned = []
    for level_price in targets:
        multiple = round(abs(level_price - entry) / risk, 2) if risk > 0 else None
        planned.append({"price": round(level_price, 5), "r": multiple})
    listed = " · ".join(
        f"TP{index} {item['price']} {item['r']}R" if item["r"] is not None else f"TP{index} {item['price']}"
        for index, item in enumerate(planned, 1)
    )
    if back:
        text = f"The 1-minute candle has closed back out of {price}. It is a trade when that candle finishes."
        state = "CLOSING BACK"
    else:
        text = f"Price is trading into {price}. Not a trade until the 1-minute candle closes back out."
        state = "COMING"
    if listed:
        text = text + " " + listed + "."
    return {
        "side": side,
        "zone": price,
        "name": zone.get("name"),
        "state": state,
        "time": _time(live),
        "text": text,
        "stop": None if stop is None else round(float(stop), 5),
        "targets": planned,
        "tps": listed,
    }


def _both_against(side: str, book: dict[str, Any] | None) -> bool:
    """Both clocks are against the trade, and the 60-second book is not quiet."""
    def signed(name: str) -> float | None:
        value = (book or {}).get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        return float(value)

    short = signed("delta_5s")
    longer = signed("delta_60s")
    if short is None or longer is None or abs(longer) < 10:
        return False
    if side == "BUY":
        return short < 0 and longer < 0
    return short > 0 and longer > 0


def _push(
    symbol: str,
    closed: list[dict[str, Any]],
    zones: list[dict[str, Any]],
    spread: float,
    area: tuple[float, float, float] | None,
    book: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """A finished close back out of a middle swing. The wick is the stop. Not an order."""
    if area is None or not closed or not zones:
        return None
    last = closed[-1]
    close = _num(last, "close")
    found: list[tuple[str, dict[str, Any]]] = []
    for side in ("BUY", "SELL"):
        zone = _turn(last, zones, side)
        if zone is None:
            continue
        if _at_edge({"side": side, "zone": float(zone["price"])}, area, symbol):
            continue
        found.append((side, zone))
    if not found:
        return None
    side, zone = min(found, key=lambda item: abs(float(item[1]["price"]) - close))
    if _both_against(side, book):
        return None
    entry = close
    stop = _num(last, "low") if side == "BUY" else _num(last, "high")
    if side == "BUY" and stop >= entry:
        return None
    if side == "SELL" and stop <= entry:
        return None
    risk = abs(entry - stop)
    if risk <= 0:
        return None
    if symbol == "EURUSD" and risk <= _band(symbol, 1.5):
        return None
    if symbol == "XAUUSD" and risk + 1e-9 < GOLD_MIN_STOP:
        return None
    targets = _targets_ahead(side, entry, stop, zones)
    if not targets or abs(float(targets[0]) - entry) <= risk:
        return None
    multiples = [round(abs(float(price) - entry) / risk, 2) for price in targets]
    listed = " · ".join(
        f"TP{index} {round(float(price), 5)} {multiple}R"
        for index, (price, multiple) in enumerate(zip(targets, multiples), 1)
    )
    longer = (book or {}).get("delta_60s")
    quiet = isinstance(longer, (int, float)) and not isinstance(longer, bool) and abs(float(longer)) < 10
    extra = ""
    if spread and float(spread) > risk / 3.0:
        extra += " The spread is a large part of the stop."
    if quiet:
        extra += " The book is quiet."
    note = (
        f"HIGH RISK. The 1-minute candle closed back out of {round(float(zone['price']), 5)}. "
        f"The stop is the wick, not 10 times the spread. Not an order.{extra} {listed}."
    )
    return {
        "chart": "INTRADAY",
        "side": side,
        "reason": "PUSH",
        "r": multiples[0],
        "decision": "HIGH RISK",
        "note": note.strip(),
        "state": "HIGH RISK",
        "trend": "",
        "tradeable": False,
        "entry": round(entry, 5),
        "stop": round(stop, 5),
        "risk_stop": round(stop, 5),
        "target": round(float(targets[0]), 5),
        "targets": [round(float(price), 5) for price in targets],
        "time": _time(last),
        "zone": round(float(zone["price"]), 5),
        "harvest": listed,
        "push": True,
        "score_on": "M1",
    }


def _at_edge(row: dict[str, Any], area: tuple[float, float, float], symbol: str) -> bool:
    """A buy only at the value low. A sell only at the value high. The middle is not this row."""
    val, _poc, vah = area
    zone = row.get("zone")
    if zone is None or not row.get("side"):
        return False
    slack = _band(symbol)
    if row["side"] == "BUY":
        return float(zone) <= val + slack
    return float(zone) >= vah - slack


def _scalp(
    symbol: str,
    closed: list[dict[str, Any]],
    zones: list[dict[str, Any]],
    spread: float,
    area: tuple[float, float, float] | None,
    state: str,
) -> dict[str, Any] | None:
    """The close is on the point of control. The target is the next zone. One order."""
    if area is None or not closed:
        return None
    val, poc, vah = area
    if len(closed) >= 2:
        older = _num(closed[-2], "close")
        newer = _num(closed[-1], "close")
        if (older < val and newer < val) or (older > vah and newer > vah):
            return None
    last = closed[-1]
    close = _num(last, "close")
    if abs(close - poc) > _band(symbol):
        return None
    low = _num(last, "low")
    high = _num(last, "high")
    open_ = _num(last, "open")
    side = None
    if low <= poc <= close and close >= open_:
        side = "BUY"
    elif high >= poc >= close and close <= open_:
        side = "SELL"
    if side is None:
        return None
    kind = "LOW" if side == "BUY" else "HIGH"
    zone = {"name": "POINT OF CONTROL", "price": poc, "kind": kind}
    wick = low if side == "BUY" else high
    stop = _stop_price(side, close, wick, spread, [float(item["price"]) for item in zones])
    if stop is None:
        return None
    targets = _targets_ahead(side, close, stop, zones)
    if not targets:
        other = vah if side == "BUY" else val
        if (side == "BUY" and other > close) or (side == "SELL" and other < close):
            targets = [other]
    if not targets:
        return None
    return _pack(symbol, "SCALP", "SCALP", side, state, zone, last, stop, targets, spread)


def _value_break(
    symbol: str,
    closed: list[dict[str, Any]],
    zones: list[dict[str, Any]],
    spread: float,
    area: tuple[float, float, float] | None,
) -> dict[str, Any] | None:
    """The last two closes just left value. An older close is not a new market order."""
    if area is None or len(closed) < 3:
        return None
    val, poc, vah = area
    prior = _num(closed[-3], "close")
    older = _num(closed[-2], "close")
    newer = _num(closed[-1], "close")
    if older > vah and newer > vah and prior <= vah:
        start, side, level = closed[-1], "BUY", vah
    elif older < val and newer < val and prior >= val:
        start, side, level = closed[-1], "SELL", val
    else:
        return None
    entry = _num(start, "close")
    pad = max(float(spread) * 10.0, PIP.get(symbol, 0.0) or 0.0)
    stop = (level + pad) if side == "SELL" else (level - pad)
    if side == "SELL" and stop <= entry:
        stop = entry + pad
    if side == "BUY" and stop >= entry:
        stop = entry - pad
    targets = _targets_ahead(side, entry, stop, zones)
    if not targets:
        if side == "SELL" and poc < entry:
            targets = [poc]
        elif side == "BUY" and poc > entry:
            targets = [poc]
    if not targets:
        span = abs(vah - val)
        projected = (level - span) if side == "SELL" else (level + span)
        if span > 0 and ((side == "SELL" and projected < entry) or (side == "BUY" and projected > entry)):
            targets = [round(projected, 5)]
    if not targets:
        return None
    zone = {
        "name": "VALUE LOW" if side == "SELL" else "VALUE HIGH",
        "price": level,
        "kind": "LOW" if side == "SELL" else "HIGH",
    }
    row = _pack(symbol, "SWING", "BREAK", side, "TREND", zone, start, stop, targets, spread)
    if row is None:
        return None
    row["note"] = (
        f"BREAK {side}. Price left value. Two 4-hour candles closed outside {round(level, 5)}. "
        f"Stop back inside value at {round(float(row['stop']), 5)}. "
        + str(row.get("note") or "")
    ).strip()
    return row


def _silence(row: dict[str, Any], text: str) -> None:
    if not row.get("side") or not row.get("tradeable"):
        return
    row["tradeable"] = False
    row["state"] = "SHOWN"
    note = str(row.get("note") or "")
    if text not in note:
        row["note"] = (text + " " + note).strip()


def _spent(symbol: str, chart: str, side: str, zone: float) -> bool:
    """One order per zone on the fast rows and the scalp. The swing is allowed to show beside them."""
    if chart not in ("INTRADAY", "INTERDAY", "SCALP"):
        return False
    state = _load_state()
    band = _band(symbol)
    for item in (state.get("spent_zones") or {}).values():
        if item.get("symbol") != symbol or item.get("chart") != chart or item.get("side") != side:
            continue
        try:
            if abs(float(item.get("zone")) - float(zone)) <= band:
                return True
        except (TypeError, ValueError):
            continue
    return False


def _limits(row: dict[str, Any], symbol: str, spread: float) -> None:
    """A zero spread, a one-pip euro stop, and a gold stop inside $2 are not buttons."""
    if not row.get("side") or row.get("entry") is None or row.get("stop") is None or not row.get("tradeable"):
        return
    if spread is None or float(spread) <= 0:
        _silence(row, "The spread is not on the quote, so this is not an order.")
        return
    risk = abs(float(row["entry"]) - float(row["stop"]))
    if symbol == "EURUSD" and risk <= _band(symbol, 1.5):
        _silence(row, "The stop is about one pip. Not a trade.")
        return
    if symbol == "XAUUSD" and row.get("chart") != "SCALP" and risk + 1e-9 < GOLD_MIN_STOP:
        _silence(row, "The stop is inside $2. Not a trade unless it is the point-of-control scalp.")


TEST_STATE = Path("failed_break_state.json")
TEST_LOG = Path("failed_break_log.jsonl")


def _flow_snap(book: dict[str, Any] | None) -> dict[str, Any]:
    book = book or {}
    ice = book.get("iceberg") if isinstance(book.get("iceberg"), dict) else {}
    return {
        "delta_5s": book.get("delta_5s"),
        "delta_60s": book.get("delta_60s"),
        "absorption": bool(book.get("absorption")),
        "iceberg": ice.get("price"),
        "iceberg_side": ice.get("side"),
        "sweep": bool(book.get("sweep_consumed")),
        "pulled": bool(book.get("size_pulled")),
    }


def _probe(bars: list[dict[str, Any]], val: float, vah: float) -> dict[str, Any] | None:
    """The latest close back through a low under value, or a high over value."""
    found: dict[str, Any] | None = None
    index = 0
    count = len(bars)
    while index < count:
        low = _num(bars[index], "low")
        high = _num(bars[index], "high")
        if low < val or high > vah:
            side = "BUY" if low < val else "SELL"
            if low < val and high > vah:
                side = "BUY" if (val - low) >= (high - vah) else "SELL"
            extreme = low if side == "BUY" else high
            extreme_at = index
            cursor = index
            while cursor < count:
                bar_low = _num(bars[cursor], "low")
                bar_high = _num(bars[cursor], "high")
                if side == "BUY" and bar_low > val and cursor > extreme_at:
                    break
                if side == "SELL" and bar_high < vah and cursor > extreme_at:
                    break
                if side == "BUY" and bar_low < extreme:
                    extreme = bar_low
                    extreme_at = cursor
                if side == "SELL" and bar_high > extreme:
                    extreme = bar_high
                    extreme_at = cursor
                cursor += 1
            close_at = None
            for later in range(extreme_at, count):
                close = _num(bars[later], "close")
                if (side == "BUY" and close > extreme) or (side == "SELL" and close < extreme):
                    close_at = later
                    break
            found = {"side": side, "extreme": extreme, "extreme_at": extreme_at, "close_at": close_at, "bars": bars}
            index = max(cursor, extreme_at + 1)
            continue
        index += 1
    return found


def _failed_test(
    symbol: str,
    m1: list[dict[str, Any]],
    m15: list[dict[str, Any]],
    area: tuple[float, float, float] | None,
    book: dict[str, Any] | None,
    spread: float,
    bid: float | None,
    ask: float | None,
) -> dict[str, Any]:
    """A 1-minute close back through an excess. The button is only on that candle, and only while value is still ahead."""
    if area is None:
        return _wait("RESPONSIVE", "TESTING. Value area is not on this chart yet. Not a trade.", "")
    val, poc, vah = area
    minute = _closed(m1)
    probe = _probe(minute, val, vah) if len(minute) >= 5 else None
    source = "1-minute"
    if probe is None or probe.get("close_at") is None:
        return _wait("RESPONSIVE", "TESTING. No close back through a low under value or a high over value. Not a trade.", "")
    show = int(probe["close_at"]) >= len(probe["bars"]) - 1
    side = str(probe["side"])
    series: list[dict[str, Any]] = probe["bars"]
    extreme = float(probe["extreme"])
    close_at = int(probe["close_at"])
    entry = _num(series[close_at], "close")
    if side == "BUY" and not entry < val:
        return _wait("RESPONSIVE", "TESTING. The close is already through the value low. Not a trade.", "")
    if side == "SELL" and not entry > vah:
        return _wait("RESPONSIVE", "TESTING. The close is already through the value high. Not a trade.", "")
    pad = max(float(spread), _band(symbol))
    stop = extreme - pad if side == "BUY" else extreme + pad
    floor = float(BE_MOVE.get(symbol, 0.0) or 0.0)
    if floor > 0:
        stop = min(stop, entry - floor) if side == "BUY" else max(stop, entry + floor)
    risk = abs(entry - stop)
    if risk <= 0:
        return _wait("RESPONSIVE", "TESTING. The stop is not beyond the extreme. Not a trade.", "")
    ladder = [val, poc, vah] if side == "BUY" else [vah, poc, val]
    targets = [price for price in ladder if (price > entry if side == "BUY" else price < entry)]
    if not targets:
        return _wait("RESPONSIVE", "TESTING. Price is already through the value low, the point of control, and the value high. Not a new entry.", "")
    far = vah if side == "BUY" else val
    deciding = [
        price for price in (poc, far)
        if (price > entry if side == "BUY" else price < entry) and abs(float(price) - entry) > risk
    ]
    if not deciding:
        return _wait("RESPONSIVE", "TESTING. The point of control and the far side are not further than the stop. Not a trade.", "")
    furthest = entry
    adverse = entry
    stopped = False
    live = bid if side == "BUY" else ask
    if isinstance(live, (int, float)) and not isinstance(live, bool):
        furthest = max(furthest, float(live)) if side == "BUY" else min(furthest, float(live))
        adverse = min(adverse, float(live)) if side == "BUY" else max(adverse, float(live))
    for bar in series[close_at + 1:]:
        if side == "BUY":
            furthest = max(furthest, _num(bar, "high"))
            adverse = min(adverse, _num(bar, "low"))
            if _num(bar, "low") <= stop:
                stopped = True
        else:
            furthest = min(furthest, _num(bar, "low"))
            adverse = max(adverse, _num(bar, "high"))
            if _num(bar, "high") >= stop:
                stopped = True
    if side == "BUY":
        reached_value = furthest + 1e-9 >= val
        reached_poc = furthest + 1e-9 >= poc
        reached_far = furthest + 1e-9 >= vah
    else:
        reached_value = furthest - 1e-9 <= vah
        reached_poc = furthest - 1e-9 <= poc
        reached_far = furthest - 1e-9 <= val
    ratios = [round(abs(price - entry) / risk, 2) for price in targets]
    at_signal = close_at >= len(series) - 1
    _remember_test({
        "symbol": symbol, "side": side, "extreme": extreme, "entry": entry, "stop": stop,
        "target": targets[0], "targets": targets, "r": ratios, "value_low": val, "poc": poc,
        "value_high": vah, "candle": _time(series[close_at]), "candle_size": source,
        "spread": spread, "mae": round(abs(entry - adverse), 5), "furthest": furthest,
        "stopped": stopped, "reached_value": reached_value, "reached_poc": reached_poc,
        "reached_far": reached_far, "flow": _flow_snap(book), "flow_at_signal": at_signal,
    })
    if not show:
        return _wait("RESPONSIVE", "TESTING. The close back is no longer the latest candle. Not a trade.", "")
    levels = " ".join(f"T{index} {round(price, 5)} {ratio:.2f}R" for index, (price, ratio) in enumerate(zip(targets, ratios), 1))
    row = {
        "chart": "RESPONSIVE", "side": side, "reason": "RESPONSIVE", "r": ratios[0],
        "decision": "—", "note": "", "state": "READY",
        "trend": "", "tradeable": True, "entry": entry, "stop": stop, "risk_stop": stop,
        "target": targets[0], "targets": targets, "time": _time(series[close_at]),
    }
    _guide(row, book, series, symbol, bid, ask)
    guide = str(row.pop("guide", "") or "")
    row["note"] = (
        f"RESPONSIVE {side}. Excess {round(extreme, 5)}. "
        f"The {source} candle closed back at {round(entry, 5)}. Stop {round(stop, 5)}. {levels}. {guide}"
    ).strip()
    live_px = bid if side == "BUY" else ask
    if isinstance(live_px, (int, float)) and not isinstance(live_px, bool) and abs(float(live_px) - entry) > _band(symbol):
        return _wait("RESPONSIVE", "Price has left that entry. Not a trade.", "")
    return row


def _remember_test(fields: dict[str, Any]) -> dict[str, Any]:
    """One record per excess low or high. A later price updates it. The same entry is not written again."""
    key = "|".join((str(fields["symbol"]), str(fields["side"]), str(round(float(fields["extreme"]), 5))))
    try:
        state = json.loads(TEST_STATE.read_text(encoding="utf-8")) if TEST_STATE.exists() else {}
    except (OSError, json.JSONDecodeError):
        state = {}
    if not isinstance(state, dict):
        state = {}
    prior = state.get(key) if isinstance(state.get(key), dict) else None
    milestone = (
        bool(fields["reached_value"]), bool(fields["reached_poc"]),
        bool(fields["reached_far"]), bool(fields["stopped"]),
    )
    if prior is None:
        prior = {
            **fields,
            "opened": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "milestone": list(milestone),
        }
        _test_event({"event": "OPEN", **prior})
    else:
        old = tuple(prior.get("milestone") or [])
        moved = prior.get("furthest") != fields["furthest"] or old != milestone
        prior["furthest"] = fields["furthest"]
        prior["mae"] = fields["mae"]
        prior["milestone"] = list(milestone)
        if moved and old != milestone:
            prior["updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            _test_event({
                "event": "UPDATE", "symbol": fields["symbol"], "side": fields["side"],
                "extreme": fields["extreme"], "entry": fields["entry"], "stop": fields["stop"],
                "targets": fields["targets"], "r": fields["r"], "furthest": fields["furthest"],
                "mae": fields["mae"], "milestone": list(milestone),
            })
    state[key] = prior
    try:
        TEST_STATE.write_text(json.dumps(state), encoding="utf-8")
    except OSError:
        pass
    return prior


def _test_event(row: dict[str, Any]) -> None:
    try:
        with TEST_LOG.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row) + "\n")
    except OSError:
        return


def build_rows(
    symbol: str,
    bars_by_chart: dict[str, list[dict[str, Any]]],
    book: dict[str, Any] | None,
    spread: float,
    levels: dict[str, Any],
    bid: float | None = None,
    ask: float | None = None,
) -> list[dict[str, Any]]:
    """Five rows. A touch is not a signal. The middle of value is not a fast trade."""
    m1 = bars_by_chart.get("M1") or []
    m15 = bars_by_chart.get("M15") or []
    h4 = bars_by_chart.get("H4") or []
    d1 = bars_by_chart.get("D1") or []
    closed = _closed(m1)
    points15, highs15, lows15 = _ends(m15)
    points4, highs4, lows4 = _ends(h4)
    _points_d, highs_d, lows_d = _ends(d1)
    state = _headline(points15)
    day_levels = levels or {"levels": []}
    intraday_zones = _collect_zones(
        day_levels,
        _prices(highs15, "HIGH") + _prices(_ends(bars_by_chart.get("H1") or [])[1], "HIGH", 4),
        _prices(lows15, "LOW") + _prices(_ends(bars_by_chart.get("H1") or [])[2], "LOW", 4),
        spread,
        high_name="SWING HIGH",
        low_name="SWING LOW",
    )
    beyond = _prices(lows15, "LOW") + _prices(highs15, "HIGH")
    mid = None
    if isinstance(bid, (int, float)) and isinstance(ask, (int, float)):
        mid = (float(bid) + float(ask)) / 2.0
    area = _value_area(book, mid if mid is not None else bid, symbol)
    intraday = _choose(symbol, "INTRADAY", state, closed, intraday_zones, spread, beyond)
    intraday_note = "No close back from the value low or the value high."
    if area is None:
        intraday = None
        intraday_note = "Value area is not on this chart yet."
    elif intraday is not None and not _at_edge(intraday, area, symbol):
        intraday = None
        val, _poc, vah = area
        outside = mid is not None and (float(mid) < val or float(mid) > vah)
        intraday_note = (
            "Price is outside the value area. No close back from the value low or the value high."
            if outside
            else "Price is in the middle of the value area. Not a trade."
        )
    scalp = _scalp(symbol, closed, intraday_zones, spread, area, state)
    swing_levels = {
        "levels": [level for level in (day_levels.get("levels") or []) if str(level.get("name")) == "YESTERDAY"]
    }
    swing_zones = _collect_zones(
        swing_levels,
        _prices(highs4, "HIGH", 4) + _prices(highs_d, "HIGH", 2),
        _prices(lows4, "LOW", 4) + _prices(lows_d, "LOW", 2),
        spread,
        high_name="4H HIGH",
        low_name="4H LOW",
    )
    wider = _prices(lows4, "LOW", 4) + _prices(highs4, "HIGH", 4)
    swing_state = _headline(points4)
    closed_h4 = _closed(h4)
    swing = _value_break(symbol, closed_h4, swing_zones, spread, area)
    if swing is None:
        swing = _choose(
            symbol, "SWING", swing_state, closed_h4, swing_zones, spread, wider, wider=wider, swing_stop=True,
        )
        if swing is not None and (area is None or not _at_edge(swing, area, symbol)):
            swing = None
        elif swing is not None and (
            (swing_state == "BEARISH" and swing.get("side") == "BUY")
            or (swing_state == "BULLISH" and swing.get("side") == "SELL")
        ):
            swing = None
    swing_miss = "No confirmed turn at the value low or the value high."
    iceberg = _iceberg(symbol, bars_by_chart, book, spread, bid, ask)
    if symbol not in ICE_ONLY:
        iceberg_note = "Iceberg is only gold, oil, Nasdaq, and natural gas."
    else:
        iceberg_note = "No iceberg price in the file."
    notes = {
        "ICEBERG": iceberg_note,
        "INTRADAY": intraday_note,
        "INTERDAY": "No intraday trade is still open.",
        "SCALP": "The close is not on the point of control.",
        "SWING": swing_miss,
    }
    chosen = {"ICEBERG": iceberg, "INTRADAY": intraday, "SCALP": scalp, "SWING": swing}
    rows: list[dict[str, Any]] = []
    for chart in ROWS:
        row = dict(chosen[chart]) if chosen.get(chart) else _wait(chart, notes[chart], state)
        row["chart"] = chart
        row["market"] = state
        row["score_on"] = "M1"
        row.setdefault("harvest", "—")
        if row.get("side"):
            delta = (book or {}).get("delta_60s")
            if isinstance(delta, (int, float)) and not isinstance(delta, bool) and delta > 0:
                row["decision"] = "60s BUYERS"
            elif isinstance(delta, (int, float)) and not isinstance(delta, bool) and delta < 0:
                row["decision"] = "60s SELLERS"
            else:
                row["decision"] = "—"
            if chart == "ICEBERG":
                row["decision"] = "ICEBERG"
        else:
            row["decision"] = "—"
            row["higher"] = "—"
            row["next_vote"] = "NONE"
        rows.append(row)
    _retain(symbol, rows, bars_by_chart)
    by_name = {row["chart"]: row for row in rows}
    intra = by_name.get("INTRADAY") or {}
    if intra.get("side"):
        _use_value_target(intra, area)
        _guide(intra, book, closed, symbol, bid, ask)
    swing_row = by_name.get("SWING") or {}
    if swing_row.get("side"):
        _use_value_target(swing_row, area)
        _guide(swing_row, book, closed, symbol, bid, ask)
    scalp_row = by_name.get("SCALP") or {}
    if scalp_row.get("side"):
        _use_value_target(scalp_row, area)
        _guide(scalp_row, book, closed, symbol, bid, ask)
    inter = by_name["INTERDAY"]
    targets = [float(price) for price in (intra.get("targets") or [])]
    guide = str(intra.get("guide") or "")
    carrier = intra
    opposite = intra.get("opposite") if isinstance(intra.get("opposite"), dict) else None
    if not (opposite and opposite.get("side") and opposite.get("side") != intra.get("side")):
        swing_opp = swing_row.get("opposite") if isinstance(swing_row.get("opposite"), dict) else None
        if swing_opp and swing_opp.get("side") and swing_opp.get("side") != swing_row.get("side"):
            carrier = swing_row
            opposite = swing_opp
            guide = str(swing_row.get("guide") or "")
    if opposite and opposite.get("side") and opposite.get("side") != carrier.get("side"):
        protected = "stop is at the entry" in guide
        held_side = str(carrier.get("side"))
        close = (
            f"Get ready to close the open {held_side}. The stop is at the entry, so closing it is not a loss."
            if protected
            else f"Get ready to close the open {held_side}. The stop is not at the entry, so closing it can still lose."
        )
        inter.update(opposite)
        inter["chart"] = "INTERDAY"
        inter["market"] = state
        inter["score_on"] = "M1"
        inter["tradeable"] = False
        inter["state"] = "SHOWN"
        inter["decision"] = "—"
        inter["higher"] = "—"
        inter["next_vote"] = "NONE"
        inter["note"] = f"{close} {opposite.get('note') or ''}".strip()
        inter["signal_note"] = str(opposite.get("note") or "")
        inter["closes"] = held_side
    elif not intra.get("side"):
        inter.update(_wait("INTERDAY", "No intraday trade is still open.", state))
        inter["tradeable"] = False
    elif "Do not aim further" in guide or "against the trade" in guide:
        inter.update(_wait("INTERDAY", "Not a new order. " + guide, state))
        inter["side"] = intra.get("side")
        inter["state"] = "SHOWN"
        inter["tradeable"] = False
    elif len(targets) < 2:
        inter.update(_wait("INTERDAY", "Not a new order. Nothing beyond the first zone.", state))
        inter["tradeable"] = False
    else:
        entry = float(intra["entry"])
        original = float(intra["stop"])
        risk = abs(entry - original)
        rest = targets[1:]
        listed = " · ".join(
            f"T{index + 2} {round(price, 5)} {abs(price - entry) / risk:.2f}R"
            if risk > 0 else f"T{index + 2} {round(price, 5)}"
            for index, price in enumerate(rest)
        )
        inter.update({
            "chart": "INTERDAY",
            "side": intra.get("side"),
            "reason": "RUNNER",
            "entry": entry,
            "stop": entry,
            "risk_stop": original,
            "target": rest[0],
            "targets": [round(price, 5) for price in rest],
            "r": None,
            "harvest": listed,
            "tradeable": False,
            "state": "SHOWN",
            "market": state,
            "score_on": "M1",
            "decision": "—",
            "higher": "—",
            "next_vote": "NONE",
            "guide": guide,
            "note": f"Not a new order. {listed}. {guide}",
        })
    inter["market"] = state
    live = m1[-1] if m1 else None
    for row in rows:
        row["market"] = state
        if row["chart"] == "INTRADAY":
            if not row.get("side"):
                push = _push(symbol, closed, intraday_zones, spread, area, book)
                if push:
                    push["market"] = state
                    row.clear()
                    row.update(push)
            row["coming"] = _coming(live, intraday_zones, area, symbol, spread, beyond)
        elif row["chart"] == "SWING":
            row["coming"] = _coming(live, swing_zones, area, symbol, spread, wider)
        if row.get("coming") and not row.get("side"):
            row["note"] = str(row["coming"].get("text") or row.get("note") or "")
        if row.get("side") and (row["chart"] != "INTERDAY" or row.get("tradeable")):
            _live_stop(row, bid, ask, symbol)
    for row in rows:
        _limits(row, symbol, spread)
        zone = row.get("zone")
        if zone is not None and row.get("side") and _spent(symbol, str(row.get("chart")), str(row.get("side")), float(zone)):
            _silence(row, "Not a new order. This zone already has one.")
    _gate(rows, book)
    responsive = _failed_test(symbol, m1, m15, area, book, spread, bid, ask)
    if responsive.get("side") and responsive.get("tradeable"):
        _live_stop(responsive, bid, ask, symbol)
        _limits(responsive, symbol, spread)
    rows.append(responsive)
    return rows


def _yen_spot(price: float) -> float:
    """6J is quoted as dollars per 100 yen. The chart is yen per dollar."""
    if 0.3 < price < 1.5:
        return 100.0 / price
    if 0.004 < price < 0.02:
        return 1.0 / price
    return price


def place_yen(book: dict[str, Any] | None, bid: float | None, ask: float | None) -> None:
    """Move the yen future onto the 159 chart. A higher future is a lower yen price."""
    if not isinstance(book, dict):
        return
    converted: dict[str, float] = {}
    for name in ("poc", "vah", "val"):
        value = book.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or float(value) <= 0:
            return
        converted[name] = _yen_spot(float(value))
    if converted["vah"] < converted["val"]:
        converted["vah"], converted["val"] = converted["val"], converted["vah"]
    last = book.get("last")
    if not isinstance(last, (int, float)) or isinstance(last, bool):
        last = book.get("futures_bid")
    shift = 0.0
    if isinstance(last, (int, float)) and not isinstance(last, bool) and isinstance(bid, (int, float)) and isinstance(ask, (int, float)):
        anchor = _yen_spot(float(last))
        if anchor > 10:
            shift = ((float(bid) + float(ask)) / 2.0) - anchor
            if abs(shift) > float(MAX_BASIS.get("USDJPY", 2.0)):
                shift = 0.0
    for name, value in converted.items():
        book[name] = round(value + shift, 5)


def place_value(book: dict[str, Any] | None, symbol: str, bid: float | None, ask: float | None) -> None:
    """Move Sierra's value area onto the CFD. The yen is already moved. A price already on the candle stays."""
    if symbol == "USDJPY" or not isinstance(book, dict):
        return
    if not isinstance(bid, (int, float)) or not isinstance(ask, (int, float)) or isinstance(bid, bool) or isinstance(ask, bool):
        return
    val = _price_field(book, "val")
    poc = _price_field(book, "poc")
    vah = _price_field(book, "vah")
    if val is None or poc is None or vah is None or not (val <= poc <= vah):
        return
    mid = (float(bid) + float(ask)) / 2.0
    if abs(poc - mid) <= _band(symbol):
        return
    last = book.get("last")
    if isinstance(last, bool) or not isinstance(last, (int, float)) or float(last) <= 0:
        return
    shift = mid - float(last)
    if abs(shift) > float(MAX_BASIS.get(symbol, 0.0) or 0.0):
        return
    book["val"] = round(val + shift, 5)
    book["poc"] = round(poc + shift, 5)
    book["vah"] = round(vah + shift, 5)


def _hold_full(side: str, book: dict[str, Any] | None) -> bool:
    """Both clocks with the trade, and no absorption. One clock is not a hold."""
    book = book or {}
    short = book.get("delta_5s")
    longer = book.get("delta_60s")
    if isinstance(short, bool) or isinstance(longer, bool):
        return False
    if not isinstance(short, (int, float)) or not isinstance(longer, (int, float)):
        return False
    if bool(book.get("absorption")):
        return False
    if side == "BUY":
        return short > 0 and longer > 0
    return short < 0 and longer < 0


def _both_against(side: str, book: dict[str, Any] | None) -> bool:
    book = book or {}
    short = book.get("delta_5s")
    longer = book.get("delta_60s")
    if isinstance(short, bool) or isinstance(longer, bool):
        return False
    if not isinstance(short, (int, float)) or not isinstance(longer, (int, float)):
        return False
    if side == "BUY":
        return short < 0 and longer < 0
    return short > 0 and longer > 0


def range_dip(bars: list[dict[str, Any]] | None) -> float | None:
    """Twice the average candle range. Locked by the caller so a fast hour cannot widen it."""
    if not bars:
        return None
    sample = list(bars[-15:-1]) if len(bars) > 15 else list(bars[-14:])
    ranges = []
    for bar in sample:
        try:
            ranges.append(abs(_num(bar, "high") - _num(bar, "low")))
        except (KeyError, TypeError, ValueError):
            continue
    if len(ranges) < 5:
        return None
    average = sum(ranges) / len(ranges)
    if average <= 0:
        return None
    return average * 2.0


LADDER_PAIRS = {"XAUUSD", "WTI", "NAS100"}


def _basis_shift(book: dict[str, Any], symbol: str, bid: float, ask: float) -> float | None:
    """The live futures-to-CFD gap. A gap wider than the pair's cap is not a price."""
    last = book.get("last")
    if isinstance(last, bool) or not isinstance(last, (int, float)) or float(last) <= 0:
        return None
    shift = ((float(bid) + float(ask)) / 2.0) - float(last)
    if abs(shift) > float(MAX_BASIS.get(symbol, 0.0) or 0.0):
        return None
    return shift


def place_marks(book: dict[str, Any] | None, symbol: str, bid: float | None, ask: float | None) -> None:
    """Shift a stack and an unfinished high or low onto the CFD. Other pairs get neither."""
    if not isinstance(book, dict):
        return
    if symbol not in LADDER_PAIRS or not isinstance(bid, (int, float)) or not isinstance(ask, (int, float)):
        book["stack"] = None
        book["unfinished_high"] = None
        book["unfinished_low"] = None
        return
    shift = _basis_shift(book, symbol, float(bid), float(ask))
    if shift is None:
        book["stack"] = None
        book["unfinished_high"] = None
        book["unfinished_low"] = None
        return
    stack = book.get("stack") if isinstance(book.get("stack"), dict) else None
    if stack and isinstance(stack.get("price"), (int, float)) and not isinstance(stack.get("price"), bool):
        stack["price"] = round(float(stack["price"]) + shift, 5)
        book["stack"] = stack
    else:
        book["stack"] = None
    for name in ("unfinished_high", "unfinished_low"):
        value = book.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or float(value) <= 0:
            book[name] = None
        else:
            book[name] = round(float(value) + shift, 5)


def stack_line(symbol: str, side: str, stack: dict[str, Any] | None) -> str:
    """A check on a row that is already a trade. Not a button and not a new signal."""
    if symbol not in LADDER_PAIRS or side not in {"BUY", "SELL"} or not isinstance(stack, dict):
        return ""
    try:
        price = float(stack.get("price"))
    except (TypeError, ValueError):
        return ""
    if price <= 0:
        return ""
    book_side = str(stack.get("side") or "")
    stands = (side == "BUY" and book_side == "bid") or (side == "SELL" and book_side == "ask")
    if not stands:
        return "Stack " + str(price) + ". It is the other way, so this row does not stand."
    if symbol == "NAS100":
        stop = price - 20.0 if side == "BUY" else price + 20.0
        return "Stack " + str(price) + ". This row stands. The stop is 20 points beyond it, at " + str(stop) + "."
    return "Stack " + str(price) + ". This row stands. The stop is just beyond the stack."


def manage_decision(
    *,
    side: str,
    entry: float,
    stop: float | None,
    risk: float | None,
    bid: float,
    ask: float,
    targets: list[float],
    dip: float | None,
    book: dict[str, Any] | None,
    volume: float,
    symbol: str = "",
    magnet: float | None = None,
    magnet_open: bool = False,
) -> dict[str, Any]:
    """The first R is the stop distance. A magnet price stays the target until its missing side prints."""
    prices = []
    for price in targets:
        try:
            prices.append(float(price))
        except (TypeError, ValueError):
            continue
    blank = {"stop": None, "take_profit": None, "bank": False, "line": "", "risk": risk, "dip": dip}
    if side not in {"BUY", "SELL"} or entry <= 0:
        return blank
    if risk is None or risk <= 0:
        if isinstance(stop, (int, float)) and not isinstance(stop, bool):
            gap = abs(entry - float(stop))
            protective = (side == "BUY" and float(stop) < entry) or (side == "SELL" and float(stop) > entry)
            if protective and gap > 0:
                risk = gap
    if risk is None or risk <= 0:
        blank["line"] = "No original stop, so 1R cannot be found."
        blank["risk"] = risk
        return blank
    mark = bid if side == "BUY" else ask
    traveled = (mark - entry) if side == "BUY" else (entry - mark)
    if traveled < 0:
        traveled = 0.0
    band = _band(symbol) if symbol else 0.0
    current = float(stop) if isinstance(stop, (int, float)) and not isinstance(stop, bool) else None

    def better(desired: float | None) -> float | None:
        if desired is None:
            return None
        if side == "BUY" and not desired < mark:
            return None
        if side == "SELL" and not desired > mark:
            return None
        if current is None:
            return desired
        step = max(float(risk) * 1e-6, 1e-8)
        if side == "BUY" and desired <= current + step:
            return None
        if side == "SELL" and desired >= current - step:
            return None
        return desired

    def reached(price: float) -> bool:
        return mark >= price if side == "BUY" else mark <= price

    result = {"stop": None, "take_profit": None, "bank": False, "line": "", "risk": risk, "dip": dip}
    if traveled < float(risk) * 0.90:
        return result
    if traveled < float(risk):
        if _both_against(side, book):
            result["bank"] = True
            result["line"] = "90% of the first R. Both clocks are against the trade. Bank."
            return result
        if _hold_full(side, book):
            result["line"] = "90% of the first R. The book is with the trade. Let the first R print."
            return result
        locked = entry + (traveled * 0.5) if side == "BUY" else entry - (traveled * 0.5)
        result["stop"] = better(locked)
        result["line"] = "90% of the first R. The book is quiet. Half of the open profit is locked."
        return result
    magnet_price = None
    if isinstance(magnet, (int, float)) and not isinstance(magnet, bool) and float(magnet) > 0:
        magnet_price = float(magnet)

    def same_price(left: float, right: float) -> bool:
        return abs(left - right) <= max(band, float(risk) * 1e-6)

    secured = entry
    pending = None
    printed_magnet = False
    for price in prices:
        magnet_here = magnet_price is not None and same_price(price, magnet_price)
        if magnet_here and magnet_open:
            pending = price
            break
        if reached(price):
            secured = price
            if magnet_here:
                printed_magnet = True
        elif pending is None:
            pending = price
            break
    if printed_magnet and not magnet_open:
        result["stop"] = better(magnet_price)
        following = None
        for price in prices:
            if side == "BUY" and price > magnet_price + max(band, float(risk) * 1e-6):
                following = price
                break
            if side == "SELL" and price < magnet_price - max(band, float(risk) * 1e-6):
                following = price
                break
        if _hold_full(side, book) and following is not None:
            result["take_profit"] = following
            result["line"] = "The missing side printed. The take profit leaves " + str(round(magnet_price, 5)) + " for " + str(round(following, 5)) + "."
            return result
        result["bank"] = True
        result["line"] = str(round(magnet_price, 5)) + " stays the target. Bank there."
        return result
    result["stop"] = better(secured)
    if pending is None and prices and reached(prices[-1]):
        result["bank"] = True
        result["line"] = "The last target is reached. Bank the trade."
        return result
    if pending is None:
        result["line"] = "The first R is made. The stop belongs at the entry."
        return result
    span = abs(pending - entry)
    if span <= float(risk) * 1.25:
        close_to = traveled >= span * 0.90
    elif band > 0:
        close_to = abs(mark - pending) <= band
    else:
        close_to = False
    on_magnet = magnet_price is not None and pending is not None and abs(pending - magnet_price) <= max(band, float(risk) * 1e-6)
    trading_magnet = on_magnet and abs(mark - magnet_price) <= max(band, float(risk) * 1e-4)
    following = None
    for price in prices:
        if side == "BUY" and price > pending:
            following = price
            break
        if side == "SELL" and price < pending:
            following = price
            break
    if on_magnet and magnet_open:
        if trading_magnet:
            result["line"] = str(round(magnet_price, 5)) + " is being traded."
        else:
            result["line"] = "The first R is made. The stop is at " + str(round(secured, 5)) + "."
        return result
    if on_magnet:
        if _hold_full(side, book) and following is not None:
            result["take_profit"] = following
            result["line"] = "The missing side printed. The take profit leaves " + str(round(magnet_price, 5)) + " for " + str(round(following, 5)) + "."
            return result
        result["line"] = str(round(magnet_price, 5)) + " stays the target."
        return result
    if not close_to and not trading_magnet:
        result["line"] = "The first R is made. The stop is at " + str(round(secured, 5)) + "."
        return result
    if _both_against(side, book):
        result["bank"] = True
        result["line"] = "Both clocks are against the trade. Bank the rest."
        return result
    if _hold_full(side, book) and following is not None:
        result["take_profit"] = following
        result["line"] = "Let " + str(round(pending, 5)) + " print. The book is with the trade. Next is " + str(round(following, 5)) + "."
        return result
    result["line"] = "The stop stays at " + str(round(secured, 5)) + "."
    return result



def _band(symbol: str, pips: float = 5.0) -> float:
    """Five pips is close enough to bank. The step is the pair's own pip."""
    return float(PIP.get(symbol, 0.0)) * pips


def _price_field(book: dict[str, Any] | None, name: str) -> float | None:
    value = (book or {}).get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if number <= 0:
        return None
    return number


def _value_area(
    book: dict[str, Any] | None,
    bid: float | None = None,
    symbol: str = "",
) -> tuple[float, float, float] | None:
    """Session prices from Sierra. A number on the wrong scale is not a price."""
    val = _price_field(book, "val")
    poc = _price_field(book, "poc")
    vah = _price_field(book, "vah")
    if val is None or poc is None or vah is None or not (val <= poc <= vah) or vah <= val:
        return None
    if isinstance(bid, (int, float)) and not isinstance(bid, bool):
        limit = float(MAX_BASIS.get(symbol, 0.0) or 0.0)
        if limit and abs(float(poc) - float(bid)) > limit:
            return None
    return val, poc, vah


def _use_value_target(row: dict[str, Any], area: tuple[float, float, float] | None) -> None:
    """The other side of value is the first target only when it is closer than the next old level."""
    if area is None or not row.get("side") or row.get("entry") is None or row.get("stop") is None:
        return
    val, _poc, vah = area
    side = str(row["side"])
    entry = float(row["entry"])
    risk = abs(entry - float(row["stop"]))
    other = vah if side == "BUY" else val
    if side == "BUY" and other <= entry:
        return
    if side == "SELL" and other >= entry:
        return
    if risk > 0 and abs(other - entry) <= risk:
        return
    targets = [float(price) for price in (row.get("targets") or [])]
    if not targets and row.get("target") is not None:
        targets = [float(row["target"])]
    other = round(other, 5)
    if targets:
        first = targets[0]
        closer = (other < first) if side == "BUY" else (other > first)
        if not closer:
            return
        targets = [other] + [price for price in targets if abs(price - other) > 1e-6]
    else:
        targets = [other]
    row["targets"] = [round(price, 5) for price in targets[:4]]
    row["target"] = row["targets"][0]
    if risk > 0:
        row["r"] = round(abs(float(row["target"]) - entry) / risk, 2)


def _say(row: dict[str, Any], text: str) -> None:
    note = str(row.get("note") or "").strip()
    if text not in note:
        row["note"] = (note + " " + text).strip()


def _book_agrees(side: str, book: dict[str, Any] | None) -> bool | None:
    """Both clocks, and the 60-second number has to be more than noise."""
    def signed(name: str) -> float | None:
        value = (book or {}).get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        return float(value)

    short = signed("delta_5s")
    longer = signed("delta_60s")
    if short is None or longer is None:
        return None
    if abs(longer) < 10:
        return False
    if side == "BUY":
        return short > 0 and longer > 0
    return short < 0 and longer < 0


def _gate(rows: list[dict[str, Any]], book: dict[str, Any] | None) -> None:
    """One side. The middle of value does not send. The book has to agree."""
    area = _value_area(book)
    primary = None
    for chart in ("INTRADAY", "SWING", "ICEBERG"):
        found = next((row for row in rows if row.get("chart") == chart and row.get("side")), None)
        if found is not None:
            primary = str(found["side"])
            break
    for row in rows:
        if not row.get("side") or row.get("entry") is None:
            continue
        if area is None:
            _say(row, "Value area is not in the Sierra file yet.")
        else:
            val, _poc, vah = area
            close = float(row["entry"])
            band = (vah - val) * 0.10
            if (val + band) < close < (vah - band):
                _say(row, "Price is in the middle of the value area.")
        if primary and str(row["side"]) != primary:
            if row.get("tradeable"):
                _silence(row, "The other side is also on the page.")
            else:
                _say(row, "The other side is also on the page.")
        if bool((book or {}).get("absorption")):
            _say(row, "Absorption is on.")
        agreed = _book_agrees(str(row["side"]), book)
        if agreed is None:
            _say(row, "No 5-second and 60-second book.")
        elif not agreed:
            longer = (book or {}).get("delta_60s")
            if isinstance(longer, (int, float)) and not isinstance(longer, bool) and abs(float(longer)) < 10:
                _say(row, f"The 60-second book is only {longer}.")
            else:
                _say(row, "The book does not agree with this side.")


def _retain(symbol: str, rows: list[dict[str, Any]], bars_by_chart: dict[str, list[dict[str, Any]]]) -> None:
    """Keep a priced signal until its stop or its target. An opposite signal stays visible beside it."""
    state = _load_state()
    active: dict[str, dict[str, Any]] = state.setdefault("active", {})
    changed = False
    for row in rows:
        chart = str(row.get("chart"))
        if chart == "INTERDAY":
            continue
        key = symbol + "|" + chart
        held = active.get(key)
        if chart == "SWING":
            if held:
                active.pop(key, None)
                changed = True
            continue
        fresh = dict(row) if row.get("side") and row.get("entry") is not None and row.get("tradeable") else None
        if held and held.get("reason") in MANUAL and held.get("entry") is not None:
            result, _be, mfe = _score_path(held, _bars_for(held, bars_by_chart), float(BE_MOVE.get(symbol, 0.0)), symbol)
            if result not in ("WIN", "LOSS"):
                if fresh and fresh.get("side") != held.get("side"):
                    clean = {k: v for k, v in fresh.items() if k != "opposite"}
                    previous = held.get("opposite") if isinstance(held.get("opposite"), dict) else None
                    same = (
                        isinstance(previous, dict)
                        and previous.get("side") == clean.get("side")
                        and previous.get("entry") == clean.get("entry")
                        and str(previous.get("time")) == str(clean.get("time"))
                    )
                    if not same:
                        held["opposite"] = clean
                        changed = True
                stored = held.get("opposite") if isinstance(held.get("opposite"), dict) else None
                if stored and stored.get("side") != held.get("side") and stored.get("entry") is not None:
                    opp_result, _, opp_mfe = _score_path(
                        stored, _bars_for(stored, bars_by_chart), float(BE_MOVE.get(symbol, 0.0)), symbol
                    )
                    if opp_result in ("WIN", "LOSS"):
                        held.pop("opposite", None)
                        changed = True
                    else:
                        stored["mfe"] = opp_mfe
                elif stored:
                    held.pop("opposite", None)
                    changed = True
                row.clear()
                row.update(held)
                row["mfe"] = mfe
                row["tradeable"] = bool(held.get("tradeable")) and float(held.get("r") or 0) >= TRADE_R
                row["state"] = "READY" if row["tradeable"] else "SHOWN"
                row["decision"] = held.get("decision") or "HELD"
                continue
            active.pop(key, None)
            changed = True
        if row.get("reason") in MANUAL and row.get("entry") is not None and row.get("tradeable"):
            active[key] = {**row, "symbol": symbol}
            changed = True
        elif held:
            active.pop(key, None)
            changed = True
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
        high = float(level["high"])
        low = float(level["low"])
        pools.append({
            "name": label,
            "price": (high + low) / 2.0,
            "high": high,
            "low": low,
            "kind": "RANGE",
        })
    for chart, count in (("M15", 6), ("H1", 4), ("H4", 4), ("D1", 2)):
        bars = bars_by_chart.get(chart) or []
        if len(bars) < 20:
            continue
        closed = bars[:-1]
        points = swings(closed)
        highs = [point for point in points if point["kind"] == "HIGH"][-count:]
        lows = [point for point in points if point["kind"] == "LOW"][-count:]
        for point in highs + lows:
            bar = closed[int(point["index"])]
            pools.append({
                "name": chart + " SWING " + point["kind"],
                "price": float(point["price"]),
                "high": _num(bar, "high"),
                "low": _num(bar, "low"),
                "kind": point["kind"],
                "time": point.get("time"),
            })
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


def _score_path(row: dict[str, Any], bars: list[dict[str, Any]], be_move: float, symbol: str = "") -> tuple[str, str, float]:
    """The first target is the winner. Within five pips of it is banked, even on the bar that also hits the stop."""
    later = [bar for bar in bars if _time(bar) >= str(row.get("time") or "")]
    entry = float(row["entry"])
    stop = float(row["stop"])
    targets = [float(price) for price in (row.get("targets") or []) if price is not None]
    target = targets[0] if targets else float(row["target"])
    buy = row["side"] == "BUY"
    pad = _band(symbol)
    near = (target - pad) if buy else (target + pad)
    mfe = 0.0
    armed = False
    result = ""
    be_result = ""
    for bar in later:
        favorable = (_num(bar, "high") - entry) if buy else (entry - _num(bar, "low"))
        mfe = max(mfe, favorable)
        hit_stop = _num(bar, "low") <= stop if buy else _num(bar, "high") >= stop
        hit_target = _num(bar, "high") >= near if buy else _num(bar, "low") <= near
        if hit_target:
            result = "WIN"
            be_result = be_result or "WIN"
            break
        if hit_stop:
            result = "LOSS"
            if not armed:
                be_result = "LOSS"
            break
        if not armed and favorable >= be_move:
            armed = True
        if armed:
            back = _num(bar, "low") <= entry if buy else _num(bar, "high") >= entry
            if back and favorable < abs(target - entry):
                be_result = "SCRATCH"
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
        result, be_result, mfe = _score_path(row, _bars_for(row, bars_by_chart), float(BE_MOVE.get(symbol, 0.0)), symbol)
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
            "entry": row.get("entry"), "stop": row.get("stop"), "target": row.get("target"),
            "targets": row.get("targets"), "r": row.get("r"), "be": be_result, "mfe": mfe,
            "next_vote": vote,
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
        seen = state.setdefault("seen_entries", {})
        key = "|".join((symbol, str(row.get("chart")), str(row.get("side")), str(round(float(row["entry"]), 5))))
        if key in if_open or key in seen:
            continue
        seen[key] = now
        if_open[key] = {**row, "symbol": symbol, "opened": now}
        if row.get("chart") in ("INTRADAY", "INTERDAY", "SCALP") and row.get("zone") is not None:
            zone_key = "|".join((symbol, str(row.get("chart")), str(row.get("side")), str(round(float(row["zone"]), 5))))
            state.setdefault("spent_zones", {})[zone_key] = {
                "symbol": symbol,
                "chart": row.get("chart"),
                "side": row.get("side"),
                "zone": float(row["zone"]),
            }
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
