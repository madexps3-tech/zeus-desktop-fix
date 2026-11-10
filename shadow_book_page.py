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


def _bars(mt5: Any, symbol: str, timeframe: int, count: int) -> list[dict[str, Any]]:
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


def _resolve(mt5: Any, symbol: str) -> str | None:
    for name in ALIASES.get(symbol, (symbol,)):
        if mt5.symbol_info(name) is not None:
            mt5.symbol_select(name, True)
            return name
    return None


def _broker_now(m5: list[dict[str, Any]]) -> datetime:
    """Session windows are broker-chart hours, not the PC clock."""
    if m5:
        stamp = m5[-1].get("time")
        if isinstance(stamp, datetime):
            return stamp.replace(tzinfo=None)
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return abs(float(value)) > 0
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _sierra_flow(symbol: str) -> tuple[Any, str]:
    """Official gate. Fresh verified Sierra only. Missing data stays stale."""
    from gold_shadow.sweep_shadow import OrderFlow

    try:
        from zeus3.legacy_adapters.sierra_flow import V3SierraFlowBridge
        snap = V3SierraFlowBridge().snapshot(symbol)
    except Exception as exc:
        return OrderFlow(stale=True), f"SIERRA_UNAVAILABLE {type(exc).__name__}"
    state = str(snap.get("evidence_state") or snap.get("state") or "SIERRA_UNAVAILABLE")
    metrics = dict(snap.get("metrics") or {})
    if not (snap.get("verified_live") and snap.get("fresh")):
        return OrderFlow(stale=True), state
    short = metrics.get("delta_5s")
    longer = metrics.get("delta_60s", metrics.get("delta_15s"))
    flipped = (
        isinstance(short, (int, float))
        and isinstance(longer, (int, float))
        and short * longer < 0
    )
    return OrderFlow(
        absorption=_truthy(metrics.get("absorption")),
        delta_flip_with_bias=flipped,
        stacked_imbalance=(
            _truthy(metrics.get("stacked_imbalance"))
            or _truthy(metrics.get("mbo_pull_stack"))
            or _truthy(metrics.get("dom_imbalance"))
            or _truthy(metrics.get("mbo_imbalance"))
        ),
        stale=False,
    ), state


def snapshot() -> dict[str, Any]:
    from gold_shadow.shadow_book import book_summary, run_shadow_book
    from gold_shadow.shadow_status import broker_status
    from gold_shadow.sweep_shadow import OrderFlow

    account = broker_status()
    scores: list[dict[str, Any]] = []
    if not account.get("connected"):
        return {
            "ok": True,
            "broker_writes": 0,
            "sends_orders": False,
            "account": account,
            "scores": scores,
            "note": "MetaTrader is not connected, so there is no live score and no P&L.",
        }
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
        official_flow, sierra_state = _sierra_flow(symbol)
        official = book_summary(run_shadow_book(symbol, h1, m15, m5, official_flow, now, h4=h4))
        preview = book_summary(run_shadow_book(symbol, h1, m15, m5, preview_flow, now, h4=h4))
        scores.append({
            "symbol": symbol,
            "broker_symbol": resolved,
            "clock": now.strftime("%H:%M"),
            "sierra_state": sierra_state,
            "official": official,
            "structure_preview": preview,
            "preview_is_tradable": False,
        })
    return {
        "ok": True,
        "broker_writes": 0,
        "sends_orders": False,
        "account": account,
        "scores": scores,
        "note": "Official waits unless fresh Sierra confirms. Structure preview is not a trade.",
    }


def _rows(items: list[dict[str, Any]]) -> str:
    if not items:
        return "<div class='mono muted'>No rows.</div>"
    body = []
    for row in items:
        action = str(row.get("action") or "WAIT")
        color = "good" if action in ("BUY", "SELL") else "muted"
        body.append(
            "<tr>"
            f"<td>{row.get('strategy_id','')}</td>"
            f"<td class='{color}'>{action}</td>"
            f"<td>{row.get('reason','')}</td>"
            f"<td>{row.get('entry') if row.get('entry') is not None else '\u2014'}</td>"
            f"<td>{row.get('stop') if row.get('stop') is not None else '\u2014'}</td>"
            f"<td>{row.get('target') if row.get('target') is not None else '\u2014'}</td>"
            "</tr>"
        )
    return (
        "<table class='mono'><tr><th>STRATEGY</th><th>ACTION</th><th>REASON</th>"
        "<th>ENTRY</th><th>STOP</th><th>TARGET</th></tr>"
        + "".join(body) + "</table>"
    )


def render() -> str:
    data = snapshot()
    account = data.get("account") or {}
    if account.get("connected"):
        positions = account.get("open_positions") or []
        pos_html = "".join(
            f"<div>{p['ticket']} {p['symbol']} {p['side']} {p['lots']} pnl {p['profit']}</div>"
            for p in positions
        ) or "<div class='muted'>No open positions.</div>"
        pnl = (
            f"<div class='big'>{account.get('floating_pnl')}</div>"
            f"<div class='mono'>Balance {account.get('balance')} \u00b7 Equity {account.get('equity')} \u00b7 "
            f"{account.get('login')} {account.get('server')}</div>"
        )
    else:
        pos_html = f"<div class='mono warn'>{account.get('reason','NOT CONNECTED')}</div>"
        pnl = "<div class='big'>\u2014</div><div class='mono muted'>Log into MetaTrader 5 first.</div>"

    blocks = []
    for score in data.get("scores") or []:
        if score.get("rows") == [] and score.get("reason"):
            blocks.append(card(score["symbol"], f"<div class='mono warn'>{score['reason']}</div>"))
            continue
        clock = score.get("clock") or "--:--"
        sierra = score.get("sierra_state") or "SIERRA_UNAVAILABLE"
        blocks.append(card(
            f"{score['symbol']} OFFICIAL \u00b7 broker {clock} \u00b7 {sierra}",
            _rows(score.get("official") or []),
        ))
        blocks.append(card(
            f"{score['symbol']} STRUCTURE PREVIEW \u00b7 not a trade",
            _rows(score.get("structure_preview") or []),
        ))
    if not blocks:
        blocks.append(card("SHADOW BOOK", "<div class='mono'>Waiting for a broker connection.</div>"))
    body = (
        card("FLOATING P&L", pnl, 6)
        + card("OPEN TRADES", f"<div class='mono'>{pos_html}</div>", 6)
        + card("AUTHORITY", "<div class='mono warn'>SHADOW ONLY \u00b7 BROKER WRITES 0 \u00b7 ORDERS ARE NOT SENT</div>")
        + "".join(blocks)
    )
    return page(
        title="ZEUS Shadow Book",
        active="SHADOW",
        body=body,
        footer="Four shadow strategies. They score. They do not send orders.",
    )
