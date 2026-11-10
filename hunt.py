"""Background shadow scan. The page reads the last result. Nothing is sent."""

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

EVERY_SECONDS = 20
LOG = Path("shadow_hunt_log.jsonl")
_LOCK = threading.Lock()
_LAST = {"ok": True, "scores": [], "note": "First scan has not finished.", "broker_writes": 0}
_STARTED = False


def latest():
    with _LOCK:
        return dict(_LAST)


def _signature(payload):
    parts = []
    for score in payload.get("scores") or []:
        mbo = score.get("mbo") or {}
        parts.append("|".join((str(score.get("symbol")), str(score.get("clock")), str(mbo.get("sweep_consumed")), str(mbo.get("iceberg_refresh")), str(mbo.get("size_pulled")))))
        for row in score.get("structure_preview") or []:
            parts.append("|".join((str(row.get("strategy_id")), str(row.get("action")), str(row.get("reason")))))
    return "\n".join(parts)


def _remember(payload, previous):
    current = _signature(payload)
    if current == previous:
        return previous
    stamp = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")
    lines = []
    for score in payload.get("scores") or []:
        mbo = score.get("mbo") or {}
        if mbo:
            lines.append(str(score.get("symbol")) + " " + str(mbo.get("reason")) + " sweep " + str(int(bool(mbo.get("sweep_consumed")))) + " iceberg " + str(int(bool(mbo.get("iceberg_refresh")))) + " pulled " + str(int(bool(mbo.get("size_pulled")))))
        for row in score.get("structure_preview") or []:
            if row.get("action") in ("BUY", "SELL") or row.get("reason") not in ("OUTSIDE_SESSION",):
                lines.append(str(score.get("symbol")) + " " + str(row.get("strategy_id")) + " " + str(row.get("action")) + " " + str(row.get("reason")))
    if lines:
        with LOG.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"time": stamp, "lines": lines[:24]}) + "\n")
    return current


def _loop():
    from zeus3.v19.shadow_book_page import snapshot
    previous = ""
    while True:
        try:
            payload = snapshot()
            payload["hunt"] = {"scanned_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds"), "every_seconds": EVERY_SECONDS}
            previous = _remember(payload, previous)
            tail = []
            if LOG.exists():
                tail = [json.loads(line) for line in LOG.read_text(encoding="utf-8").splitlines()[-8:] if line.strip()]
            payload["hunt_log"] = tail
            with _LOCK:
                _LAST.clear()
                _LAST.update(payload)
        except Exception as exc:
            with _LOCK:
                _LAST["note"] = "HUNT_ERROR " + type(exc).__name__ + ": " + str(exc)
        time.sleep(EVERY_SECONDS)


def start():
    global _STARTED
    if _STARTED:
        return
    _STARTED = True
    threading.Thread(target=_loop, name="zeus-shadow-hunt", daemon=True).start()
