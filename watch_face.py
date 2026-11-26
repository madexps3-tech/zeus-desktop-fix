from pathlib import Path
"""The phone chart. No order button. watch_wire.py writes this into the phone page."""
PY = r'''
_VIEW_CACHE = {}


def _view_number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def _view_public(payload):
    flow = payload.get("flow") if isinstance(payload.get("flow"), dict) else {}
    candles = []
    for bar in (payload.get("candles") or [])[-180:]:
        if not isinstance(bar, dict):
            continue
        candles.append({
            "time": bar.get("time"),
            "open": _view_number(bar.get("open")),
            "high": _view_number(bar.get("high")),
            "low": _view_number(bar.get("low")),
            "close": _view_number(bar.get("close")),
        })
    pools = []
    for level in payload.get("pools") or []:
        if not isinstance(level, dict):
            continue
        pools.append({
            "name": level.get("name") or "",
            "kind": level.get("kind") or "",
            "price": _view_number(level.get("price")),
            "high": _view_number(level.get("high")),
            "low": _view_number(level.get("low")),
            "time": level.get("time"),
        })
    bands = []
    for level in payload.get("m5") or []:
        if isinstance(level, dict):
            bands.append({"name": level.get("name") or "", "kind": level.get("kind") or "", "price": _view_number(level.get("price"))})
    ladder_in = payload.get("ladder") if isinstance(payload.get("ladder"), dict) else {}
    levels = []
    for level in (ladder_in.get("levels") or [])[:40]:
        if isinstance(level, dict):
            levels.append({
                "price": _view_number(level.get("price")),
                "bid_contracts": _view_number(level.get("bid_contracts")) or 0,
                "ask_contracts": _view_number(level.get("ask_contracts")) or 0,
            })
    icebergs = []
    for item in ladder_in.get("icebergs") or []:
        if isinstance(item, dict):
            icebergs.append({"price": _view_number(item.get("price")), "side": item.get("side") or ""})
    rows = []
    for row in payload.get("rows") or []:
        if not isinstance(row, dict):
            continue
        rows.append({
            "chart": row.get("chart") or "",
            "side": row.get("side") or "",
            "entry": row.get("entry"),
            "stop": row.get("stop"),
            "target": row.get("target"),
            "targets": [price for price in (row.get("targets") or []) if price is not None][:4],
            "state": row.get("state") or "",
            "note": str(row.get("note") or row.get("reason") or ""),
            "late": bool(row.get("late")),
            "push": bool(row.get("push")),
        })
    feed_in = payload.get("feed") if isinstance(payload.get("feed"), dict) else {}
    day = flow.get("dom_day") if isinstance(flow.get("dom_day"), dict) else None
    return {
        "ok": True,
        "symbol": payload.get("symbol"),
        "label": payload.get("label") or payload.get("symbol"),
        "chart": payload.get("chart"),
        "candles": candles,
        "quote": payload.get("quote") or {},
        "spread": payload.get("spread"),
        "market": payload.get("market") or "",
        "pools": pools,
        "m5": bands,
        "rows": rows,
        "flow": {
            "delta_5s": flow.get("delta_5s"),
            "delta_60s": flow.get("delta_60s"),
            "stepping": flow.get("stepping") or "",
            "walk": flow.get("walk") or "",
            "poc": flow.get("poc"),
            "vah": flow.get("vah"),
            "val": flow.get("val"),
            "unfinished_high": flow.get("unfinished_high"),
            "unfinished_low": flow.get("unfinished_low"),
            "absorption": bool(flow.get("absorption")),
            "iceberg": bool(flow.get("iceberg")),
            "iceberg_price": flow.get("iceberg_price"),
            "iceberg_side": flow.get("iceberg_side"),
            "pulled": bool(flow.get("pulled")),
            "sweep_consumed": bool(flow.get("sweep_consumed")),
            "dom_day": day,
            "note": str(flow.get("note") or ""),
        },
        "ladder": {
            "shown": bool(ladder_in.get("shown")),
            "shift": ladder_in.get("shift"),
            "reason": str(ladder_in.get("reason") or ""),
            "levels": levels,
            "icebergs": icebergs,
        },
        "feed": {
            "quote_age": feed_in.get("quote_age"),
            "quote_stale": bool(feed_in.get("quote_stale")),
            "candles_stale": bool(feed_in.get("candles_stale")),
            "session": feed_in.get("session") or "",
            "line": feed_in.get("line") or "",
        },
    }


async def watch_view(request):
    token = _cookie(request.headers.get("Cookie", ""), "zeus_watch")
    if not token:
        return web.json_response({"ok": False, "message": ""}, status=401)
    name, message = _name_for(token)
    if not name:
        return web.json_response({"ok": False, "message": message}, status=401)
    symbol = str(request.query.get("symbol") or "XAUUSD").upper()
    chart = str(request.query.get("chart") or "M1").upper()
    if symbol not in PAIRS or chart not in ("M1", "M5", "M15", "M30", "H1", "H4", "D1"):
        return web.json_response({"ok": False, "message": "That symbol is not on this page."}, status=404)
    if _HOST is None:
        return web.json_response({"ok": False, "message": "Zeus is not ready."}, status=503)
    import time as _time
    key = symbol + "|" + chart
    hit = _VIEW_CACHE.get(key)
    if hit and _time.monotonic() - hit[0] < 3:
        return web.json_response(hit[1])
    from zeus3.v19.signals_page import _LOCK as page_lock, _payload
    locked = page_lock.acquire(timeout=8)
    if not locked:
        if hit:
            return web.json_response(hit[1])
        return web.json_response({"ok": False, "message": "Zeus is busy."}, status=503)
    try:
        payload = _payload(symbol, chart, _HOST, False)
    except Exception as exc:
        return web.json_response({"ok": False, "message": str(exc)}, status=503)
    finally:
        page_lock.release()
    public = _view_public(payload if isinstance(payload, dict) else {})
    _VIEW_CACHE[key] = (_time.monotonic(), public)
    return web.json_response(public)
'''


def apply(watch):
    layout_path = Path(__file__).resolve().with_name("watch_layout.txt")
    if not layout_path.exists():
        print("Could not find the phone chart layout.", flush=True)
        raise SystemExit(1)
    layout = layout_path.read_text(encoding="utf-8")
    body = watch.read_text(encoding="utf-8")
    nl = "\r\n" if "\r\n" in body else "\n"
    route = 'app.router.add_get("/board", watch_board)'
    added = 'app.router.add_get("/view", watch_view)' + nl + "        " + route
    if "watch_view" not in body and route in body:
        body = body.replace(route, added, 1)
    cut = body.find("\nPHONE = ")
    if "def watch_view" not in body:
        block = nl + nl + PY.strip() + nl
        if cut >= 0:
            body = body[:cut] + block + body[cut:]
            cut = body.find("\nPHONE = ")
        else:
            body += block
    if "id='cv'" not in body:
        if cut >= 0:
            body = body[:cut]
        body = body.rstrip() + nl + nl + layout.strip() + nl
    watch.write_text(body, encoding="utf-8")
    print("Phone chart added.", flush=True)
