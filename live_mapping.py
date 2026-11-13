from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from zeus3.contracts.broker import BrokerReadClient, BrokerSymbolCatalogEntry
from zeus3.contracts.instruments import BUILTIN_INSTRUMENTS
from zeus3.diagnostics.mapping_validation import resolve_semantic_cash_mapping
from zeus3.instruments.resolver import MappingResult, resolve_broker_symbol


def _iso_bar_time(raw: Any) -> datetime | None:
    if raw is None:
        return None
    try:
        return datetime.fromtimestamp(float(raw), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def diagnose_candidates(
    worker: BrokerReadClient,
    symbols: Iterable[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for broker_symbol in tuple(dict.fromkeys(str(x) for x in symbols if str(x).strip())):
        row: dict[str, Any] = {
            "broker_symbol": broker_symbol,
            "trade_mode": None,
            "quote_time": None,
            "m1_latest": None,
            "errors": [],
        }
        try:
            spec = worker.symbol_spec(broker_symbol)
            row["trade_mode"] = spec.trade_mode
        except Exception as exc:
            row["errors"].append(f"spec:{type(exc).__name__}:{exc}")
        try:
            quote = worker.quote(broker_symbol)
            row["quote_time"] = (
                quote.source_timestamp_utc.isoformat()
                if quote.source_timestamp_utc is not None
                else quote.received_at_utc.isoformat()
            )
        except Exception as exc:
            row["errors"].append(f"quote:{type(exc).__name__}:{exc}")
        rows.append(row)
    return rows


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def promote_unique_current_candidate(
    canonical_symbol: str,
    mapping: MappingResult,
    diagnostics: list[dict[str, Any]],
) -> tuple[MappingResult, str | None]:
    if not mapping.ambiguous or len(mapping.candidates) < 2:
        return mapping, None
    viable: list[str] = []
    for row in diagnostics:
        if row.get("broker_symbol") not in set(mapping.candidates):
            continue
        if int(row.get("trade_mode") if row.get("trade_mode") is not None else -1) != 4:
            continue
        q = _parse_iso(row.get("quote_time"))
        b = _parse_iso(row.get("m1_latest"))
        if q is None:
            continue
        if b is not None and abs((q - b).total_seconds()) > 15 * 60:
            continue
        viable.append(str(row["broker_symbol"]))
    if len(viable) != 1:
        return mapping, None
    return (
        MappingResult(
            canonical_symbol=str(canonical_symbol).upper(),
            broker_symbol=viable[0],
            confidence=99,
            ambiguous=False,
            candidates=mapping.candidates,
        ),
        "UNIQUE_FULL_TRADE_MODE_AND_CURRENT_M1_CANDIDATE",
    )


def _diagnosis_names(candidates: tuple[str, ...]) -> tuple[str, ...]:
    """A long weak list is not worth a bar download for every name."""
    return tuple(candidates[:4])


def _worth_diagnosing(mapping) -> bool:
    if int(mapping.confidence) >= 80:
        return True
    return int(mapping.confidence) == 0 and len(tuple(mapping.candidates)) <= 4


def _catalog_entries(worker: BrokerReadClient) -> tuple[BrokerSymbolCatalogEntry, ...]:
    method = getattr(worker, "symbol_catalog_entries", None)
    if not callable(method):
        return ()
    return tuple(method())


def build_runtime_mappings(
    worker: BrokerReadClient,
    *,
    canonical_symbols: Iterable[str] | None = None,
) -> tuple[dict[str, MappingResult], tuple[dict[str, Any], ...]]:
    broker_symbols = worker.symbol_catalog()
    entries: tuple[BrokerSymbolCatalogEntry, ...] | None = None

    requested = tuple(
        str(x).upper()
        for x in (
            canonical_symbols
            if canonical_symbols is not None
            else BUILTIN_INSTRUMENTS.keys()
        )
    )
    mappings: dict[str, MappingResult] = {}
    catalog: list[dict[str, Any]] = []

    for canonical in requested:
        definition = BUILTIN_INSTRUMENTS.get(canonical)
        if definition is None:
            continue
        mapping = resolve_broker_symbol(
            canonical,
            broker_symbols,
            aliases=definition.aliases,
        )
        reason: str | None = None

        if mapping.ambiguous and mapping.candidates and _worth_diagnosing(mapping):
            diagnostics = diagnose_candidates(worker, _diagnosis_names(mapping.candidates))
            mapping, reason = promote_unique_current_candidate(
                canonical, mapping, diagnostics
            )

        if not mapping.execution_ready and canonical in {"WTI", "BRENT"}:
            if entries is None:
                entries = _catalog_entries(worker)
            semantic = resolve_semantic_cash_mapping(
                canonical,
                mapping,
                entries or (),
                worker,
                lambda w, names: [
                    {
                        "broker_symbol": row["broker_symbol"],
                        "m1_latest_bar_utc": row["m1_latest"],
                        "quote": {"source_timestamp_utc": row["quote_time"]},
                        "symbol_spec": {"trade_mode": row["trade_mode"]},
                    }
                    for row in diagnose_candidates(w, names)
                ],
            )
            if semantic.mapping.execution_ready:
                mapping = semantic.mapping
                reason = semantic.reason

        mappings[canonical] = mapping
        catalog.append(
            {
                "canonical_symbol": canonical,
                "display_name": definition.display_name,
                "asset_class": definition.asset_class,
                "broker_symbol": mapping.broker_symbol,
                "mapped": mapping.execution_ready,
                "ambiguous": mapping.ambiguous,
                "confidence": mapping.confidence,
                "reason": reason,
            }
        )

    return mappings, tuple(catalog)

def build_fast_runtime_mappings(
    worker: BrokerReadClient,
    *,
    canonical_symbols: Iterable[str] | None = None,
) -> tuple[dict[str, MappingResult], tuple[dict[str, Any], ...]]:
    """Map by the broker's real names. Do not download the whole symbol list."""
    requested = tuple(
        str(x).upper()
        for x in (
            canonical_symbols
            if canonical_symbols is not None
            else BUILTIN_INSTRUMENTS.keys()
        )
    )
    cached = _load_symbol_cache()
    old_catalog = getattr(worker, "catalog_request_timeout_seconds", None)
    old_request = getattr(worker, "request_timeout_seconds", None)
    if old_catalog is not None:
        worker.catalog_request_timeout_seconds = 1.5
    if old_request is not None:
        worker.request_timeout_seconds = 1.5
    mappings: dict[str, MappingResult] = {}
    catalog: list[dict[str, Any]] = []
    timed_out = False
    try:
        for canonical in requested:
            definition = BUILTIN_INSTRUMENTS.get(canonical)
            if definition is None:
                continue
            found = None
            if not timed_out:
                try:
                    found = _first_live_name(
                        worker,
                        _name_attempts(canonical, definition.aliases, cached.get(canonical)),
                    )
                except TimeoutError:
                    timed_out = True
                    found = cached.get(canonical)
            else:
                found = cached.get(canonical)
            if not found:
                mapping = MappingResult(canonical, None, 0, False, ())
            else:
                mapping = MappingResult(canonical, found, 90, False, (found,))
                cached[canonical] = found
            mappings[canonical] = mapping
            catalog.append(
                {
                    "canonical_symbol": canonical,
                    "display_name": definition.display_name,
                    "asset_class": definition.asset_class,
                    "broker_symbol": mapping.broker_symbol,
                    "mapped": mapping.execution_ready,
                    "ambiguous": False,
                    "confidence": mapping.confidence,
                    "reason": "DIRECT_NAME" if mapping.execution_ready else None,
                }
            )
    finally:
        if old_catalog is not None:
            worker.catalog_request_timeout_seconds = old_catalog
        if old_request is not None:
            worker.request_timeout_seconds = old_request
    _save_symbol_cache(cached)
    return mappings, tuple(catalog)


def _name_attempts(canonical: str, aliases: tuple[str, ...], cached: str | None) -> tuple[str, ...]:
    ordered: list[str] = []
    if cached:
        ordered.append(cached)
    for base in (canonical, *aliases):
        ordered.append(base + "+")
        ordered.append(base)
    seen: set[str] = set()
    unique: list[str] = []
    for name in ordered:
        key = name.upper()
        if key in seen:
            continue
        seen.add(key)
        unique.append(name)
    return tuple(unique[:2])


def _first_live_name(worker: BrokerReadClient, names: tuple[str, ...]) -> str | None:
    for name in names:
        try:
            worker.symbol_spec(name)
        except Exception as exc:
            if "timed out" in str(exc).lower():
                raise TimeoutError(str(exc)) from exc
            continue
        return name
    return None


def _cache_path():
    from pathlib import Path
    return Path.cwd() / "ZEUS_SYMBOL_CACHE.json"


def _load_symbol_cache() -> dict[str, str]:
    import json
    path = _cache_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {str(k).upper(): str(v) for k, v in raw.items() if str(v).strip()}


def _save_symbol_cache(cache: dict[str, str]) -> None:
    import json
    try:
        _cache_path().write_text(json.dumps(cache, indent=2), encoding="utf-8")
    except OSError:
        return
