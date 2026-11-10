from pathlib import Path

path = Path("src") / "zeus3" / "v19" / "web.py"
text = path.read_text(encoding="utf-8")
newline = "\r\n" if "\r\n" in text else "\n"
if "ZEUS_PROGRESS" in text:
    print("Loader progress is already in place.", flush=True)
    raise SystemExit(0)

helper = (
    "def main() -> int:" + newline
    + "    def _step(msg):" + newline
    + "        print(msg, flush=True)" + newline
    + "        try:" + newline
    + "            with open('ZEUS_PROGRESS.txt', 'a', encoding='utf-8') as handle:" + newline
    + "                handle.write(msg + chr(10))" + newline
    + "        except Exception:" + newline
    + "            pass" + newline
    + "    _step('ZEUS loader started')" + newline
)
old_main = "def main() -> int:" + newline
if old_main not in text:
    print("Could not find the loader start.", flush=True)
    raise SystemExit(1)
text = text.replace(old_main, helper, 1)
text = text.replace(
    "runtime = ChartHostRuntime.bootstrap(",
    "_step('Loading markets from MetaTrader')" + newline + "        runtime = ChartHostRuntime.bootstrap(",
    1,
)
text = text.replace(
    'print("ZEUS V3 V1.9 FINAL UI DEVELOPMENT")',
    "_step('Dashboard is ready')" + newline + '    print("ZEUS V3 V1.9 FINAL UI DEVELOPMENT")',
    1,
)
path.write_bytes(text.encode("utf-8"))
print("Loader will now report each step in this window.", flush=True)
