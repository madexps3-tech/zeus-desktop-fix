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


page = Path("src") / "zeus3" / "v19" / "web.py"
page_text = page.read_text(encoding="utf-8")
page_nl = "\r\n" if "\r\n" in page_text else "\n"
old_brain = (
    "        try:" + page_nl
    + "            self.integrated_brain = self._new_integrated_brain(runtime)" + page_nl
    + "            brain_start_error = None" + page_nl
    + "        except Exception as exc:" + page_nl
    + "            # A failed/corrupt research journal must never stop the owner's" + page_nl
    + "            # known-working manual trading desk from starting." + page_nl
    + "            self.integrated_brain = None" + page_nl
    + "            brain_start_error = f'{type(exc).__name__}: {exc}'"
)
new_brain = (
    "        self.integrated_brain = None" + page_nl
    + "        brain_start_error = None" + page_nl
    + "        self._defer_brain = True"
)
old_scrub = (
    "            self._v1_crash_recovery_count = await asyncio.to_thread(" + page_nl
    + "                self._scrub_orphaned_v1_demo_authority, self.runtime)" + page_nl
    + "            self._v1_crash_recovery_error = None"
)
new_scrub = (
    "            self._v1_crash_recovery_count = 0" + page_nl
    + "            self._v1_crash_recovery_error = 'PAGE_FIRST'" + page_nl
    + "            asyncio.create_task(self._open_page_then_finish())"
)
method = (
    "    async def _open_page_then_finish(self) -> None:" + page_nl
    + "        try:" + page_nl
    + "            self._v1_crash_recovery_count = await asyncio.to_thread(" + page_nl
    + "                self._scrub_orphaned_v1_demo_authority, self.runtime)" + page_nl
    + "            self._v1_crash_recovery_error = None" + page_nl
    + "        except Exception as exc:" + page_nl
    + "            self._v1_crash_recovery_error = f'{type(exc).__name__}: {exc}'" + page_nl
    + "            self._v1_demo_last_tick = {" + page_nl
    + "                'status': 'BLOCKED'," + page_nl
    + "                'blockers': ['V1_CANONICAL_CRASH_RECOVERY_NOT_VERIFIED']," + page_nl
    + "                'broker_writes': 0," + page_nl
    + "            }" + page_nl
    + "        if getattr(self, '_defer_brain', False) and self.integrated_brain is None:" + page_nl
    + "            try:" + page_nl
    + "                self.integrated_brain = await asyncio.to_thread(" + page_nl
    + "                    self._new_integrated_brain, self.runtime)" + page_nl
    + "            except Exception as exc:" + page_nl
    + "                self.integrated_brain = None" + page_nl
    + "                self._brain_last_tick = {" + page_nl
    + "                    'status': 'RESEARCH_PRODUCER_FAIL_CLOSED'," + page_nl
    + "                    'error': f'{type(exc).__name__}: {exc}'," + page_nl
    + "                    'broker_writes': 0," + page_nl
    + "                }" + page_nl
    + "        if self.integrated_brain is not None and self._brain_task is None:" + page_nl
    + "            try:" + page_nl
    + "                self._subscribe_world_brain_reads()" + page_nl
    + "                self._brain_task = asyncio.create_task(" + page_nl
    + "                    self._integrated_brain_loop(), name='v19-integrated-world-brain'," + page_nl
    + "                )" + page_nl
    + "            except Exception as exc:" + page_nl
    + "                self._brain_last_tick = {" + page_nl
    + "                    'status': 'RESEARCH_PRODUCER_FAIL_CLOSED'," + page_nl
    + "                    'error': f'{type(exc).__name__}: {exc}'," + page_nl
    + "                    'broker_writes': 0," + page_nl
    + "                }" + page_nl
    + "        if self._v1_crash_recovery_error is None and self._native_auto_task is None:" + page_nl
    + "            self._native_auto_task = asyncio.create_task(" + page_nl
    + "                self._native_auto_loop(), name='v19-native-auto-dispatcher'" + page_nl
    + "            )" + page_nl
    + page_nl
    + "    async def on_startup(self, app: web.Application) -> None:"
)
anchor = "    async def on_startup(self, app: web.Application) -> None:"
if "_open_page_then_finish" in page_text and "_defer_brain = True" in page_text:
    print("Trading page already opens before the research brain.", flush=True)
else:
    if old_brain not in page_text or old_scrub not in page_text or anchor not in page_text:
        print("Could not open the trading page first.", flush=True)
        raise SystemExit(1)
    page_text = page_text.replace(old_brain, new_brain, 1)
    page_text = page_text.replace(old_scrub, new_scrub, 1)
    page_text = page_text.replace(anchor, method, 1)
    page.write_bytes(page_text.encode("utf-8"))
    print("Trading page opens before the research brain.", flush=True)


