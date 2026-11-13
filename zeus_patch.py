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

if "def signals_taken" not in text:
    taken_method = (
        "    async def signals_taken(self, request: web.Request) -> web.Response:" + newline
        + "        from zeus3.v19.signals_page import signals_taken" + newline
        + "        return await signals_taken(self, request)" + newline
        + newline
    )
    marker = "    def application(self) -> web.Application:"
    if marker not in text:
        print("Could not add the taken handler.", flush=True)
        raise SystemExit(1)
    text = text.replace(marker, taken_method + marker, 1)
    print("Taken handler added.", flush=True)

if "/api/v19/signals/taken" not in text:
    old_sig = 'app.router.add_get("/api/v19/signals", self.signals_snapshot)'
    if old_sig not in text:
        print("Could not find the signals route.", flush=True)
        raise SystemExit(1)
    text = text.replace(
        old_sig,
        old_sig + newline + '        app.router.add_post("/api/v19/signals/taken", self.signals_taken)',
        1,
    )
    print("Taken route added.", flush=True)

if "def signals_priority" not in text:
    priority_method = (
        "    async def signals_priority(self, request: web.Request) -> web.Response:" + newline
        + "        from zeus3.v19.signals_page import signals_priority" + newline
        + "        return await signals_priority(self, request)" + newline
        + newline
    )
    marker = "    def application(self) -> web.Application:"
    if marker not in text:
        print("Could not add the priority handler.", flush=True)
        raise SystemExit(1)
    text = text.replace(marker, priority_method + marker, 1)
    print("Priority handler added.", flush=True)

if "/api/v19/signals/priority" not in text:
    old_taken = 'app.router.add_post("/api/v19/signals/taken", self.signals_taken)'
    if old_taken not in text:
        print("Could not find the taken route.", flush=True)
        raise SystemExit(1)
    text = text.replace(
        old_taken,
        old_taken + newline + '        app.router.add_post("/api/v19/signals/priority", self.signals_priority)',
        1,
    )
    print("Priority route added.", flush=True)

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

runtime = Path("src") / "zeus3" / "chart" / "runtime.py"
clock = runtime.read_text(encoding="utf-8")
clock_newline = "\r\n" if "\r\n" in clock else "\n"
old_quotes = (
    "            try:" + clock_newline
    + "                mapped_quotes.append(worker.quote(mapping.broker_symbol))" + clock_newline
    + "            except Exception:" + clock_newline
    + "                continue"
)
new_quotes = (
    "            if len(mapped_quotes) >= 3:" + clock_newline
    + "                break" + clock_newline
    + "            try:" + clock_newline
    + "                mapped_quotes.append(worker.quote(mapping.broker_symbol))" + clock_newline
    + "            except Exception:" + clock_newline
    + "                continue"
)
if "len(mapped_quotes) >= 3" in clock:
    print("Startup quotes are already limited.", flush=True)
elif old_quotes not in clock:
    print("Could not limit the startup quotes.", flush=True)
    raise SystemExit(1)
else:
    runtime.write_bytes(clock.replace(old_quotes, new_quotes, 1).encode("utf-8"))
    print("Startup reads three quotes, not the whole list.", flush=True)



runtime_fast = Path("src") / "zeus3" / "chart" / "runtime.py"
fast = runtime_fast.read_text(encoding="utf-8")
fast_nl = "\r\n" if "\r\n" in fast else "\n"
old_import = "from zeus3.instruments.live_mapping import build_runtime_mappings"
new_import = "from zeus3.instruments.live_mapping import build_fast_runtime_mappings"
old_call = "mappings, catalog = build_runtime_mappings(worker)"
new_call = "mappings, catalog = build_fast_runtime_mappings(worker)"
old_worker = (
    "        worker = SubprocessMT5ReadClient(" + fast_nl
    + "            MT5WorkerConfig(" + fast_nl
    + "                profile_id=\"PRIMARY_CHART\"," + fast_nl
    + "                terminal_path=selected," + fast_nl
    + "                expected_login=expected_login," + fast_nl
    + "                expected_server=expected_server," + fast_nl
    + "                expected_company=expected_company," + fast_nl
    + "            )" + fast_nl
    + "        )"
)
new_worker = (
    "        worker = SubprocessMT5ReadClient(" + fast_nl
    + "            MT5WorkerConfig(" + fast_nl
    + "                profile_id=\"PRIMARY_CHART\"," + fast_nl
    + "                terminal_path=selected," + fast_nl
    + "                expected_login=expected_login," + fast_nl
    + "                expected_server=expected_server," + fast_nl
    + "                expected_company=expected_company," + fast_nl
    + "                initialize_timeout_ms=15000," + fast_nl
    + "            )" + fast_nl
    + "        )"
)
if "build_fast_runtime_mappings" in fast and "initialize_timeout_ms=15000" in fast:
    print("Direct name mapping is already installed.", flush=True)
else:
    if old_import not in fast or old_call not in fast or old_worker not in fast:
        print("Could not install the direct name mapping.", flush=True)
        raise SystemExit(1)
    fast = fast.replace(old_import, new_import, 1)
    fast = fast.replace(old_call, new_call, 1)
    fast = fast.replace(old_worker, new_worker, 1)
    runtime_fast.write_bytes(fast.encode("utf-8"))
    print("Startup checks the real symbol names only.", flush=True)
