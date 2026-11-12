"""One signal per chart. A close beyond a swing is a break. A wick is a sweep."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PAIRS = ("XAUUSD", "XAGUSD", "NAS100", "BTCUSD", "EURUSD", "USDJPY", "WTI")
CHARTS = ("M1", "M5", "M15", "M30", "H1", "H4", "D1")
MIN_R = 0.5
WING = 2
LOG = Path("signal_research.jsonl")
STATE = Path("signal_research_state.json")
FLOW_PAIRS = {"XAUUSD", "NAS100", "WTI"}


def _num(bar: dict[str, Any], name: str) -> float:
    return float(bar[name])


def _time(bar: dict[str, Any]) -> str:
    return str(bar.get("time") or "")


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


def _session(stamp: str) -> str:
    try:
        hour = datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(timezone.utc).hour
    except ValueError:
        return "UNKNOWN"
    if hour < 7:
        return "ASIA"
    if hour < 12:
        return "LONDON"
    if hour < 21:
        return "NEW_YORK"
    return "LATE"


def _row(
    chart: str,
    side: str,
    reason: str,
    entry: float,
    stop: float,
    target: float,
    when: str,
    ready: bool,
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
        "session": _session(when),
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
    prior_high = highs[-2] if len(highs) > 1 else last_high
    prior_low = lows[-2] if len(lows) > 1 else last_low

    swept_high = _num(last, "high") > last_high["price"] and close < last_high["price"]
    swept_low = _num(last, "low") < last_low["price"] and close > last_low["price"]
    if trend == "UP" and close < last_low["price"] and swept_low:
        return _row(chart, "SELL", "MSS", close, _num(last, "high"), last_low["price"], _time(last), True)
    if trend == "DOWN" and close > last_high["price"] and swept_high:
        return _row(chart, "BUY", "MSS", close, _num(last, "low"), last_high["price"], _time(last), True)
    if swept_high:
        return _row(chart, "SELL", "SWEEP", close, _num(last, "high"), last_low["price"], _time(last), True)
    if swept_low:
        return _row(chart, "BUY", "SWEEP", close, _num(last, "low"), last_high["price"], _time(last), True)

    if trend == "UP" and close > last_high["price"]:
        ready = _num(last, "low") <= last_high["price"] and close > last_high["price"]
        return _row(chart, "BUY", "BOS", last_high["price"], prior_low["price"], _num(last, "high"), _time(last), ready)
    if trend == "DOWN" and close < last_low["price"]:
        ready = _num(last, "high") >= last_low["price"] and close < last_low["price"]
        return _row(chart, "SELL", "BOS", last_low["price"], prior_high["price"], _num(last, "low"), _time(last), ready)
    if trend == "UP" and close < last_low["price"]:
        return _row(chart, "SELL", "CHoCH", close, last_high["price"], last_low["price"], _time(last), True)
    if trend == "DOWN" and close > last_high["price"]:
        return _row(chart, "BUY", "CHoCH", close, last_low["price"], last_high["price"], _time(last), True)
    if trend == "RANGE":
        span = last_high["price"] - last_low["price"]
        if span <= 0:
            return None
        if close >= last_high["price"] - span * 0.2:
            return _row(chart, "SELL", "RANGE", last_high["price"], last_high["price"] + span * 0.1, last_low["price"], _time(last), close >= last_high["price"])
        if close <= last_low["price"] + span * 0.2:
            return _row(chart, "BUY", "RANGE", last_low["price"], last_low["price"] - span * 0.1, last_high["price"], _time(last), close <= last_low["price"])
    return None


def _flow_decision(symbol: str, book: dict[str, Any] | None, ready: bool) -> tuple[str, str]:
    if not ready:
        return "WAIT", "The pullback has not held yet."
    if symbol not in FLOW_PAIRS:
        return "NO_BOOK", "This pair has no live book. The structure is still shown."
    book = book or {}
    if not book.get("fresh"):
        return "NO_BOOK", str(book.get("reason") or "The live book is not fresh.")
    if book.get("size_pulled") and not book.get("iceberg_refresh"):
        return "SKIP", "The orders at this price were pulled."
    if book.get("iceberg_refresh") or book.get("sweep_consumed"):
        return "TAKE", "The live book is defending this price."
    return "WAIT", "The book is live, but it is not defending this price."


def build_rows(
    symbol: str,
    bars_by_chart: dict[str, list[dict[str, Any]]],
    book: dict[str, Any] | None,
    spread: float,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for chart in CHARTS:
        row = signal_for_chart(chart, bars_by_chart.get(chart) or [])
        if row is None:
            rows.append({"chart": chart, "side": "", "reason": "NO_SIGNAL", "r": None, "decision": "—", "note": "No 0.5R structure on this chart."})
            continue
        decision, note = _flow_decision(symbol, book, bool(row["ready"]))
        reward = abs(row["target"] - row["entry"])
        if spread > 0 and reward > 0 and spread >= reward * 0.5:
            note = "The spread is at least half of this target. " + note
            row["spread_eats_target"] = True
        else:
            row["spread_eats_target"] = False
        row["decision"] = decision
        row["note"] = note
        row["spread"] = spread
        rows.append(row)
    by_chart = {row["chart"]: row for row in rows}
    for row in rows:
        if not row.get("side"):
            row["higher"] = "—"
            continue
        higher = []
        for chart in ("H4", "D1"):
            other = by_chart.get(chart) or {}
            if chart == row["chart"] or not other.get("side"):
                continue
            higher.append("WITH " + chart if other["side"] == row["side"] else "AGAINST " + chart)
        row["higher"] = ", ".join(higher) or "—"
    return rows


def _load_state() -> dict[str, Any]:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"open": {}, "summary": {}}


def _save_state(state: dict[str, Any]) -> None:
    STATE.write_text(json.dumps(state), encoding="utf-8")


def _append(row: dict[str, Any]) -> None:
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")


def record(symbol: str, rows: list[dict[str, Any]], bars_by_chart: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Write the signal when it appears. Score the stop and the target later."""
    state = _load_state()
    summary: dict[str, dict[str, int]] = state.setdefault("summary", {})
    open_rows: dict[str, dict[str, Any]] = state.setdefault("open", {})
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    for row in rows:
        if not row.get("side"):
            continue
        key = "|".join((symbol, row["chart"], row["reason"], row["side"], str(row["entry"]), str(row["time"])))
        if key in open_rows:
            continue
        open_rows[key] = {**row, "symbol": symbol, "opened": now, "scored": False}
        bucket = summary.setdefault(row["reason"], {"wins": 0, "losses": 0, "expired": 0, "open": 0})
        bucket["open"] = int(bucket.get("open") or 0) + 1
        _append({"event": "SIGNAL", "symbol": symbol, "at": now, **row})
    done = []
    for key, row in open_rows.items():
        bars = bars_by_chart.get(str(row.get("chart"))) or []
        later = [bar for bar in bars if _time(bar) > str(row.get("time"))]
        result = ""
        for bar in later:
            hit_stop = _num(bar, "low") <= float(row["stop"]) if row["side"] == "BUY" else _num(bar, "high") >= float(row["stop"])
            hit_target = _num(bar, "high") >= float(row["target"]) if row["side"] == "BUY" else _num(bar, "low") <= float(row["target"])
            if hit_stop:
                result = "LOSS"
                break
            if hit_target:
                result = "WIN"
                break
        if not result and len(later) >= 40:
            result = "EXPIRED"
        if not result:
            continue
        reason = str(row.get("reason"))
        bucket = summary.setdefault(reason, {"wins": 0, "losses": 0, "expired": 0, "open": 0})
        bucket["open"] = max(0, int(bucket.get("open") or 0) - 1)
        if result == "WIN":
            bucket["wins"] = int(bucket.get("wins") or 0) + 1
        elif result == "LOSS":
            bucket["losses"] = int(bucket.get("losses") or 0) + 1
        else:
            bucket["expired"] = int(bucket.get("expired") or 0) + 1
        _append({"event": result, "symbol": symbol, "at": now, "chart": row.get("chart"), "reason": reason, "side": row.get("side"), "r": row.get("r")})
        done.append(key)
    for key in done:
        open_rows.pop(key, None)
    _save_state(state)
    return summary
