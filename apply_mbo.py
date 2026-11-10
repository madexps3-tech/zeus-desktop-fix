from pathlib import Path

NEEDLE = '"market_data_lag_seconds",'
EXTRA = '"market_data_lag_seconds",' + chr(10) + '    "mbo_imbalance",' + chr(10) + '    "mbo_pull_stack",'

def patch(path: Path) -> None:
    if not path.exists():
        print("Missing", path)
        return
    text = path.read_text(encoding="utf-8")
    if "mbo_imbalance" in text:
        print("Already patched", path.name)
        return
    if NEEDLE not in text:
        print("Metric list not found in", path.name)
        return
    path.write_bytes(text.replace(NEEDLE, EXTRA, 1).encode("utf-8"))
    print("Patched", path.name)

root = Path("src") / "zeus2" / "integration"
patch(root / "legacy_intelligence_bridge.py")
patch(root / "legacy_intelligence_pr737.py")
