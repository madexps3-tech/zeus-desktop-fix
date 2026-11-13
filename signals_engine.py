"""One signal per chart. A close beyond a swing is a break. A wick is a sweep."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

PAIRS = ("XAUUSD", "XAGUSD", "NAS100", "BTCUSD", "EURUSD", "USDJPY", "WTI")
CHARTS = ("M1", "M5", "M15", "M30", "H1", "H4", "D1")
MIN_R = 0.5
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
        return "WAIT", "The pullback has not held yet."
    delta = book.get("delta_5s")
    if book.get("iceberg_refresh"):
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


def build_rows(
    symbol: str,
    bars_by_chart: dict[str, list[dict[str, Any]]],
    book: dict[str, Any] | None,
    spread: float,
    levels: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for chart in CHARTS:
        bars = bars_by_chart.get(chart) or []
        closed = bars[:-1]
        points = swings(closed) if len(closed) >= 20 else []
        state = market_state(points) if points else "RANGE"
        row = signal_for_chart(chart, bars)
        if row is None:
            row = breakout_watch(chart, bars, levels)
        if row is None:
            rows.append({
                "chart": chart, "side": "", "reason": "NO_SIGNAL", "r": None,
                "decision": "—", "note": "No 0.5R structure on this chart.",
                "state": state, "tradeable": False,
            })
            continue
        row["state"] = state
        if row.get("reason") == "POTENTIAL":
            row["decision"] = "POTENTIAL"
            if book and book.get("size_pulled"):
                row["note"] = str(row.get("note") or "") + " Orders were pulled on this pair. The file does not say at which price."
            rows.append(row)
            continue
        decision, note = pair_flow(symbol, book, bool(row.get("ready")))
        reward = abs(float(row["target"]) - float(row["entry"]))
        if spread > 0 and reward > 0 and spread >= reward * 0.5:
            note = "The spread is at least half of this target. " + note
            row["spread_eats_target"] = True
        else:
            row["spread_eats_target"] = False
        row["decision"] = decision
        row["note"] = note
        row["spread"] = spread
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
            state_word = str((by_chart.get(chart) or {}).get("state") or "")
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
    return rows


def _retain(symbol: str, rows: list[dict[str, Any]], bars_by_chart: dict[str, list[dict[str, Any]]]) -> None:
    """Keep a priced signal until its stop or its target. A quiet candle does not erase it."""
    state = _load_state()
    active: dict[str, dict[str, Any]] = state.setdefault("active", {})
    changed = False
    for row in rows:
        chart = str(row.get("chart"))
        key = symbol + "|" + chart
        if row.get("tradeable") and row.get("entry") is not None:
            active[key] = {**row, "symbol": symbol}
            changed = True
            continue
        held = active.get(key)
        if not held:
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
        row["tradeable"] = True
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
