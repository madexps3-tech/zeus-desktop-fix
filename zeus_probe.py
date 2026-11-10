import subprocess
from pathlib import Path

known = r"C:\Users\madex\OneDrive\Desktop\MetaTrader 5 - Copy\terminal64.exe"
print("Looking for the running terminal.", flush=True)
paths = []
try:
    found = subprocess.run(
        [
            "powershell", "-NoProfile", "-NonInteractive", "-Command",
            "Get-CimInstance Win32_Process -Filter \"Name='terminal64.exe'\" | Select-Object -ExpandProperty ExecutablePath",
        ],
        capture_output=True,
        text=True,
        timeout=12,
    )
    paths = [
        line.strip()
        for line in (found.stdout or "").splitlines()
        if line.strip().lower().endswith("terminal64.exe")
    ]
except Exception as exc:
    print("Could not list terminals:", type(exc).__name__, flush=True)
if not paths:
    print("No running terminal was found. Using the Copy path.", flush=True)
    terminal = known
else:
    for path in paths:
        print("Running:", path, flush=True)
    copies = [path for path in paths if "MetaTrader 5 - Copy" in path]
    terminal = copies[0] if copies else paths[0]
print("The chart loader will use:", terminal, flush=True)
Path("ZEUS_TERMINAL_PATH.txt").write_text(terminal, encoding="utf-8")
