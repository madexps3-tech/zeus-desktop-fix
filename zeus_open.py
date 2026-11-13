"""Open the ZEUS window immediately. The broker symbol list loads behind it."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path.cwd()
PORT = 8783
BACK = 8784
CHILD: subprocess.Popen | None = None

PAGE = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>ZEUS</title>
<style>
body { margin:0; background:#050b11; color:#e7eef5; font:16px Consolas,monospace; }
main { max-width:740px; margin:72px auto; padding:24px; }
h1 { font-size:22px; letter-spacing:.14em; font-weight:600; }
p { color:#8ea3b8; line-height:1.5; }
#line { color:#e9c66b; min-height:4em; white-space:pre-wrap; }
</style>
</head>
<body>
<main>
<h1>ZEUS</h1>
<p>This window is open. The broker symbol list is loading behind it. This is not Chrome or Edge.</p>
<div id="line">Loading markets from MetaTrader</div>
</main>
<script>
async function tick(){
  try {
    const r = await fetch('/status');
    const j = await r.json();
    document.getElementById('line').textContent = j.line || 'Loading markets from MetaTrader';
    if (j.ready) { location.replace('http://127.0.0.1:8784/'); return; }
  } catch (e) {}
  setTimeout(tick, 1000);
}
tick();
</script>
</body>
</html>
"""


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def backend_ready() -> bool:
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{BACK}/", timeout=1).close()
        return True
    except Exception:
        return False


def status() -> dict:
    progress = read_text(ROOT / "ZEUS_PROGRESS.txt").strip()
    log = read_text(ROOT / "ZEUS_SERVER.log")
    last = progress.splitlines()[-1] if progress else "Loading markets from MetaTrader"
    if "Authorization failed" in log:
        last = "MetaTrader refused the login. Log in to the terminal, then run ZEUS again."
    elif CHILD is not None and CHILD.poll() not in (None, 0) and not backend_ready():
        tail = "\n".join(log.strip().splitlines()[-12:]) or "The loader stopped."
        last = tail
    return {"ready": backend_ready(), "line": last}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        return

    def do_GET(self) -> None:
        if self.path.startswith("/status"):
            body = json.dumps(status()).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        body = PAGE.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)


def main() -> int:
    global CHILD
    log_handle = open(ROOT / "ZEUS_SERVER.log", "w", encoding="utf-8")
    env = os.environ.copy()
    env["PYTHONPATH"] = env.get("PYTHONPATH") or str(ROOT / "src")
    CHILD = subprocess.Popen(
        [sys.executable, "-u", "-m", "zeus3.v19.web", "--port", str(BACK)],
        cwd=str(ROOT),
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        env=env,
    )
    note = ROOT / "ZEUS_PROGRESS.txt"
    if not note.exists():
        note.write_text("ZEUS window is open. Loading markets from MetaTrader.\n", encoding="utf-8")
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"ZEUS window port {PORT} is open. Markets load on {BACK}.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
