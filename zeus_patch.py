from pathlib import Path

path = Path("src") / "zeus3" / "v19" / "web.py"
text = path.read_text(encoding="utf-8")
newline = "\r\n" if "\r\n" in text else "\n"
fixed = text.replace(
    "print(Connecting to MetaTrader..., flush=True)",
    'print("Connecting to MetaTrader...", flush=True)',
)
if fixed != text:
    text = fixed
    print("Repaired the broken loader line.", flush=True)
else:
    print("Loader line is already valid.", flush=True)

if "ZEUS_PROGRESS" not in text:
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
    print("Loader progress added.", flush=True)

if "def signals_page" not in text:
    methods = (
        "    async def signals_page(self, request: web.Request) -> web.Response:" + newline
        + "        from zeus3.v19.signals_page import render_signals_page" + newline
        + "        return web.Response(text=render_signals_page(), content_type='text/html')" + newline
        + newline
        + "    async def signals_snapshot(self, request: web.Request) -> web.Response:" + newline
        + "        from zeus3.v19.signals_page import signals_snapshot" + newline
        + "        return await signals_snapshot(self, request)" + newline
        + newline
    )
    marker = "    def application(self) -> web.Application:"
    marker_nl = "    def application(self) -> web.Application:" 
    if marker not in text and marker_nl not in text:
        print("Could not find the page list.", flush=True)
        raise SystemExit(1)
    text = text.replace(marker, methods + marker, 1)
    print("Signals handlers added.", flush=True)

if "/v19/signals" not in text:
    old_route = 'app.router.add_get("/v19/shadow", self.shadow_book_page)'
    new_route = (
        old_route + newline
        + '        app.router.add_get("/v19/signals", self.signals_page)' + newline
        + '        app.router.add_get("/api/v19/signals", self.signals_snapshot)'
    )
    if old_route not in text:
        print("Could not find the shadow page route.", flush=True)
        raise SystemExit(1)
    text = text.replace(old_route, new_route, 1)
    print("Signals route added.", flush=True)

path.write_bytes(text.encode("utf-8"))

shell = Path("src") / "zeus3" / "v19" / "shell.py"
nav = shell.read_text(encoding="utf-8")
if "/v19/signals" not in nav:
    old_nav = '("CHART", "/v19/chart"),'
    if old_nav not in nav:
        print("Could not find the chart tab.", flush=True)
        raise SystemExit(1)
    nav = nav.replace(
        old_nav,
        old_nav + ("\r\n" if "\r\n" in nav else "\n") + '    ("SIGNALS", "/v19/signals"),',
        1,
    )
    shell.write_bytes(nav.encode("utf-8"))
    print("Signals tab added.", flush=True)
else:
    print("Signals tab is already there.", flush=True)

resolver = Path("src") / "zeus3" / "instruments" / "resolver.py"
mapping = resolver.read_text(encoding="utf-8")
resolver_newline = "\r\n" if "\r\n" in mapping else "\n"
if "_prefer_plus" not in mapping:
    helper = (
        "def _prefer_plus(canonical: str, candidates: tuple[str, ...]) -> str | None:" + resolver_newline
        + "    plus = tuple(x for x in candidates if _upper(x) == _upper(canonical) + \"+\")" + resolver_newline
        + "    if len(plus) == 1:" + resolver_newline
        + "        return plus[0]" + resolver_newline
        + "    return None" + resolver_newline
        + resolver_newline
        + resolver_newline
        + "def resolve_broker_symbol("
    )
    old_def = "def resolve_broker_symbol("
    old_tie = (
        "    if len(canonical_decorated) > 1:" + resolver_newline
        + "        return MappingResult(canonical, None, 0, True, canonical_decorated)"
    )
    new_tie = (
        "    if len(canonical_decorated) > 1:" + resolver_newline
        + "        chosen = _prefer_plus(canonical, canonical_decorated)" + resolver_newline
        + "        if chosen is not None:" + resolver_newline
        + "            return MappingResult(canonical, chosen, 90, False, canonical_decorated)" + resolver_newline
        + "        return MappingResult(canonical, None, 0, True, canonical_decorated)"
    )
    if old_def not in mapping or old_tie not in mapping:
        print("Could not update the gold symbol match.", flush=True)
        raise SystemExit(1)
    mapping = mapping.replace(old_def, helper, 1)
    mapping = mapping.replace(old_tie, new_tie, 1)
    resolver.write_bytes(mapping.encode("utf-8"))
    print("Gold now uses XAUUSD+ when both gold names exist.", flush=True)
else:
    print("Gold symbol match is already updated.", flush=True)