boot_path = Path("src") / "zeus3" / "v19" / "web.py"
boot = boot_path.read_text(encoding="utf-8")
bnl = "\r\n" if "\r\n" in boot else "\n"
old_boot = (
    "        _step('Loading markets from MetaTrader')" + bnl
    + "        runtime = ChartHostRuntime.bootstrap(" + bnl
    + "            terminal_path=selected_terminal," + bnl
    + "            expected_login=expected_login," + bnl
    + "            expected_server=expected_server," + bnl
    + "            expected_company=expected_company," + bnl
    + "        )"
)
new_boot = (
    "        _step('Loading markets from MetaTrader')" + bnl
    + "        _boot_box = {}" + bnl
    + "        def _boot_markets():" + bnl
    + "            try:" + bnl
    + "                _boot_box['runtime'] = ChartHostRuntime.bootstrap(" + bnl
    + "                    terminal_path=selected_terminal," + bnl
    + "                    expected_login=expected_login," + bnl
    + "                    expected_server=expected_server," + bnl
    + "                    expected_company=expected_company," + bnl
    + "                )" + bnl
    + "            except BaseException as exc:" + bnl
    + "                _boot_box['error'] = exc" + bnl
    + "        _boot_thread = threading.Thread(target=_boot_markets, name='zeus-mt5-boot', daemon=True)" + bnl
    + "        _boot_thread.start()" + bnl
    + "        _boot_thread.join(45)" + bnl
    + "        if _boot_thread.is_alive():" + bnl
    + "            print('MetaTrader did not answer within 45 seconds.', flush=True)" + bnl
    + "            print(selected_terminal, flush=True)" + bnl
    + "            _step('MetaTrader did not answer')" + bnl
    + "            os._exit(4)" + bnl
    + "        if 'error' in _boot_box:" + bnl
    + "            raise _boot_box['error']" + bnl
    + "        runtime = _boot_box['runtime']"
)
if "_boot_thread" not in boot:
    print("The loader is no longer cut off.", flush=True)
elif "_boot_thread.join(25)" in boot:
    boot = boot.replace("_boot_thread.join(25)", "_boot_thread.join(45)", 1)
    boot_path.write_bytes(boot.encode("utf-8"))
    print("The old cutoff is still in place.", flush=True)
else:
    print("The old cutoff is still in place.", flush=True)

import re
direct_boot = (
    "        runtime = ChartHostRuntime.bootstrap(" + bnl
    + "            terminal_path=selected_terminal," + bnl
    + "            expected_login=expected_login," + bnl
    + "            expected_server=expected_server," + bnl
    + "            expected_company=expected_company," + bnl
    + "        )"
)
boot_now = boot_path.read_text(encoding="utf-8")
if "_boot_thread" not in boot_now:
    print("The loader is no longer cut off.", flush=True)
else:
    boot_fixed, count = re.subn(
        r"        _boot_box = \{\}.*?        runtime = _boot_box\['runtime'\]",
        direct_boot,
        boot_now,
        count=1,
        flags=re.S,
    )
    if count != 1:
        print("Could not remove the loader cutoff.", flush=True)
        raise SystemExit(1)
    boot_path.write_bytes(boot_fixed.encode("utf-8"))
    print("The loader is no longer cut off.", flush=True)


stage = Path("src") / "zeus3" / "chart" / "runtime.py"
stage_text = stage.read_text(encoding="utf-8")
snl = "\r\n" if "\r\n" in stage_text else "\n"
old_stage = "        worker.start()" + snl + snl + "        mappings, catalog = build_fast_runtime_mappings(worker)"
new_stage = (
    "        def _boot_note(msg):" + snl
    + "            print(msg, flush=True)" + snl
    + "            with open('ZEUS_PROGRESS.txt', 'a', encoding='utf-8') as handle:" + snl
    + "                handle.write(msg + chr(10))" + snl
    + "        _boot_note('Asking MetaTrader for the account')" + snl
    + "        from threading import Thread" + snl
    + "        _box = {}" + snl
    + "        def _start_worker():" + snl
    + "            try:" + snl
    + "                _box['ok'] = worker.start()" + snl
    + "            except BaseException as exc:" + snl
    + "                _box['error'] = exc" + snl
    + "        _starter = Thread(target=_start_worker, daemon=True)" + snl
    + "        _starter.start()" + snl
    + "        _starter.join(20)" + snl
    + "        if _starter.is_alive():" + snl
    + "            try:" + snl
    + "                worker._terminate_owned()" + snl
    + "            except Exception:" + snl
    + "                pass" + snl
    + "            _boot_note('The account call did not return')" + snl
    + "            raise TimeoutError('account call')" + snl
    + "        if 'error' in _box:" + snl
    + "            raise _box['error']" + snl
    + "        _boot_note('Reading the symbol names')" + snl
    + "        mappings, catalog = build_fast_runtime_mappings(worker)" + snl
    + "        _boot_note('Symbol names are in')"
)
old_page = "        try:" + snl + "            host = cls("
new_page = "        _boot_note('Building the page')" + snl + "        try:" + snl + "            host = cls("
if "_boot_note('Asking MetaTrader for the account')" in stage_text:
    print("Startup stages are already shown.", flush=True)
elif old_stage not in stage_text or old_page not in stage_text:
    print("Could not show the startup stages.", flush=True)
    raise SystemExit(1)
else:
    stage_text = stage_text.replace(old_stage, new_stage, 1).replace(old_page, new_page, 1)
    stage.write_bytes(stage_text.encode("utf-8"))
    print("Startup now shows which step it is on.", flush=True)
