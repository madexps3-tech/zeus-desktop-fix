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

if "def signals_positions" not in text:
    positions_method = (
        "    async def signals_positions(self, request: web.Request) -> web.Response:" + newline
        + "        from zeus3.v19.signals_page import signals_positions" + newline
        + "        return await signals_positions(self, request)" + newline
        + newline
    )
    marker = "    def application(self) -> web.Application:"
    if marker not in text:
        print("Could not add the positions handler.", flush=True)
        raise SystemExit(1)
    text = text.replace(marker, positions_method + marker, 1)
    print("Positions handler added.", flush=True)

if "/api/v19/signals/positions" not in text:
    old_priority = 'app.router.add_post("/api/v19/signals/priority", self.signals_priority)'
    if old_priority not in text:
        print("Could not find the priority route.", flush=True)
        raise SystemExit(1)
    text = text.replace(
        old_priority,
        old_priority + newline + '        app.router.add_get("/api/v19/signals/positions", self.signals_positions)',
        1,
    )
    print("Positions route added.", flush=True)

if "def signals_manage" not in text:
    manage_method = (
        "    async def signals_manage(self, request: web.Request) -> web.Response:" + newline
        + "        from zeus3.v19.signals_page import signals_manage" + newline
        + "        return await signals_manage(self, request)" + newline
        + newline
    )
    marker = "    def application(self) -> web.Application:"
    if marker not in text:
        print("Could not add the manage handler.", flush=True)
        raise SystemExit(1)
    text = text.replace(marker, manage_method + marker, 1)
    print("Manage handler added.", flush=True)

if "/api/v19/signals/manage" not in text:
    old_positions = 'app.router.add_get("/api/v19/signals/positions", self.signals_positions)'
    if old_positions not in text:
        print("Could not find the positions route.", flush=True)
        raise SystemExit(1)
    text = text.replace(
        old_positions,
        old_positions + newline + '        app.router.add_post("/api/v19/signals/manage", self.signals_manage)',
        1,
    )
    print("Manage route added.", flush=True)

if "def signals_ice" not in text:
    ice_method = (
        "    async def signals_ice(self, request: web.Request) -> web.Response:" + newline
        + "        from zeus3.v19.signals_page import signals_ice" + newline
        + "        return await signals_ice(self, request)" + newline
        + newline
    )
    marker = "    def application(self) -> web.Application:"
    if marker not in text:
        print("Could not add the iceberg auto handler.", flush=True)
        raise SystemExit(1)
    text = text.replace(marker, ice_method + marker, 1)
    print("Iceberg auto handler added.", flush=True)

if "/api/v19/signals/ice" not in text:
    old_manage = 'app.router.add_post("/api/v19/signals/manage", self.signals_manage)'
    if old_manage not in text:
        print("Could not find the manage route.", flush=True)
        raise SystemExit(1)
    text = text.replace(
        old_manage,
        old_manage + newline + '        app.router.add_post("/api/v19/signals/ice", self.signals_ice)',
        1,
    )
    print("Iceberg auto route added.", flush=True)

if "def auto_page" not in text:
    auto_method = (
        "    async def auto_page(self, request: web.Request) -> web.Response:" + newline
        + "        from zeus3.v19.signals_page import render_auto_page" + newline
        + "        return web.Response(text=render_auto_page(), content_type='text/html')" + newline
        + newline
        + "    async def auto_state(self, request: web.Request) -> web.Response:" + newline
        + "        from zeus3.v19.signals_page import auto_state" + newline
        + "        return await auto_state(self, request)" + newline
        + newline
        + "    async def auto_save(self, request: web.Request) -> web.Response:" + newline
        + "        from zeus3.v19.signals_page import auto_save" + newline
        + "        return await auto_save(self, request)" + newline
        + newline
    )
    marker = "    def application(self) -> web.Application:"
    if marker not in text:
        print("Could not add the auto page.", flush=True)
        raise SystemExit(1)
    text = text.replace(marker, auto_method + marker, 1)
    print("Auto handlers added.", flush=True)

