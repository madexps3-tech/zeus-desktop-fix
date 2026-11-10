from pathlib import Path

path = Path("src") / "zeus2" / "integration" / "legacy_intelligence_bridge.py"
if not path.exists():
    print("Sierra bridge file was not found. The clock fix does not need it.")
    raise SystemExit(0)
text = path.read_text(encoding="utf-8")
if "mbo_imbalance" in text:
    print("MBO fields are already kept.")
    raise SystemExit(0)
needle = '"market_data_lag_seconds",'
if needle not in text:
    print("Could not find the Sierra metric list.")
    raise SystemExit(1)
extra = (
    '"market_data_lag_seconds",\n'
    '    "mbo_imbalance",\n'
    '    "mbo_pull_stack",\n'
    '    "bid_order_count",\n'
    '    "ask_order_count",'
)
path.write_bytes(text.replace(needle, extra, 1).encode("utf-8"))
print("Sierra will now keep MBO fields.")
