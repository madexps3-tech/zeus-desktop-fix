"""Ask MetaTrader once, on its own, and print the real answer."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

CODE = r"""
import sys
from MetaTrader5 import initialize, shutdown, last_error, account_info
path = sys.argv[1]
portable = sys.argv[2] == "1"
ok = initialize(path, portable=portable, timeout=12000)
print("INIT", "portable" if portable else "normal", bool(ok), flush=True)
if not ok:
    print("ERROR", last_error(), flush=True)
    raise SystemExit(2)
info = account_info()
login = getattr(info, "login", None) if info is not None else None
server = getattr(info, "server", None) if info is not None else None
print("ACCOUNT", login, server, flush=True)
shutdown()
"""


def attempt(path: str, portable: bool) -> int:
    proc = subprocess.Popen(
        [sys.executable, "-c", CODE, path, "1" if portable else "0"],
    )
    try:
        return proc.wait(timeout=20)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)
        print("NO ANSWER", "portable" if portable else "normal", flush=True)
        return 3


def main() -> int:
    file_path = Path("ZEUS_TERMINAL_PATH.txt")
    path = file_path.read_text(encoding="utf-8").strip() if file_path.exists() else ""
    if not path:
        print("No terminal path.", flush=True)
        return 2
    print("Testing", path, flush=True)
    for portable in (False, True):
        code = attempt(path, portable)
        if code == 0:
            print("MetaTrader answered.", flush=True)
            return 0
    print("MetaTrader is open but it did not accept the connection.", flush=True)
    print("In MetaTrader: Tools, Options, Expert Advisors.", flush=True)
    print("Turn on Allow algorithmic trading and Allow DLL imports. Click OK.", flush=True)
    print("Then File, Exit. Open C:\\MT5\\terminal64.exe, log in, and run ZEUS once.", flush=True)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
