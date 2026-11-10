"""MBO gate and a shadow $10k account. Nothing here sends an order."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

VIRTUAL_EQUITY = 10_000.0
RISK_FRACTION = 0.02
RISK_DOLLARS = VIRTUAL_EQUITY * RISK_FRACTION
FRESH_SECONDS = 20.0

MBO_ROOT = {
    "XAUUSD": "GC",
    "NAS100": "NQ",
    "WTI": "CL",
}


def _roots():
    found = []
    for key in ("ZEUS_SIERRA_DATA_DIR", "SIERRA_DATA_FOLDER", "SIERRACHART_DATA_DIR"):
        raw = os.environ.get(key)
        if raw:
            found.append(Path(raw))
    if os.name == "nt":
        found.extend((Path(r"C:\SierraChart\Data"), Path(r"C:\SierraChart_2\Data"), Path(r"C:\SierraChart2\Data")))
        profile = os.environ.get("USERPROFILE")
        if profile:
            home = Path(profile)
            found.extend((home / "SierraChart" / "Data", home / "Documents" / "SierraChart" / "Data"))
        try:
            found.extend(Path("C:/").glob("SierraChart*/Data"))
        except OSError:
            pass
    return found


def read_mbo(cfd_symbol):
    root = MBO_ROOT.get(cfd_symbol.upper())
    if root is None:
        return {"root": None, "fresh": False, "reason": "MBO_NOT_USED"}
    newest = None
    for folder in _roots():
        path = folder / ("zeus_mbo_" + root + ".json")
        if not path.is_file():
            continue
        if newest is None or path.stat().st_mtime > newest.stat().st_mtime:
            newest = path
    if newest is None:
        return {"root": root, "fresh": False, "reason": "MBO_NOT_CONNECTED"}
    age = datetime.now(timezone.utc).timestamp() - newest.stat().st_mtime
    try:
        payload = json.loads(newest.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {"root": root, "fresh": False, "reason": "MBO_BAD_PACKET"}
    fresh = age <= FRESH_SECONDS
    return {
        "root": root,
        "fresh": fresh,
        "age_seconds": round(age, 1),
        "sweep_consumed": bool(payload.get("sweep_consumed")),
        "iceberg_refresh": bool(payload.get("iceberg_refresh")),
        "size_pulled": bool(payload.get("size_pulled")),
        "reason": "MBO_LIVE" if fresh else "MBO_STALE",
    }


def lot_from_ticks(info, entry, stop):
    if entry is None or stop is None or info is None:
        return {"lots": None, "reason": "NO_PRICE"}
    tick = float(getattr(info, "trade_tick_size", 0) or 0)
    value = float(getattr(info, "trade_tick_value", 0) or 0)
    step = float(getattr(info, "volume_step", 0) or 0)
    minimum = float(getattr(info, "volume_min", 0) or 0)
    if tick <= 0 or value <= 0 or step <= 0 or minimum <= 0:
        return {"lots": None, "reason": "NO_TICK_SPEC", "tick": tick, "tick_value": value}
    ticks = abs(float(entry) - float(stop)) / tick
    loss_per_lot = ticks * value
    if loss_per_lot <= 0:
        return {"lots": None, "reason": "NO_TICK_SPEC", "tick": tick, "tick_value": value}
    raw = RISK_DOLLARS / loss_per_lot
    lots = round(int(raw / step) * step, 8)
    if lots < minimum:
        return {"lots": None, "reason": "LOT_BELOW_MINIMUM", "tick": tick, "tick_value": value, "loss_per_lot": round(loss_per_lot, 2)}
    return {"lots": lots, "reason": "SIZED", "tick": tick, "tick_value": value, "loss_per_lot": round(loss_per_lot, 2), "risk_dollars": round(lots * loss_per_lot, 2)}


def gate(action, reason, mbo):
    if action not in ("BUY", "SELL"):
        return {"action": action, "reason": reason, "taken": False}
    if not mbo.get("fresh"):
        return {"action": action, "reason": str(mbo.get("reason") or "MBO_NOT_CONNECTED"), "taken": False}
    if mbo.get("size_pulled") and not mbo.get("sweep_consumed"):
        return {"action": "WAIT", "reason": "MBO_SIZE_PULLED", "taken": False}
    if mbo.get("sweep_consumed") or mbo.get("iceberg_refresh"):
        return {"action": action, "reason": "MBO_CONFIRMED", "taken": True}
    return {"action": action, "reason": "MBO_SWEEP_NOT_CONFIRMED", "taken": False}


def _key(row):
    return "|".join((str(row.get("symbol")), str(row.get("strategy_id")), str(row.get("action")), str(row.get("entry"))))


def update_ledger(path, rows):
    try:
        book = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        book = {"trades": []}
    trades = list(book.get("trades") or [])
    known = {_key(row) for row in trades}
    quotes = {str(row.get("symbol")): row for row in rows if row.get("bid") is not None or row.get("ask") is not None}
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    for row in rows:
        if not row.get("taken") or _key(row) in known:
            continue
        trades.append({**row, "status": "OPEN", "opened": now, "pnl": 0.0})
        known.add(_key(row))
    for trade in trades:
        live = quotes.get(str(trade.get("symbol")))
        if live is not None:
            trade["bid"] = live.get("bid")
            trade["ask"] = live.get("ask")
    closed = 0.0
    floating = 0.0
    for trade in trades:
        if trade.get("status") != "OPEN":
            closed += float(trade.get("pnl") or 0)
            continue
        entry = float(trade["entry"])
        stop = float(trade["stop"])
        target = float(trade["target"])
        tick = float(trade["tick"])
        value = float(trade["tick_value"])
        lots = float(trade["lots"])
        price = trade.get("bid") if trade["action"] == "BUY" else trade.get("ask")
        if price is None:
            continue
        price = float(price)
        if trade["action"] == "BUY":
            hit_stop = price <= stop
            hit_target = price >= target
            signed = price - entry
        else:
            hit_stop = price >= stop
            hit_target = price <= target
            signed = entry - price
        pnl = round((signed / tick) * value * lots, 2)
        if hit_stop:
            trade["status"] = "STOP"
            trade["pnl"] = round((((stop - entry) if trade["action"] == "BUY" else (entry - stop)) / tick) * value * lots, 2)
            trade["closed"] = now
            closed += float(trade["pnl"])
        elif hit_target:
            trade["status"] = "TARGET"
            trade["pnl"] = round((((target - entry) if trade["action"] == "BUY" else (entry - target)) / tick) * value * lots, 2)
            trade["closed"] = now
            closed += float(trade["pnl"])
        else:
            trade["pnl"] = pnl
            floating += pnl
    path.write_text(json.dumps({"trades": trades[-200:]}, indent=2), encoding="utf-8")
    return {"equity": round(VIRTUAL_EQUITY + closed + floating, 2), "closed_pnl": round(closed, 2), "floating_pnl": round(floating, 2), "risk_dollars": RISK_DOLLARS, "trades": trades[-30:]}
