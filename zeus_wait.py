import time
import urllib.request
from pathlib import Path

url = "http://127.0.0.1:8783/"
progress = Path("ZEUS_PROGRESS.txt")
seen = ""
for _ in range(120):
    if progress.exists():
        text = progress.read_text(encoding="utf-8", errors="replace")
        if text != seen:
            print(text[len(seen):], end="", flush=True)
            seen = text
    try:
        urllib.request.urlopen(url, timeout=2).close()
        raise SystemExit(0)
    except SystemExit:
        raise
    except Exception:
        time.sleep(1)
print("The dashboard did not open. The last loader line is above.")
raise SystemExit(1)
