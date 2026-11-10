from pathlib import Path
import sys

root = Path(sys.argv[1].strip().strip('"').rstrip("\\/"))
sweep_path = root / "src" / "gold_shadow" / "sweep_shadow.py"
book_path = root / "src" / "gold_shadow" / "shadow_book.py"
mbo_path = root / "src" / "gold_shadow" / "mbo_book.py"
page_path = root / "src" / "zeus3" / "v19" / "shadow_book_page.py"
web_path = root / "src" / "zeus3" / "v19" / "web.py"

sweep = sweep_path.read_text(encoding="utf-8")
if "scalp" not in sweep:
    sweep = sweep.replace(
        "    strategy_id: str = STRATEGY_ID,\n) -> ShadowSignal:",
        "    strategy_id: str = STRATEGY_ID,\n    scalp: bool = False,\n) -> ShadowSignal:",
        1,
    )
old = (
    "    bias = bias_from_swings(h1)\n"
    "    if bias == \"UNCLEAR\":\n"
    "        return _wait(symbol, \"H1_BIAS_UNCLEAR\", orderflow, strategy_id)\n"
    "    if h4 is not None and len(h4) >= 20:\n"
    "        higher = bias_from_swings(h4)\n"
    "        if higher not in (\"UNCLEAR\", bias):\n"
    "            return _wait(symbol, \"H4_DISAGREES\", orderflow, strategy_id)\n\n"
    "    side = \"BUY\" if bias == \"BULL\" else \"SELL\"\n"
)
new = (
    "    bias = bias_from_swings(h1)\n"
    "    if not scalp:\n"
    "        if bias == \"UNCLEAR\":\n"
    "            return _wait(symbol, \"H1_BIAS_UNCLEAR\", orderflow, strategy_id)\n"
    "        if h4 is not None and len(h4) >= 20:\n"
    "            higher = bias_from_swings(h4)\n"
    "            if higher not in (\"UNCLEAR\", bias):\n"
    "                return _wait(symbol, \"H4_DISAGREES\", orderflow, strategy_id)\n"
    "        sides = (\"BUY\",) if bias == \"BULL\" else (\"SELL\",)\n"
    "    else:\n"
    "        sides = (\"BUY\", \"SELL\") if bias == \"UNCLEAR\" else ((\"BUY\",) if bias == \"BULL\" else (\"SELL\",))\n"
)
if old in sweep:
    sweep = sweep.replace(old, new, 1)
    sweep = sweep.replace(
        "    if len(m5) < 10 or len(m15) < 15:\n        return _wait(symbol, \"NOT_ENOUGH_BARS\", orderflow, strategy_id)\n\n    fresh = None\n    for _, level in _candidate_levels(m15, side, spec[\"equal\"]):",
        "    if len(m5) < 10 or len(m15) < 15:\n        return _wait(symbol, \"NOT_ENOUGH_BARS\", orderflow, strategy_id)\n\n    fallback = _wait(symbol, \"NO_FRESH_SWEEP_RECLAIM\", orderflow, strategy_id)\n    chosen = None\n    chosen_at = -1\n    for side in sides:\n        fresh = None\n        for _, level in _candidate_levels(m15, side, spec[\"equal\"]):",
        1,
    )
    sweep = sweep.replace("        if found is None:\n            continue\n        if found[\"reclaim_index\"] < len(m5) - 2:\n            continue", "        if found is None or found[\"reclaim_index\"] < len(m5) - 2:\n            continue", 1)
    sweep = sweep.replace("            return _wait(symbol, \"CHASE\", orderflow, strategy_id)", "            fallback = _wait(symbol, \"CHASE\", orderflow, strategy_id)\n            continue")
    sweep = sweep.replace("            return _wait(symbol, \"ALREADY_INVALID\", orderflow, strategy_id)", "            fallback = _wait(symbol, \"ALREADY_INVALID\", orderflow, strategy_id)\n            continue")
    sweep = sweep.replace("        return _wait(symbol, \"STOP_INSIDE_NOISE\", orderflow, strategy_id)", "        fallback = _wait(symbol, \"STOP_INSIDE_NOISE\", orderflow, strategy_id)\n        continue")
    sweep = sweep.replace("        return _wait(symbol, \"STOP_TOO_WIDE\", orderflow, strategy_id)", "        fallback = _wait(symbol, \"STOP_TOO_WIDE\", orderflow, strategy_id)\n        continue")
    sweep = sweep.replace("                return _wait(symbol, \"LOT_BELOW_MINIMUM\", orderflow, strategy_id)", "                fallback = _wait(symbol, \"LOT_BELOW_MINIMUM\", orderflow, strategy_id)\n                continue")
    sweep = sweep.replace("    return ShadowSignal(\n        strategy_id=strategy_id,\n        action=side,", "        if int(fresh[\"reclaim_index\"]) < chosen_at:\n            continue\n        chosen_at = int(fresh[\"reclaim_index\"])\n        chosen = ShadowSignal(\n        strategy_id=strategy_id,\n        action=side,", 1)
    sweep = sweep.replace(
        "            \"stale\": orderflow.stale,\n        },\n    )\n",
        "            \"stale\": orderflow.stale,\n        },\n        )\n    return chosen if chosen is not None else fallback\n",
        1,
    )
    sweep_path.write_text(sweep, encoding="utf-8")

