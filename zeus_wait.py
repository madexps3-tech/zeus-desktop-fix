import time
import urllib.request
from pathlib import Path

url = "http://127.0.0.1:8783/"
progress = Path("ZEUS_PROGRESS.txt")
log = Path("ZEUS_SERVER.log")
print("Waiting for the loader. Market loading can take several minutes.", flush=True)
seen = ""
for i in range(900):
    if progress.exists():
        text = progress.read_text(encoding="utf-8", errors="replace")
        if text != seen:
            print(text[len(seen):], end="", flush=True)
            seen = text
        if "did not answer" in text.lower() or "did not return" in text.lower():
            print("This step did not return. ZEUS has stopped. This window is not still loading.", flush=True)
            raise SystemExit(1)
    if i and i % 30 == 0:
        print("Still loading. Leave this window and the ZEUS Server window open.", flush=True)
    if log.exists() and i and i % 15 == 0:
        tail = log.read_text(encoding="utf-8", errors="replace")[-1800:]
        if "Traceback" in tail or "MT5 terminal selection failed" in tail or "timed out" in tail.lower() or "No broker markets" in tail:
            print(tail, flush=True)
            print("The loader stopped. The lines above are the reason.", flush=True)
            raise SystemExit(1)
    try:
        urllib.request.urlopen(url, timeout=2).close()
        print("Dashboard is answering.", flush=True)
        raise SystemExit(0)
    except SystemExit:
        raise
    except Exception:
        time.sleep(1)
print("The dashboard did not open.")
if log.exists():
    print(log.read_text(encoding="utf-8", errors="replace")[-2000:], flush=True)
print("Leave MetaTrader logged in, with no popup on top of it. Close any other ZEUS Server window, then run this again.", flush=True)
raise SystemExit(1)
