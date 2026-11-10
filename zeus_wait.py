import time
import urllib.request
from pathlib import Path

url = "http://127.0.0.1:8783/"
progress = Path("ZEUS_PROGRESS.txt")
seen = ""
print("Waiting for the loader. Market loading can take several minutes.", flush=True)
for i in range(480):
    if progress.exists():
        text = progress.read_text(encoding="utf-8", errors="replace")
        if text != seen:
            print(text[len(seen):], end="", flush=True)
            seen = text
    if i and i % 30 == 0:
        print("Still loading. Leave this window open.", flush=True)
    try:
        urllib.request.urlopen(url, timeout=2).close()
        print("Dashboard is answering.", flush=True)
        raise SystemExit(0)
    except SystemExit:
        raise
    except Exception:
        time.sleep(1)
print("The dashboard did not open.")
raise SystemExit(1)
