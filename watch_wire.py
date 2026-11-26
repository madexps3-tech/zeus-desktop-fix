"""Start the phone page from the signals page. Run once, on the PC, before ZEUS opens."""
from pathlib import Path

page = Path("src") / "zeus3" / "v19" / "signals_page.py"
if not page.exists():
    print("Could not find the signals page.", flush=True)
    raise SystemExit(1)
text = page.read_text(encoding="utf-8")
if "start_watch" in text:
    print("Phone watch is already wired.", flush=True)
elif "_AUTO_THREAD.start()" not in text:
    print("Could not find the auto start.", flush=True)
    raise SystemExit(1)
else:
    nl = "\r\n" if "\r\n" in text else "\n"
    text = text.replace(
        "_AUTO_THREAD.start()",
        "_AUTO_THREAD.start()" + nl
        + "    try:" + nl
        + "        from zeus3.v19.watch_page import start_watch" + nl
        + "        start_watch(host)" + nl
        + "    except Exception:" + nl
        + "        pass",
        1,
    )
    page.write_text(text, encoding="utf-8")
    print("Phone watch starts with the page.", flush=True)