if "/v19/auto" not in text:
    old_ice = 'app.router.add_post("/api/v19/signals/ice", self.signals_ice)'
    if old_ice not in text:
        print("Could not find the iceberg route.", flush=True)
        raise SystemExit(1)
    text = text.replace(
        old_ice,
        old_ice + newline
        + '        app.router.add_get("/v19/auto", self.auto_page)' + newline
        + '        app.router.add_get("/api/v19/auto", self.auto_state)' + newline
        + '        app.router.add_post("/api/v19/auto", self.auto_save)',
        1,
    )
    print("Auto route added.", flush=True)

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

if "/v19/auto" not in nav:
    old_nav = '("SIGNALS", "/v19/signals"),'
    if old_nav not in nav:
        old_nav = '("CHART", "/v19/chart"),'
    if old_nav not in nav:
        print("Could not find a tab to place AUTO next to.", flush=True)
    else:
        nav = nav.replace(
            old_nav,
            old_nav + ("\r\n" if "\r\n" in nav else "\n") + '    ("AUTO", "/v19/auto"),',
            1,
        )
        shell.write_bytes(nav.encode("utf-8"))
        print("Auto tab added.", flush=True)

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

manual_needle = "        controls = self._owner_manual_controls_snapshot()"
manual_insert = (
    manual_needle + snl
    + "        if controls.get(\"acceptance_armed\") and not controls.get(\"kill_switch\") and isinstance(controls.get(\"binding\"), dict):" + snl
    + "            controls[\"owner_manual_enabled\"] = True" + snl
    + "            if not isinstance(controls.get(\"owner_manual_binding\"), dict):" + snl
    + "                controls[\"owner_manual_binding\"] = dict(controls[\"binding\"])"
)
if "controls[\"owner_manual_enabled\"] = True" in stage_text:
    print("The signals order no longer waits on the manual switch.", flush=True)
elif manual_needle not in stage_text:
    print("Could not find the manual order check.", flush=True)
    raise SystemExit(1)
else:
    stage_text = stage_text.replace(manual_needle, manual_insert, 1)
    stage.write_bytes(stage_text.encode("utf-8"))
    print("The signals order no longer waits on the manual switch.", flush=True)

slip_path = Path("src") / "zeus2" / "execution" / "mt5_native.py"
slip = slip_path.read_text(encoding="utf-8")
slip_nl = "\r\n" if "\r\n" in slip else "\n"
old_slip = (
    "            quote = self.quote(broker_symbol)" + slip_nl
    + "            request.update({" + slip_nl
    + '                "action": self.mt5.TRADE_ACTION_DEAL,' + slip_nl
    + '                "price": quote.ask if is_buy else quote.bid,' + slip_nl
    + '                "deviation": int(deviation_points),' + slip_nl
    + "            })"
)
new_slip = (
    "            quote = self.quote(broker_symbol)" + slip_nl
    + "            info = self.mt5.symbol_info(broker_symbol)" + slip_nl
    + "            point = float(getattr(info, \"point\", 0.0) or 0.0) if info is not None else 0.0" + slip_nl
    + "            spread_points = int(round((float(quote.ask) - float(quote.bid)) / point)) if point > 0 else 0" + slip_nl
    + "            slip = max(int(deviation_points), spread_points * 3, 100)" + slip_nl
    + "            request.update({" + slip_nl
    + '                "action": self.mt5.TRADE_ACTION_DEAL,' + slip_nl
    + '                "price": quote.ask if is_buy else quote.bid,' + slip_nl
    + '                "deviation": int(slip),' + slip_nl
    + "            })"
)
if "spread_points * 3" in slip:
    print("Market slippage already covers the spread.", flush=True)
elif old_slip not in slip:
    print("Could not find the market send.", flush=True)
    raise SystemExit(1)
else:
    slip_path.write_text(slip.replace(old_slip, new_slip, 1), encoding="utf-8")
    print("Market orders can move through the spread.", flush=True)

slip = slip_path.read_text(encoding="utf-8")
if "raw=None," in slip and "raw=raw," not in slip:
    print("Broker reply is already plain text.", flush=True)
elif "raw=raw," not in slip:
    print("Could not find the broker reply.", flush=True)
    raise SystemExit(1)
else:
    slip_path.write_text(slip.replace("raw=raw,", "raw=None,", 1), encoding="utf-8")
    print("Broker reply no longer jams the order result.", flush=True)

