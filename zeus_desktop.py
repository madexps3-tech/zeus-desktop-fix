import time
import urllib.request
from pathlib import Path

URL = "http://127.0.0.1:8783/"
ok = False
end = time.time() + 180
while time.time() < end:
    try:
        urllib.request.urlopen(URL, timeout=2).close()
        ok = True
        break
    except Exception:
        time.sleep(0.4)
if not ok:
    raise SystemExit(1)
print("Opening the ZEUS dashboard.")
import webview
storage = Path(__file__).resolve().parent / "webview_profile"
storage.mkdir(exist_ok=True)
webview.create_window("ZEUS", URL, width=1440, height=900)
webview.start(private_mode=False, storage_path=str(storage))
