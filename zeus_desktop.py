"""Open the ZEUS window at once. The command windows stay hidden."""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
URL = "http://127.0.0.1:8783/"
HOME = "http://127.0.0.1:8783/v19/signals"
LOG = ROOT / "ZEUS_SERVER.log"
PROGRESS = ROOT / "ZEUS_PROGRESS.txt"
ICON = ROOT / "zeus.ico"
CHILD: subprocess.Popen | None = None

PAGE = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>ZEUS</title>
<style>
html,body{margin:0;height:100%;background:#071018;color:#e7eef5;
  font:18px Segoe UI,sans-serif}
main{height:100%;display:flex;flex-direction:column;align-items:center;
  justify-content:center;gap:18px}
.mark{width:72px;height:72px;border-radius:16px;background:#102033;
  color:#e9c66b;display:flex;align-items:center;justify-content:center;
  font:700 40px Georgia,serif;box-shadow:0 0 0 1px #3a4a22}
h1{margin:0;letter-spacing:.28em;font-weight:600;font-size:22px}
#line{color:#e9c66b;min-height:3em;max-width:640px;text-align:center;
  white-space:pre-wrap}
.sub{color:#8ea3b8;font-size:14px}
</style>
</head>
<body>
<main>
<div class="mark">Z</div>
<h1>ZEUS</h1>
<div id="line">Loading</div>
<div class="sub">MetaTrader stays logged in. This window is the program.</div>
</main>
</body>
</html>
"""


def _ico(path: Path) -> None:
    """A dark square with a gold Z. Windows uses this on the shortcut and the window."""
    size = 32
    pixels = []
    for y in range(size - 1, -1, -1):
        for x in range(size):
            edge = x < 2 or y < 2 or x > 29 or y > 29
            bar = y < 6 or y > 25 or abs((31 - y) - x) < 3
            if edge:
                pixels.append((32, 48, 64, 255))
            elif bar:
                pixels.append((233, 198, 107, 255))
            else:
                pixels.append((16, 32, 51, 255))
    xor = b"".join(bytes((b, g, r, a)) for r, g, b, a in pixels)
    header = (
        b"\x28\x00\x00\x00"
        + size.to_bytes(4, "little")
        + (size * 2).to_bytes(4, "little")
        + b"\x01\x00\x20\x00"
        + b"\x00" * 24
    )
    mask = b"\x00" * (size * size // 8)
    image = header + xor + mask
    entry = (
        bytes((size, size, 0, 0))
        + b"\x01\x00\x20\x00"
        + len(image).to_bytes(4, "little")
        + (6 + 16).to_bytes(4, "little")
    )
    path.write_bytes(b"\x00\x00\x01\x00\x01\x00" + entry + image)


def _shortcut(icon: Path) -> None:
    desktop = Path.home() / "Desktop"
    if not desktop.is_dir():
        desktop = Path.home() / "OneDrive" / "Desktop"
    if not desktop.is_dir():
        return
    launcher = ROOT / "ZEUS.vbs"
    launcher.write_text(
        'Set app = CreateObject("Wscript.Shell")\r\n'
        f'app.Run "cmd /c cd /d ""{ROOT}"" && DESKTOP_ZEUS.bat", 0, False\r\n',
        encoding="utf-8",
    )
    link = desktop / "ZEUS.lnk"
    command = (
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('"
        + str(link).replace("'", "''")
        + "');$s.TargetPath='wscript.exe';$s.Arguments='//nologo \""
        + str(launcher).replace("'", "''")
        + "\"';$s.WorkingDirectory='"
        + str(ROOT).replace("'", "''")
        + "';$s.IconLocation='"
        + str(icon).replace("'", "''")
        + ",0';$s.WindowStyle=7;$s.Save()"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        cwd=str(ROOT),
        creationflags=0x08000000,
        check=False,
    )


def _set_window_icon(icon: Path) -> None:
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, "ZEUS")
        if not hwnd:
            return
        handle = user32.LoadImageW(None, str(icon), 1, 0, 0, 0x10)
        if not handle:
            return
        user32.SendMessageW(hwnd, 0x80, 1, handle)
        user32.SendMessageW(hwnd, 0x80, 0, handle)
    except Exception:
        return


def _up() -> bool:
    try:
        urllib.request.urlopen(URL, timeout=2).close()
        return True
    except Exception:
        return False


def _python() -> str:
    """MetaTrader does not answer a windowless Python. Use the console one."""
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe":
        console = exe.with_name("python.exe")
        if console.is_file():
            return str(console)
    return str(exe)


def _start_server() -> None:
    global CHILD
    if _up():
        return
    handle = open(LOG, "w", encoding="utf-8")
    env = os.environ.copy()
    env["PYTHONPATH"] = env.get("PYTHONPATH") or str(ROOT / "src")
    info = subprocess.STARTUPINFO()
    info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    info.wShowWindow = 0
    CHILD = subprocess.Popen(
        [_python(), "-u", "-m", "zeus3.v19.web"],
        cwd=str(ROOT),
        stdout=handle,
        stderr=subprocess.STDOUT,
        env=env,
        startupinfo=info,
        creationflags=0x00000010,
    )


def _status() -> str:
    parts = []
    if PROGRESS.is_file():
        text = PROGRESS.read_text(encoding="utf-8", errors="replace").strip()
        if text:
            parts.append(text.splitlines()[-1])
    if CHILD is not None and CHILD.poll() not in (None, 0):
        tail = LOG.read_text(encoding="utf-8", errors="replace")[-700:] if LOG.is_file() else ""
        parts.append(tail or "The loader stopped.")
    elif LOG.is_file():
        tail = LOG.read_text(encoding="utf-8", errors="replace")[-700:]
        if "Traceback" in tail or "Authorization failed" in tail:
            parts.append(tail)
    return "\n".join(parts) or "Loading"


def _quote(text: str) -> str:
    return text.replace("\\", "\\\\").replace("`", "\\`").replace("\r", "")


def _hide_console() -> None:
    """Hide this process's console. The ZEUS window is a different window and stays."""
    try:
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)
    except Exception:
        return


def main() -> int:
    _hide_console()
    try:
        _ico(ICON)
        _shortcut(ICON)
    except Exception:
        pass
    _start_server()
    import webview

    window = webview.create_window("ZEUS", html=PAGE, width=1440, height=900)

    def watch() -> None:
        for _ in range(900):
            _set_window_icon(ICON)
            if _up():
                window.load_url(HOME)
                return
            line = _status()
            try:
                window.evaluate_js(
                    "var n=document.getElementById('line');if(n)n.textContent=`"
                    + _quote(line)
                    + "`;"
                )
            except Exception:
                return
            time.sleep(1)
        try:
            window.evaluate_js(
                "var n=document.getElementById('line');if(n)n.textContent='The dashboard did not open.';"
            )
        except Exception:
            return

    webview.start(watch, private_mode=False, storage_path=str(ROOT / "webview_profile"))
    if CHILD is not None and CHILD.poll() is None:
        CHILD.terminate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