slip = slip_path.read_text(encoding="utf-8")
slip_nl = "\r\n" if "\r\n" in slip else "\n"
old_close = (
    "        quote = self.quote(symbol)" + slip_nl
    + "        closing_buy = side.upper() == \"SELL\"" + slip_nl
    + "        request = {" + slip_nl
    + "            \"action\": self.mt5.TRADE_ACTION_DEAL," + slip_nl
    + "            \"position\": int(ticket)," + slip_nl
    + "            \"symbol\": symbol," + slip_nl
    + "            \"volume\": float(volume)," + slip_nl
    + "            \"type\": self.mt5.ORDER_TYPE_BUY if closing_buy else self.mt5.ORDER_TYPE_SELL," + slip_nl
    + "            \"price\": quote.ask if closing_buy else quote.bid," + slip_nl
    + "            \"deviation\": int(deviation_points)," + slip_nl
)
new_close = (
    "        quote = self.quote(symbol)" + slip_nl
    + "        closing_buy = side.upper() == \"SELL\"" + slip_nl
    + "        info = self.mt5.symbol_info(symbol)" + slip_nl
    + "        point = float(getattr(info, \"point\", 0.0) or 0.0) if info is not None else 0.0" + slip_nl
    + "        spread_points = int(round((float(quote.ask) - float(quote.bid)) / point)) if point > 0 else 0" + slip_nl
    + "        close_slip = max(int(deviation_points), spread_points * 3, 100)" + slip_nl
    + "        request = {" + slip_nl
    + "            \"action\": self.mt5.TRADE_ACTION_DEAL," + slip_nl
    + "            \"position\": int(ticket)," + slip_nl
    + "            \"symbol\": symbol," + slip_nl
    + "            \"volume\": float(volume)," + slip_nl
    + "            \"type\": self.mt5.ORDER_TYPE_BUY if closing_buy else self.mt5.ORDER_TYPE_SELL," + slip_nl
    + "            \"price\": quote.ask if closing_buy else quote.bid," + slip_nl
    + "            \"deviation\": int(close_slip)," + slip_nl
)
if "close_slip = max" in slip:
    print("Close orders already cover the spread.", flush=True)
elif old_close not in slip:
    print("Could not find the close send.", flush=True)
    raise SystemExit(1)
else:
    slip_path.write_text(slip.replace(old_close, new_close, 1), encoding="utf-8")
    print("Close and partial orders can move through the spread.", flush=True)

web_path = Path("src") / "zeus3" / "v19" / "web.py"
web_text = web_path.read_text(encoding="utf-8")
web_nl = "\r\n" if "\r\n" in web_text else "\n"
old_send = (
    "            payload = await asyncio.to_thread(" + web_nl
    + "                self.runtime.execute_owner_order_clean," + web_nl
    + "                symbol=symbol," + web_nl
    + "                timeframe=timeframe," + web_nl
    + "                order_type=order_type," + web_nl
    + "                requested_entry=entry," + web_nl
    + "                stop=stop," + web_nl
    + "                targets=targets," + web_nl
    + "                target_specs=target_specs," + web_nl
    + "                requested_risk_pct=requested_risk," + web_nl
    + "                horizon_lane=horizon_lane," + web_nl
    + "                owner_note=owner_note," + web_nl
    + "            )"
)
new_send = (
    "            fast_entry = 0.0 if entry is None else entry" + web_nl
    + "            payload = None" + web_nl
    + "            try:" + web_nl
    + "                payload = await asyncio.to_thread(" + web_nl
    + "                    self.runtime.execute_owner_order_fast," + web_nl
    + "                    symbol=symbol," + web_nl
    + "                    timeframe=timeframe," + web_nl
    + "                    order_type=order_type," + web_nl
    + "                    requested_entry=fast_entry," + web_nl
    + "                    stop=stop," + web_nl
    + "                    targets=targets," + web_nl
    + "                    target_specs=target_specs," + web_nl
    + "                    requested_risk_pct=requested_risk," + web_nl
    + "                    horizon_lane=horizon_lane," + web_nl
    + "                    owner_note=owner_note," + web_nl
    + "                )" + web_nl
    + "            except Exception:" + web_nl
    + "                payload = None" + web_nl
    + "            fast_sent = bool(payload) and (" + web_nl
    + "                payload.get(\"submitted\") or payload.get(\"stage\") == \"BROKER_ACK\"" + web_nl
    + "                or int(payload.get(\"broker_writes\") or 0) > 0" + web_nl
    + "            )" + web_nl
    + "            if not fast_sent:" + web_nl
    + "                payload = await asyncio.to_thread(" + web_nl
    + "                    self.runtime.execute_owner_order_clean," + web_nl
    + "                    symbol=symbol," + web_nl
    + "                    timeframe=timeframe," + web_nl
    + "                    order_type=order_type," + web_nl
    + "                    requested_entry=entry," + web_nl
    + "                    stop=stop," + web_nl
    + "                    targets=targets," + web_nl
    + "                    target_specs=target_specs," + web_nl
    + "                    requested_risk_pct=requested_risk," + web_nl
    + "                    horizon_lane=horizon_lane," + web_nl
    + "                    owner_note=owner_note," + web_nl
    + "                )"
)
if "execute_owner_order_fast," in web_text and "fast_sent" in web_text:
    print("The trade button already uses the open connection.", flush=True)
