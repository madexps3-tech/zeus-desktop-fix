import time
import urllib.request
from pathlib import Path

url = "http://127.0.0.1:8783/"
progress = Path("ZEUS_PROGRESS.txt")
seen = ""
print("Waiting for the loader.", flush=True)
for i in range(90):
    if progress.exists():
        text = progress.read_text(encoding="utf-8", errors="replace")
        if text != seen:
            print(text[len(seen):], end="", flush=True)
            seen = text
    elif i == 8:
        print("The loader has not reported yet. Any error is above this line.", flush=True)
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
