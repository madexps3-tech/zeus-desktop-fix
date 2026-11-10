from pathlib import Path
import sys

root = Path(sys.argv[1])
sweep_path = root / "src" / "gold_shadow" / "sweep_shadow.py"
book_path = root / "src" / "gold_shadow" / "shadow_book.py"
sweep = sweep_path.read_text(encoding="utf-8")
if "def broker_sessions" not in sweep:
    fn = (
        "def broker_sessions(sessions, now):\n"
        "    stamp = now.replace(tzinfo=None)\n"
        "    shift = int(round((stamp - __import__('datetime').datetime.utcnow()).total_seconds() / 3600.0))\n"
        "    if shift == 0:\n"
        "        return tuple(sessions)\n"
        "    shift = max(-12, min(14, shift))\n"
        "    def move(value):\n"
        "        minutes = (value.hour * 60 + value.minute + shift * 60) % (24 * 60)\n"
        "        return __import__('datetime').time(minutes // 60, minutes % 60)\n"
        "    return tuple((move(start), move(end)) for start, end in sessions)\n\n\n"
    )
    sweep = sweep.replace("def _in_session(", fn + "def _in_session(", 1)
    old = '    if not spec:\n        return _wait(symbol, "NO_PROFILE", strategy_id=strategy_id)\n\n    if risk is not None'
    new = '    if not spec:\n        return _wait(symbol, "NO_PROFILE", strategy_id=strategy_id)\n    sessions = broker_sessions(sessions, now)\n\n    if risk is not None'
    if old not in sweep:
        raise SystemExit("Could not patch the session clock")
    sweep = sweep.replace(old, new, 1)
    sweep_path.write_text(sweep, encoding="utf-8")
book = book_path.read_text(encoding="utf-8")
if "broker_sessions" not in book:
    book = book.replace("    DEFAULT_SESSIONS,\n", "    DEFAULT_SESSIONS,\n    broker_sessions,\n", 1)
    book = book.replace("_in_session(now, DEFAULT_SESSIONS)", "_in_session(now, broker_sessions(DEFAULT_SESSIONS, now))", 1)
    book_path.write_text(book, encoding="utf-8")
print("CLOCK_PATCHED")