elif old_send not in web_text:
    print("Could not find the trade send.", flush=True)
    raise SystemExit(1)
else:
    web_path.write_text(web_text.replace(old_send, new_send, 1), encoding="utf-8")
    print("The trade button uses the open MetaTrader connection.", flush=True)


risk_runtime = Path("src") / "zeus3" / "chart" / "runtime.py"
risk_text = risk_runtime.read_text(encoding="utf-8")
risk_nl = "\r\n" if "\r\n" in risk_text else "\n"
old_clean_cap = (
    "        if (" + risk_nl
    + "            risk_pct <= 0" + risk_nl
    + "            or risk_pct > float(controls[\"max_single_trade_risk_pct\"])" + risk_nl
    + "        ):" + risk_nl
    + "            raise ValueError(" + risk_nl
    + "                \"requested risk must be >0 and <= max single-trade risk\"" + risk_nl
    + "            )"
)
new_clean_cap = (
    "        if risk_pct <= 0:" + risk_nl
    + "            raise ValueError(\"requested risk must be >0\")" + risk_nl
    + "        if requested_risk_pct is not None:" + risk_nl
    + "            controls[\"max_single_trade_risk_pct\"] = max(" + risk_nl
    + "                float(controls[\"max_single_trade_risk_pct\"]), risk_pct" + risk_nl
    + "            )" + risk_nl
    + "            controls[\"max_total_open_unprotected_risk_pct\"] = max(" + risk_nl
    + "                float(controls[\"max_total_open_unprotected_risk_pct\"])," + risk_nl
    + "                float(controls[\"max_single_trade_risk_pct\"]) + risk_pct," + risk_nl
    + "            )"
)
old_fast_cap = (
    "        if (" + risk_nl
    + "            risk_pct <= 0" + risk_nl
    + "            or risk_pct > float(policy.max_single_trade_risk_pct)" + risk_nl
    + "        ):" + risk_nl
    + "            raise ValueError(" + risk_nl
    + "                \"V3 requested risk must be >0 and <= the owner-configured \"" + risk_nl
    + "                f\"single-trade cap ({policy.max_single_trade_risk_pct:g}%)\"" + risk_nl
    + "            )"
)
new_fast_cap = (
    "        if risk_pct <= 0:" + risk_nl
    + "            raise ValueError(\"V3 requested risk must be >0\")" + risk_nl
    + "        if requested_risk_pct is None and risk_pct > float(policy.max_single_trade_risk_pct):" + risk_nl
    + "            raise ValueError(" + risk_nl
    + "                \"V3 requested risk must be >0 and <= the owner-configured \"" + risk_nl
    + "                f\"single-trade cap ({policy.max_single_trade_risk_pct:g}%)\"" + risk_nl
    + "            )"
)
old_fast_total = (
    "        if (" + risk_nl
    + "            float(current_open_risk) + float(risk_pct)" + risk_nl
    + "            > float(policy.max_total_open_unprotected_risk_pct) + 1e-9" + risk_nl
    + "        ):"
)
new_fast_total = (
    "        if (" + risk_nl
    + "            requested_risk_pct is None" + risk_nl
    + "            and float(current_open_risk) + float(risk_pct)" + risk_nl
    + "            > float(policy.max_total_open_unprotected_risk_pct) + 1e-9" + risk_nl
    + "        ):"
)
old_fast_pass = (
    "            max_single_trade_risk_pct=float(policy.max_single_trade_risk_pct)," + risk_nl
    + "            max_total_open_risk_pct=float(" + risk_nl
    + "                policy.max_total_open_unprotected_risk_pct" + risk_nl
    + "            ),"
)
new_fast_pass = (
    "            max_single_trade_risk_pct=max(float(policy.max_single_trade_risk_pct), float(risk_pct))," + risk_nl
    + "            max_total_open_risk_pct=max(" + risk_nl
    + "                float(policy.max_total_open_unprotected_risk_pct)," + risk_nl
    + "                float(current_open_risk) + float(risk_pct)," + risk_nl
    + "            ),"
)
if "controls[\"max_single_trade_risk_pct\"] = max(" in risk_text and "requested_risk_pct is None and risk_pct >" in risk_text:
    print("A typed risk is already sent as typed.", flush=True)
