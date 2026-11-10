from pathlib import Path
import sys

root = Path(sys.argv[1].strip().strip('"').rstrip("\\/"))
sweep_path = root / "src" / "gold_shadow" / "sweep_shadow.py"
book_path = root / "src" / "gold_shadow" / "shadow_book.py"
mbo_path = root / "src" / "gold_shadow" / "mbo_book.py"
page_path = root / "src" / "zeus3" / "v19" / "shadow_book_page.py"
web_path = root / "src" / "zeus3" / "v19" / "web.py"

sweep = sweep_path.read_text(encoding="utf-8")
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
    "    if bias == \"BULL\":\n"
    "        side = \"BUY\"\n"
    "    elif bias == \"BEAR\":\n"
    "        side = \"SELL\"\n"
    "    else:\n"
    "        side = None\n"
    "        best_at = -1\n"
    "        for candidate in (\"BUY\", \"SELL\"):\n"
    "            for _, level in _candidate_levels(m15, candidate, spec[\"equal\"]):\n"
    "                found = _find_sweep(m5, level, candidate, spec[\"sweep\"])\n"
    "                if found is None or found[\"reclaim_index\"] < len(m5) - 2:\n"
    "                    continue\n"
    "                if found[\"reclaim_index\"] >= best_at:\n"
    "                    best_at = found[\"reclaim_index\"]\n"
    "                    side = candidate\n"
    "        if side is None:\n"
    "            return _wait(symbol, \"NO_FRESH_SWEEP_RECLAIM\", orderflow, strategy_id)\n"
)
if old not in sweep and "for candidate in (\"BUY\", \"SELL\"):" not in sweep:
    raise SystemExit("Could not find the hourly-bias rule")
if old in sweep:
    sweep_path.write_text(sweep.replace(old, new, 1), encoding="utf-8")

book = book_path.read_text(encoding="utf-8")
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
        "    out.update({k: held[k] for k in (\"sweep_consumed\", \"iceberg_refresh\", \"size_pulled\")})\n"
        "    out[\"latched\"] = True\n"
        "    return out\n\n\ndef lot_from_ticks(",
        1,
    )
    mbo_path.write_text(mbo, encoding="utf-8")

page = page_path.read_text(encoding="utf-8")
if "latch(read_mbo" not in page:
    page = page.replace("lot_from_ticks, read_mbo", "latch, lot_from_ticks, read_mbo")
    page = page.replace("def _mbo_view(mt5, symbol, resolved, preview):", "def _mbo_view(mt5, symbol, resolved, preview, bar_time=None):")
    page = page.replace("mbo = read_mbo(symbol)", "mbo = latch(read_mbo(symbol), bar_time)")
    page = page.replace("_mbo_view(mt5, symbol, resolved, preview)", "_mbo_view(mt5, symbol, resolved, preview, m5[-1][\"time\"] if m5 else None)")
if "setInterval(hunt, 20000)" not in page:
    page = page.replace(
        "fetch('/api/v19/shadow-book').then(function(r){return r.json()}).then(paint)",
        "function hunt(){fetch('/api/v19/shadow-book').then(function(r){return r.json()}).then(paint).catch(function(){})}\nhunt(); setInterval(hunt, 20000);\n0 && fetch('/api/v19/shadow-book').then(function(r){return r.json()}).then(paint)",
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
    web = web.replace(
        "from zeus3.v19.shadow_book_page import snapshot\n        try:\n            payload = await asyncio.get_running_loop().run_in_executor(None, snapshot)",
        "from gold_shadow.hunt import latest\n        try:\n            payload = latest()",
    )
    web = web.replace(
        "from zeus3.v19.shadow_book_page import snapshot\n        try:\n            payload = snapshot()",
        "from gold_shadow.hunt import latest\n        try:\n            payload = latest()",
    )
web_path.write_text(web, encoding="utf-8")
print("RULES_PATCHED")