book = book_path.read_text(encoding="utf-8")
if "scalp=True" not in book:
    book = book.replace("strategy_id=STRATEGY_ID,\n    )", "strategy_id=STRATEGY_ID, scalp=True,\n    )", 1)
    book = book.replace("strategy_id=TOKYO_ID,\n    )", "strategy_id=TOKYO_ID,\n        scalp=True,\n    )", 1)
    book = book.replace(
        "    if h4 is not None and len(h4) >= 20:\n        higher = bias_from_swings(h4)\n        if higher not in (\"UNCLEAR\", bias):\n            return _wait(symbol, \"H4_DISAGREES\", orderflow, PULLBACK_ID)\n",
        "",
        1,
    )
    book_path.write_text(book, encoding="utf-8")

mbo = mbo_path.read_text(encoding="utf-8")
if "def latch(" not in mbo:
    mbo = mbo.replace(
        "def lot_from_ticks(",
        "_LATCH = {}\n\n\ndef latch(mbo, bar_time):\n"
        "    root = mbo.get(\"root\")\n"
        "    if not root:\n"
        "        return mbo\n"
        "    bar = bar_time.isoformat() if hasattr(bar_time, \"isoformat\") else str(bar_time or \"\")\n"
        "    held = _LATCH.get(str(root))\n"
        "    if held is None or held.get(\"bar\") != bar:\n"
        "        held = {\"bar\": bar, \"sweep_consumed\": False, \"iceberg_refresh\": False, \"size_pulled\": False}\n"
        "    if mbo.get(\"fresh\"):\n"
        "        held[\"sweep_consumed\"] = bool(held[\"sweep_consumed\"] or mbo.get(\"sweep_consumed\"))\n"
        "        held[\"iceberg_refresh\"] = bool(held[\"iceberg_refresh\"] or mbo.get(\"iceberg_refresh\"))\n"
        "        held[\"size_pulled\"] = bool(held[\"size_pulled\"] or mbo.get(\"size_pulled\"))\n"
        "    _LATCH[str(root)] = held\n"
        "    out = dict(mbo)\n"
        "    out.update(held)\n"
        "    out[\"latched\"] = True\n"
        "    return out\n\n\ndef lot_from_ticks(",
        1,
    )
    mbo_path.write_text(mbo, encoding="utf-8")

page = page_path.read_text(encoding="utf-8")
if "latch(" not in page:
    page = page.replace("read_mbo, update_ledger", "latch, read_mbo, update_ledger")
    page = page.replace("from gold_shadow.mbo_book import VIRTUAL_EQUITY, gate, lot_from_ticks, read_mbo, update_ledger", "from gold_shadow.mbo_book import VIRTUAL_EQUITY, gate, latch, lot_from_ticks, read_mbo, update_ledger")
    page = page.replace("def _mbo_view(mt5, symbol, resolved, preview):", "def _mbo_view(mt5, symbol, resolved, preview, bar_time=None):")
    page = page.replace("mbo = read_mbo(symbol)", "mbo = latch(read_mbo(symbol), bar_time)")
    page = page.replace("_mbo_view(mt5, symbol, resolved, preview)", "_mbo_view(mt5, symbol, resolved, preview, m5[-1][\"time\"] if m5 else None)")
if "setInterval" not in page:
    page = page.replace(
        "fetch('/api/v19/shadow-book').then(function(r){return r.json()}).then(paint)",
        "function hunt(){fetch('/api/v19/shadow-book').then(function(r){return r.json()}).then(paint)}\nhunt();\nsetInterval(hunt, 20000);\nvoid 0 && fetch('/api/v19/shadow-book').then(function(r){return r.json()}).then(paint)",
    )
page_path.write_text(page, encoding="utf-8")

web = web_path.read_text(encoding="utf-8")
if "start_shadow_hunt" not in web:
    web = web.replace(
        "        await super().on_startup(app)\n",
        "        await super().on_startup(app)\n        try:\n            from gold_shadow.hunt import start as start_shadow_hunt\n            start_shadow_hunt()\n        except Exception:\n            pass\n",
        1,
    )
if "from gold_shadow.hunt import latest" not in web:
    web = web.replace("payload = await asyncio.get_running_loop().run_in_executor(None, snapshot)", "payload = latest()")
    web = web.replace("payload = snapshot()", "payload = latest()")
    web = web.replace("from zeus3.v19.shadow_book_page import snapshot\n        try:\n            payload = latest()", "from gold_shadow.hunt import latest\n        try:\n            payload = latest()")
web_path.write_text(web, encoding="utf-8")
print("RULES_PATCHED")