else:
    missing = [
        name for name, block in (
            ("desk cap", old_clean_cap),
            ("fast cap", old_fast_cap),
            ("fast total", old_fast_total),
            ("fast pass", old_fast_pass),
        ) if block not in risk_text
    ]
    if missing:
        print("Could not free the typed risk: " + ", ".join(missing), flush=True)
        raise SystemExit(1)
    risk_text = risk_text.replace(old_clean_cap, new_clean_cap, 1)
    risk_text = risk_text.replace(old_fast_cap, new_fast_cap, 1)
    risk_text = risk_text.replace(old_fast_total, new_fast_total, 1)
    risk_text = risk_text.replace(old_fast_pass, new_fast_pass, 1)
    risk_runtime.write_bytes(risk_text.encode("utf-8"))
    print("A typed risk is sent as typed.", flush=True)

desk_path = Path("src") / "zeus2" / "execution" / "commercial_trade_desk.py"
desk_text = desk_path.read_text(encoding="utf-8")
old_hundred = "            if approved_cap <= 0 or approved_cap > 100:"
new_hundred = "            if approved_cap <= 0:"
old_hundred_msg = "                    \"Stage6 owner single-trade risk cap must be >0 and <=100\""
new_hundred_msg = "                    \"Stage6 owner single-trade risk cap must be >0\""
if old_hundred not in desk_text:
    print("The order path already accepts the typed risk.", flush=True)
else:
    desk_path.write_text(
        desk_text.replace(old_hundred, new_hundred, 1).replace(old_hundred_msg, new_hundred_msg, 1),
        encoding="utf-8",
    )
    print("The order path accepts the typed risk.", flush=True)

desk_ui = Path("src") / "zeus3" / "v19" / "trade_desk_v19_frontend.py"
ui = desk_ui.read_text(encoding="utf-8")
ui_changes = [
    (
        '<button id="manualBtn" class="statebtn" onclick="toggleAuthorityTD(\'OWNER_MANUAL\')">MANUAL</button>',
        "",
    ),
    ("stateBtnTD('manualBtn',man,'MANUAL ✓','MANUAL OFF');", ""),
    ("man=laneOn('OWNER_MANUAL')", "man=true"),
    ("if(!laneOn('OWNER_MANUAL'))blockers.push('MANUAL OFF');", ""),
    ("if(!laneOn('OWNER_MANUAL'))b.push('MANUAL OFF');", ""),
    (":!laneOn('OWNER_MANUAL')", ":false"),
    (":laneOn('OWNER_MANUAL')", ":true"),
    ("&&!laneOn('OWNER_MANUAL')", ""),
    ("&&laneOn('OWNER_MANUAL')", ""),
    ("+' · MANUAL '+(laneOn('OWNER_MANUAL')?'ON':'OFF')+", "+"),
]
if "OFF')++'" in ui:
    ui = ui.replace("OFF')++'", "OFF')+'")
    desk_ui.write_text(ui, encoding="utf-8")
    print("The trade desk script is repaired.", flush=True)
if 'id="manualBtn"' not in ui and "laneOn('OWNER_MANUAL')" not in ui:
    print("The manual switch is already gone.", flush=True)
else:
    updated = ui
    for old, new in ui_changes:
        updated = updated.replace(old, new)
    if 'id="manualBtn"' in updated or "laneOn('OWNER_MANUAL')" in updated:
        print("Could not remove the manual switch.", flush=True)
        raise SystemExit(1)
    desk_ui.write_text(updated, encoding="utf-8")
    print("The manual switch is gone. A trade no longer waits on it.", flush=True)
