"""Shadow book page. Scores only. Broker writes stay at zero."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from zeus3.v19.shell import card, page

SYMBOLS = ("XAUUSD", "XAGUSD", "WTI", "USOIL", "EURUSD", "USDJPY", "NAS100", "BTCUSD")
ALIASES = {
    "XAUUSD": ("XAUUSD", "XAUUSD.a", "XAUUSD+", "GOLD"),
    "XAGUSD": ("XAGUSD", "XAGUSD.a", "SILVER"),
    "WTI": ("WTI", "USOIL", "XTIUSD", "USOIL.a", "WTI.a", "USOUSD"),
    "USOIL": ("USOIL", "WTI", "XTIUSD", "USOUSD"),
    "EURUSD": ("EURUSD", "EURUSD.a"),
    "USDJPY": ("USDJPY", "USDJPY.a"),
    "NAS100": ("NAS100", "USTEC", "NAS100.a", "US100"),
    "BTCUSD": ("BTCUSD", "BTCUSD.a"),
}


def _bars(mt5, symbol, timeframe, count):
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
    if rates is None:
        return []
    rows = []
    for rate in rates:
        rows.append({
            "time": datetime.fromtimestamp(int(rate["time"]), timezone.utc).replace(tzinfo=None),
            "open": float(rate["open"]),
            "high": float(rate["high"]),
            "low": float(rate["low"]),
            "close": float(rate["close"]),
        })
    return rows


def _resolve(mt5, symbol):
    for name in ALIASES.get(symbol, (symbol,)):
        if mt5.symbol_info(name) is not None:
            mt5.symbol_select(name, True)
            return name
    return None


def _broker_now(m5):
    if m5:
        stamp = m5[-1].get("time")
        if isinstance(stamp, datetime):
            return stamp.replace(tzinfo=None)
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _truthy(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return abs(float(value)) > 0
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _sierra_flow(symbol):
    from gold_shadow.sweep_shadow import OrderFlow
    try:
        from zeus3.legacy_adapters.sierra_flow import V3SierraFlowBridge
        snap = V3SierraFlowBridge().snapshot(symbol)
    except Exception as exc:
        return OrderFlow(stale=True), "SIERRA_UNAVAILABLE " + type(exc).__name__, {}
    state = str(snap.get("evidence_state") or snap.get("state") or "SIERRA_UNAVAILABLE")
    metrics = dict(snap.get("metrics") or {})
    if not (snap.get("verified_live") and snap.get("fresh")):
        return OrderFlow(stale=True), state, metrics
    short = metrics.get("delta_5s")
    longer = metrics.get("delta_60s", metrics.get("delta_15s"))
    flipped = isinstance(short, (int, float)) and isinstance(longer, (int, float)) and short * longer < 0
    flow = OrderFlow(
        absorption=_truthy(metrics.get("absorption")),
        delta_flip_with_bias=flipped,
        stacked_imbalance=_truthy(metrics.get("stacked_imbalance")) or _truthy(metrics.get("dom_imbalance")) or _truthy(metrics.get("mbo_pull_stack")) or _truthy(metrics.get("mbo_imbalance")),
        stale=False,
    )
    return flow, state, metrics


def snapshot():
    from gold_shadow.shadow_book import book_summary, run_shadow_book
    from gold_shadow.shadow_status import broker_status
    from gold_shadow.sweep_shadow import OrderFlow
    account = broker_status()
    scores = []
    if not account.get("connected"):
        return {"ok": True, "broker_writes": 0, "sends_orders": False, "account": account, "scores": scores, "note": "MetaTrader is not connected."}
    try:
        import MetaTrader5 as mt5
    except ImportError:
        return {"ok": False, "broker_writes": 0, "message": "METATRADER5_MODULE_MISSING"}
    preview_flow = OrderFlow(absorption=True, delta_flip_with_bias=True, stacked_imbalance=False, stale=False)
    for symbol in ("XAUUSD", "XAGUSD", "WTI", "EURUSD", "NAS100", "BTCUSD"):
        resolved = _resolve(mt5, symbol)
        if resolved is None:
            scores.append({"symbol": symbol, "reason": "SYMBOL_NOT_ON_BROKER", "rows": []})
            continue
        h1 = _bars(mt5, resolved, mt5.TIMEFRAME_H1, 80)
        h4 = _bars(mt5, resolved, mt5.TIMEFRAME_H4, 80)
        m15 = _bars(mt5, resolved, mt5.TIMEFRAME_M15, 80)
        m5 = _bars(mt5, resolved, mt5.TIMEFRAME_M5, 120)
        now = _broker_now(m5)
        official_flow, sierra_state, sierra_metrics = _sierra_flow(symbol)
        scores.append({
            "symbol": symbol,
            "broker_symbol": resolved,
            "clock": now.strftime("%H:%M"),
            "sierra_state": sierra_state,
            "sierra_metrics": sierra_metrics,
            "official": book_summary(run_shadow_book(symbol, h1, m15, m5, official_flow, now, h4=h4)),
            "structure_preview": book_summary(run_shadow_book(symbol, h1, m15, m5, preview_flow, now, h4=h4)),
            "preview_is_tradable": False,
        })
    return {"ok": True, "broker_writes": 0, "sends_orders": False, "account": account, "scores": scores, "note": "Official waits unless fresh Sierra confirms."}


def _show(metrics, name):
    value = metrics.get(name)
    return "-" if value is None else str(value)


def _metric_line(metrics):
    if not metrics:
        return "<div class='mono muted'>No fresh Sierra numbers on this packet.</div>"
    return "<div class='mono'>absorption " + _show(metrics, "absorption") + " stacked " + _show(metrics, "stacked_imbalance") + " dom " + _show(metrics, "dom_imbalance") + " delta5 " + _show(metrics, "delta_5s") + " delta60 " + _show(metrics, "delta_60s") + " bid " + _show(metrics, "bid_depth") + " ask " + _show(metrics, "ask_depth") + "</div>"


def _rows(items):
    if not items:
        return "<div class='mono muted'>No rows.</div>"
    body = []
    for row in items:
        action = str(row.get("action") or "WAIT")
        color = "good" if action in ("BUY", "SELL") else "muted"
        entry = row.get("entry")
        stop = row.get("stop")
        target = row.get("target")
        body.append("<tr><td>" + str(row.get("strategy_id", "")) + "</td><td class='" + color + "'>" + action + "</td><td>" + str(row.get("reason", "")) + "</td><td>" + ("-" if entry is None else str(entry)) + "</td><td>" + ("-" if stop is None else str(stop)) + "</td><td>" + ("-" if target is None else str(target)) + "</td></tr>")
    return "<table class='mono'><tr><th>STRATEGY</th><th>ACTION</th><th>REASON</th><th>ENTRY</th><th>STOP</th><th>TARGET</th></tr>" + "".join(body) + "</table>"


def render():
    data = snapshot()
    account = data.get("account") or {}
    if account.get("connected"):
        positions = account.get("open_positions") or []
        pos_html = "".join("<div>" + str(p["ticket"]) + " " + str(p["symbol"]) + " " + str(p["side"]) + " " + str(p["lots"]) + " pnl " + str(p["profit"]) + "</div>" for p in positions) or "<div class='muted'>No open positions.</div>"
        pnl = "<div class='big'>" + str(account.get("floating_pnl")) + "</div><div class='mono'>Balance " + str(account.get("balance")) + " Equity " + str(account.get("equity")) + " " + str(account.get("login")) + " " + str(account.get("server")) + "</div>"
    else:
        pos_html = "<div class='mono warn'>" + str(account.get("reason", "NOT CONNECTED")) + "</div>"
        pnl = "<div class='big'>-</div><div class='mono muted'>Log into MetaTrader 5 first.</div>"
    blocks = []
    for score in data.get("scores") or []:
        if score.get("rows") == [] and score.get("reason"):
            blocks.append(card(score["symbol"], "<div class='mono warn'>" + str(score["reason"]) + "</div>"))
            continue
        clock = score.get("clock") or "--:--"
        sierra = score.get("sierra_state") or "SIERRA_UNAVAILABLE"
        blocks.append(card(str(score["symbol"]) + " OFFICIAL broker " + str(clock) + " " + str(sierra), _metric_line(score.get("sierra_metrics") or {}) + _rows(score.get("official") or [])))
        blocks.append(card(str(score["symbol"]) + " STRUCTURE PREVIEW not a trade", _rows(score.get("structure_preview") or [])))
    if not blocks:
        blocks.append(card("SHADOW BOOK", "<div class='mono'>Waiting for a broker connection.</div>"))
    body = card("FLOATING P&L", pnl, 6) + card("OPEN TRADES", "<div class='mono'>" + pos_html + "</div>", 6) + card("AUTHORITY", "<div class='mono warn'>SHADOW ONLY. BROKER WRITES 0. ORDERS ARE NOT SENT</div>") + "".join(blocks)
    return page(title="ZEUS Shadow Book", active="SHADOW", body=body, footer="Four shadow strategies. They score. They do not send orders.")
