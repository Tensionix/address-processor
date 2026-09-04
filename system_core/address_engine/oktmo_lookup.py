from __future__ import annotations

import csv
from dataclasses import dataclass
import json
import re
import threading
from pathlib import Path
from typing import Any

from .region_reference import RegionEntry, best_region_match, load_region_entries, region_key
from .russian_morphology import lemmatize_word, morphology_status, phrase_case_forms, phrase_lemmas


_FUZZY_THRESHOLD = 72
_SCOPE_CANDIDATE_FUZZY_THRESHOLD = 86
_INDEX: dict[str, list[tuple[str, str, str]]] | None = None
_INDEX_KEYS: list[str] | None = None
_MUNICIPALITY_BY_CODE: dict[str, str] | None = None
_MUNICIPALITY_BY_LOCALITY_KEY: dict[str, list[tuple[str, str, str]]] | None = None
_CONTEXT_BY_CODE: dict[str, "OktmoLookupContext"] | None = None
_SUBJECT_TER_BY_REGION_KEY: dict[str, str] | None = None
_INDEX_SOURCE_KEY: tuple[str, float, int] | None = None
_LOOKUP_OKTMO_CACHE: dict[tuple[str, str, str, str], tuple[str, str] | None] = {}
_LOOKUP_MUNICIPALITY_CACHE: dict[tuple[str, str, str, str, str], str | None] = {}
_LOOKUP_CONTEXT_CACHE: dict[tuple[str, str, str, str], "OktmoLookupContext" | None] = {}
_SUBJECT_SCOPE_CACHE: tuple[tuple[tuple[str, float, int] | None, int], list["OktmoSubjectScope"]] | None = None
_REGION_SCOPE_OPTIONS_CACHE: tuple[tuple[tuple[str, float, int] | None, int], list[dict[str, str]]] | None = None
_MUNICIPALITY_SCOPE_OPTIONS_CACHE: dict[tuple[tuple[tuple[str, float, int] | None, int], str], list[dict[str, str]]] = {}
_SCOPE_KEY_PROFILE_CACHE: dict[tuple[tuple[str, float, int] | None, str, str], dict[str, Any]] = {}
_OKTMO_CACHE_LOCK = threading.RLock()

OKTMO_LOOKUP_CACHE_VERSION = 3
OKTMO_SCOPE_OPTIONS_VERSION = 2

SUBJECT_CONSTRAINT_WEIGHT = 0.0
MUNICIPALITY_KEY_WEIGHT = 45.0
LOCALITY_KEY_WEIGHT = 90.0
CONTEXTUAL_LOCALITY_KEY_WEIGHT = 20.0
FREQUENT_CONTEXT_LOCALITY_KEYS = {
    "березовый",
    "веселый",
    "восточный",
    "дальний",
    "дальнее",
    "дружный",
    "западный",
    "зеленый",
    "ключ",
    "ключи",
    "красный",
    "лесной",
    "луговой",
    "майский",
    "мирный",
    "молодежный",
    "новый",
    "озерный",
    "октябрьский",
    "первомайский",
    "победа",
    "прибрежный",
    "приморский",
    "радужный",
    "речной",
    "северный",
    "советский",
    "солнечный",
    "сосновый",
    "степной",
    "центральный",
    "южный",
}


@dataclass(frozen=True)
class _SubjectScopeRule:
    region_id: str
    value: str
    ter: str
    display_name: str
    include_kod1: tuple[tuple[int, int], ...] = ()
    exclude_kod1: tuple[tuple[int, int], ...] = ()


@dataclass(frozen=True)
class OktmoSubjectScope:
    value: str
    ter: str
    name: str
    region_id: str = ""
    include_kod1: tuple[tuple[int, int], ...] = ()
    exclude_kod1: tuple[tuple[int, int], ...] = ()

    def as_option(self) -> dict[str, str]:
        label = f"{self.name} ({self.ter})"
        return {
            "value": self.value,
            "label": label,
            "label_ru": label,
            "code": self.value,
            "ter": self.ter,
            "subject_ter": self.ter,
            "region_id": self.region_id,
        }


# GUI region selection is a federal-subject layer, not a raw OKTMO TER prefix.
# NAO, HMAO and YNAO share the technical TER of a parent oblast in Rosstat CSV,
# so the stable scope is encoded as TER + KOD1 range.
_PARENT_SUBJECT_SCOPE_RULES: tuple[_SubjectScopeRule, ...] = (
    _SubjectScopeRule(
        region_id="arkhangelskaya_oblast",
        value="11",
        ter="11",
        display_name="Архангельская область",
        exclude_kod1=((800, 999),),
    ),
    _SubjectScopeRule(
        region_id="tyumenskaya_oblast",
        value="71",
        ter="71",
        display_name="Тюменская область",
        exclude_kod1=((800, 999),),
    ),
)
_AUTONOMOUS_SUBJECT_SCOPE_RULES: tuple[_SubjectScopeRule, ...] = (
    _SubjectScopeRule(
        region_id="nenetskiy_ao",
        value="11:800-999",
        ter="11",
        display_name="Ненецкий автономный округ",
        include_kod1=((800, 999),),
    ),
    _SubjectScopeRule(
        region_id="khanty_mansiyskiy_ao_yugra",
        value="71:800-899",
        ter="71",
        display_name="Ханты-Мансийский автономный округ — Югра",
        include_kod1=((800, 899),),
    ),
    _SubjectScopeRule(
        region_id="yamalo_nenetskiy_ao",
        value="71:900-999",
        ter="71",
        display_name="Ямало-Ненецкий автономный округ",
        include_kod1=((900, 999),),
    ),
)
_PARENT_SUBJECT_SCOPE_BY_REGION_ID = {rule.region_id: rule for rule in _PARENT_SUBJECT_SCOPE_RULES}
_PARENT_SUBJECT_SCOPE_BY_TER = {rule.ter: rule for rule in _PARENT_SUBJECT_SCOPE_RULES}
_AUTONOMOUS_SUBJECT_SCOPE_BY_REGION_ID = {rule.region_id: rule for rule in _AUTONOMOUS_SUBJECT_SCOPE_RULES}


def clear_oktmo_caches(data_dir: Path | str | None = None) -> None:
    """Drop parsed Rosstat OKTMO indexes and derived GUI option caches."""

    with _OKTMO_CACHE_LOCK:
        _clear_oktmo_caches_locked(data_dir)


def _clear_oktmo_caches_locked(data_dir: Path | str | None = None) -> None:
    global _INDEX, _INDEX_KEYS, _MUNICIPALITY_BY_CODE, _MUNICIPALITY_BY_LOCALITY_KEY
    global _CONTEXT_BY_CODE, _SUBJECT_TER_BY_REGION_KEY, _INDEX_SOURCE_KEY, _SUBJECT_SCOPE_CACHE
    global _REGION_SCOPE_OPTIONS_CACHE

    _INDEX = None
    _INDEX_KEYS = None
    _MUNICIPALITY_BY_CODE = None
    _MUNICIPALITY_BY_LOCALITY_KEY = None
    _CONTEXT_BY_CODE = None
    _SUBJECT_TER_BY_REGION_KEY = None
    _INDEX_SOURCE_KEY = None
    _SUBJECT_SCOPE_CACHE = None
    _REGION_SCOPE_OPTIONS_CACHE = None
    _LOOKUP_OKTMO_CACHE.clear()
    _LOOKUP_MUNICIPALITY_CACHE.clear()
    _LOOKUP_CONTEXT_CACHE.clear()
    _MUNICIPALITY_SCOPE_OPTIONS_CACHE.clear()
    _SCOPE_KEY_PROFILE_CACHE.clear()
    if data_dir is not None:
        clear_oktmo_disk_cache(Path(data_dir))


def clear_oktmo_disk_cache(data_dir: Path) -> None:
    cache_path = _index_cache_path(data_dir)
    try:
        if cache_path.exists():
            cache_path.unlink()
    except OSError:
        pass


def _index_cache_path(data_dir: Path) -> Path:
    return data_dir / "rosstat" / "oktmo_lookup_cache.json"


def _csv_source_signature(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "source_name": path.name,
        "source_mtime_ns": stat.st_mtime_ns,
        "source_size": stat.st_size,
    }


def _list_tuple_rows(values: Any, width: int) -> list[tuple[str, ...]]:
    rows: list[tuple[str, ...]] = []
    if not isinstance(values, list):
        return rows
    for row in values:
        if not isinstance(row, list) or len(row) != width:
            continue
        rows.append(tuple(str(item) for item in row))
    return rows


def _load_index_cache(
    data_dir: Path,
    csv_path: Path,
) -> tuple[
    dict[str, list[tuple[str, str, str]]],
    dict[str, str],
    dict[str, list[tuple[str, str, str]]],
    dict[str, OktmoLookupContext],
    dict[str, str],
] | None:
    cache_path = _index_cache_path(data_dir)
    if not cache_path.exists():
        return None
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    try:
        if payload.get("cache_version") != OKTMO_LOOKUP_CACHE_VERSION:
            return None
        if payload.get("source") != _csv_source_signature(csv_path):
            return None
    except OSError:
        return None
    raw_index = payload.get("index")
    raw_locality = payload.get("municipality_by_locality_key")
    raw_context = payload.get("context_by_code")
    raw_municipality = payload.get("municipality_by_code")
    raw_subject_ter = payload.get("subject_ter_by_region_key")
    if not all(isinstance(item, dict) for item in (raw_index, raw_locality, raw_context, raw_municipality, raw_subject_ter)):
        return None
    index = {str(key): [tuple(row) for row in _list_tuple_rows(value, 3)] for key, value in raw_index.items()}
    municipality_by_locality_key = {
        str(key): [tuple(row) for row in _list_tuple_rows(value, 3)] for key, value in raw_locality.items()
    }
    context_by_code: dict[str, OktmoLookupContext] = {}
    for key, value in raw_context.items():
        if not isinstance(value, dict):
            continue
        context = _context_from_payload(value)
        if context is not None:
            context_by_code[str(key)] = context
    municipality_by_code = {str(key): str(value) for key, value in raw_municipality.items()}
    subject_ter_by_region_key = {str(key): str(value) for key, value in raw_subject_ter.items()}
    return index, municipality_by_code, municipality_by_locality_key, context_by_code, subject_ter_by_region_key


def _write_index_cache(
    data_dir: Path,
    csv_path: Path,
    index: dict[str, list[tuple[str, str, str]]],
    municipality_by_code: dict[str, str],
    municipality_by_locality_key: dict[str, list[tuple[str, str, str]]],
    context_by_code: dict[str, OktmoLookupContext],
    subject_ter_by_region_key: dict[str, str],
) -> None:
    cache_path = _index_cache_path(data_dir)
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "cache_version": OKTMO_LOOKUP_CACHE_VERSION,
            "source": _csv_source_signature(csv_path),
            "index": {key: [list(row) for row in rows] for key, rows in index.items()},
            "municipality_by_code": municipality_by_code,
            "municipality_by_locality_key": {
                key: [list(row) for row in rows] for key, rows in municipality_by_locality_key.items()
            },
            "context_by_code": {key: _context_payload(context) for key, context in context_by_code.items()},
            "subject_ter_by_region_key": subject_ter_by_region_key,
        }
        tmp_path = cache_path.with_suffix(cache_path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        tmp_path.replace(cache_path)
    except Exception:
        pass


@dataclass(frozen=True)
class OktmoLookupContext:
    oktmo_code: str
    oktmo_name: str
    municipality: str | None = None
    parent_subject: str | None = None
    subject: str | None = None
    federal_district: str | None = None
    autonomous_okrug: str | None = None
    subject_ter: str | None = None
    subject_scope: str | None = None


def _context_payload(context: OktmoLookupContext) -> dict[str, str]:
    return {
        "oktmo_code": context.oktmo_code,
        "oktmo_name": context.oktmo_name,
        "municipality": context.municipality or "",
        "parent_subject": context.parent_subject or "",
        "subject": context.subject or "",
        "federal_district": context.federal_district or "",
        "autonomous_okrug": context.autonomous_okrug or "",
        "subject_ter": context.subject_ter or "",
        "subject_scope": context.subject_scope or "",
    }


def _context_from_payload(payload: dict[str, Any]) -> OktmoLookupContext | None:
    code = str(payload.get("oktmo_code") or "")
    name = str(payload.get("oktmo_name") or "")
    if not code or not name:
        return None
    return OktmoLookupContext(
        oktmo_code=code,
        oktmo_name=name,
        municipality=str(payload.get("municipality") or "") or None,
        parent_subject=str(payload.get("parent_subject") or "") or None,
        subject=str(payload.get("subject") or "") or None,
        federal_district=str(payload.get("federal_district") or "") or None,
        autonomous_okrug=str(payload.get("autonomous_okrug") or "") or None,
        subject_ter=str(payload.get("subject_ter") or "") or None,
        subject_scope=str(payload.get("subject_scope") or "") or None,
    )


@dataclass(frozen=True)
class WeightedOktmoKey:
    value: str
    weight: float
    source: str
    role: str
    context_required: bool = False
    code: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "weight": self.weight,
            "source": self.source,
            "role": self.role,
            "context_required": self.context_required,
            "code": self.code or "",
        }

_SUBJECT_TER_HINTS = {
    "приморский край": "05",
    "приморский кр": "05",
    "уссурийск": "05",
    "уссурийский": "05",
    "уссурйиск": "05",
    "амурская область": "10",
    "амурская обл": "10",
    "благовещенск": "10",
    "благовещенский": "10",
    "иркутская область": "25",
    "иркутская обл": "25",
    "тюменская область": "71",
    "тюменская обл": "71",
    "тюмень": "71",
    "ханты-мансийский автономный округ": "71",
    "ханты мансийский автономный округ": "71",
    "хмао": "71",
    "югра": "71",
    "мегион": "71",
}
_SUBJECT_SCOPE_HINTS = {
    "архангельская область": "11",
    "архангельская обл": "11",
    "ненецкий автономный округ": "11:800-999",
    "ненецкий ао": "11:800-999",
    "нао": "11:800-999",
    "тюменская область": "71",
    "тюменская обл": "71",
    "тюмень": "71",
    "ханты-мансийский автономный округ": "71:800-899",
    "ханты мансийский автономный округ": "71:800-899",
    "ханты-мансийский ао": "71:800-899",
    "хмао": "71:800-899",
    "югра": "71:800-899",
    "сургут": "71:800-899",
    "сургутский": "71:800-899",
    "мегион": "71:800-899",
    "ямало-ненецкий автономный округ": "71:900-999",
    "ямало ненецкий автономный округ": "71:900-999",
    "ямало-ненецкий ао": "71:900-999",
    "янао": "71:900-999",
    "салехард": "71:900-999",
    "новый уренгой": "71:900-999",
}


def lookup_oktmo(
    territory_text: str | None,
    data_dir: Path,
    subject_hint: str | None = None,
    subject_ter_hint: str | None = None,
    municipality_hint: str | None = None,
) -> tuple[str, str] | None:
    """Return (oktmo_code, oktmo_name) for the best fuzzy match, or None."""
    if not territory_text or not territory_text.strip():
        return None
    _ensure_index(data_dir)
    if not _INDEX or not _INDEX_KEYS:
        return None
    query = _normalize_name(territory_text)
    if not query:
        return None
    subject_scope = _resolve_subject_scope(data_dir, subject_ter_hint) or _infer_subject_scope(data_dir, subject_hint or territory_text)
    subject_cache_key = subject_scope.value if subject_scope else _normalize_name(subject_hint or "")
    cache_key = (
        query,
        subject_cache_key,
        subject_scope.value if subject_scope else "",
        _municipality_match_key(municipality_hint),
    )
    if cache_key in _LOOKUP_OKTMO_CACHE:
        return _LOOKUP_OKTMO_CACHE[cache_key]
    keys = _keys_for_subject_scope(subject_scope)
    if not keys:
        _LOOKUP_OKTMO_CACHE[cache_key] = None
        return None
    try:
        from rapidfuzz import process as fz_process
        result = fz_process.extractOne(query, keys, score_cutoff=_FUZZY_THRESHOLD)
    except ImportError:
        result = _linear_best(query, keys)
    if result is None:
        _LOOKUP_OKTMO_CACHE[cache_key] = None
        return None
    matched_key = result[0]
    rows = _INDEX.get(matched_key, [])
    if subject_scope:
        rows = [row for row in rows if _oktmo_row_in_subject_scope(row, subject_scope)]
    rows = _prefer_oktmo_rows_for_municipality(rows, municipality_hint)
    if not rows:
        _LOOKUP_OKTMO_CACHE[cache_key] = None
        return None
    row = _select_best_oktmo_row(rows)
    resolved = (row[0], row[1])
    _LOOKUP_OKTMO_CACHE[cache_key] = resolved
    return resolved


def lookup_oktmo_context(
    territory_text: str | None,
    data_dir: Path,
    subject_hint: str | None = None,
    subject_ter_hint: str | None = None,
    municipality_hint: str | None = None,
) -> OktmoLookupContext | None:
    """Return the best OKTMO row with its municipal and regional context."""
    if not territory_text or not territory_text.strip():
        return None
    _ensure_index(data_dir)
    if not _INDEX or not _INDEX_KEYS:
        return None
    query = _normalize_name(territory_text)
    if not query:
        return None
    subject_scope = _resolve_subject_scope(data_dir, subject_ter_hint) or _infer_subject_scope(data_dir, subject_hint or territory_text)
    subject_cache_key = subject_scope.value if subject_scope else _normalize_name(subject_hint or "")
    cache_key = (
        query,
        subject_cache_key,
        subject_scope.value if subject_scope else "",
        _municipality_match_key(municipality_hint),
    )
    if cache_key in _LOOKUP_CONTEXT_CACHE:
        return _LOOKUP_CONTEXT_CACHE[cache_key]
    keys = _keys_for_subject_scope(subject_scope)
    if not keys:
        _LOOKUP_CONTEXT_CACHE[cache_key] = None
        return None
    try:
        from rapidfuzz import process as fz_process

        result = fz_process.extractOne(query, keys, score_cutoff=_FUZZY_THRESHOLD)
    except ImportError:
        result = _linear_best(query, keys)
    if result is None:
        _LOOKUP_CONTEXT_CACHE[cache_key] = None
        return None
    rows = _INDEX.get(result[0], [])
    if subject_scope:
        rows = [row for row in rows if _oktmo_row_in_subject_scope(row, subject_scope)]
    rows = _prefer_oktmo_rows_for_municipality(rows, municipality_hint)
    if not rows:
        _LOOKUP_CONTEXT_CACHE[cache_key] = None
        return None
    row = _select_best_oktmo_row(rows)
    context = _context_for_code(row[0]) or OktmoLookupContext(oktmo_code=row[0], oktmo_name=row[1], subject_ter=row[2])
    _LOOKUP_CONTEXT_CACHE[cache_key] = context
    return context


def lookup_municipality(
    territory_text: str | None,
    data_dir: Path,
    subject_hint: str | None = None,
    subject_ter_hint: str | None = None,
    oktmo_code: str | None = None,
    municipality_hint: str | None = None,
) -> str | None:
    """Return the parent municipality name for an OKTMO/locality reference."""
    _ensure_index(data_dir)
    code_key = _digits_only(oktmo_code)
    subject_scope = _resolve_subject_scope(data_dir, subject_ter_hint) or _infer_subject_scope(data_dir, subject_hint or territory_text)
    if code_key:
        cache_key = ("", subject_scope.value if subject_scope else "", "", code_key, _municipality_match_key(municipality_hint))
        if cache_key in _LOOKUP_MUNICIPALITY_CACHE:
            return _LOOKUP_MUNICIPALITY_CACHE[cache_key]
    else:
        cache_key = None
    if _MUNICIPALITY_BY_CODE and oktmo_code:
        municipality = _MUNICIPALITY_BY_CODE.get(code_key)
        if municipality and (not subject_scope or _context_in_subject_scope(_context_for_code(code_key), subject_scope)):
            if cache_key is not None:
                _LOOKUP_MUNICIPALITY_CACHE[cache_key] = municipality
            return municipality

    if not territory_text or not territory_text.strip():
        return None
    if not _MUNICIPALITY_BY_LOCALITY_KEY:
        return None

    query = _normalize_name(territory_text)
    if not query:
        return None
    subject_cache_key = subject_scope.value if subject_scope else _normalize_name(subject_hint or "")
    cache_key = (
        query,
        subject_cache_key,
        subject_scope.value if subject_scope else "",
        code_key,
        _municipality_match_key(municipality_hint),
    )
    if cache_key in _LOOKUP_MUNICIPALITY_CACHE:
        return _LOOKUP_MUNICIPALITY_CACHE[cache_key]
    keys = _municipality_keys_for_subject_scope(subject_scope)
    if not keys:
        _LOOKUP_MUNICIPALITY_CACHE[cache_key] = None
        return None
    try:
        from rapidfuzz import process as fz_process
        result = fz_process.extractOne(query, keys, score_cutoff=_FUZZY_THRESHOLD)
    except ImportError:
        result = _linear_best(query, keys)
    if result is None:
        _LOOKUP_MUNICIPALITY_CACHE[cache_key] = None
        return None

    rows = _MUNICIPALITY_BY_LOCALITY_KEY.get(result[0], [])
    if subject_scope:
        rows = [row for row in rows if _municipality_key_row_in_subject_scope(row, subject_scope)]
    rows = _prefer_municipality_rows(rows, municipality_hint)
    if not rows:
        _LOOKUP_MUNICIPALITY_CACHE[cache_key] = None
        return None
    municipality = _select_best_municipality(rows)[0]
    _LOOKUP_MUNICIPALITY_CACHE[cache_key] = municipality
    return municipality


def settlement_scope_candidates(
    data_dir: Path,
    query: str | None,
    *,
    subject_ter_hint: str | None = None,
    municipality_hint: str | None = None,
    limit: int = 40,
) -> list[dict[str, Any]]:
    """Return OKTMO locality/MO candidates for a GUI settlement search."""
    text = str(query or "").strip()
    if not text:
        return []
    _ensure_index(data_dir)
    if not _INDEX or not _INDEX_KEYS:
        return []

    subject_scope = _resolve_subject_scope(data_dir, subject_ter_hint) or _infer_subject_scope(data_dir, subject_ter_hint)
    municipality = _selected_municipality_name(municipality_hint, subject_scope)
    query_norms = [
        item
        for item in dict.fromkeys(
            _normalize_name(seed)
            for seed in (
                text,
                _clean_locality_search_name(text),
                _clean_municipality_search_name(text),
            )
        )
        if item
    ]
    if not query_norms:
        return []

    keys = _keys_for_subject_scope(subject_scope)
    scored_keys: dict[str, tuple[int, str]] = {}
    for norm in query_norms:
        if norm in _INDEX:
            scored_keys[norm] = (100, norm)
        try:
            from rapidfuzz import process as fz_process

            for key, score, _index in fz_process.extract(
                norm,
                keys,
                score_cutoff=_SCOPE_CANDIDATE_FUZZY_THRESHOLD,
                limit=max(limit * 8, 24),
            ):
                old = scored_keys.get(key)
                if old is None or int(score) > old[0]:
                    scored_keys[key] = (int(score), norm)
        except ImportError:
            for key in keys:
                score = _simple_similarity(norm, key)
                if score < _SCOPE_CANDIDATE_FUZZY_THRESHOLD:
                    continue
                old = scored_keys.get(key)
                if old is None or score > old[0]:
                    scored_keys[key] = (score, norm)

    rows_by_code: dict[str, tuple[OktmoLookupContext, int, str, bool]] = {}
    for key, (score, matched) in scored_keys.items():
        rows = _candidate_rows_for_key(key, subject_scope, municipality)
        exact = key in query_norms
        for code, _display_name, _ter in rows:
            context = _context_for_code(code)
            if not context or _is_catalog_group_heading(context.oktmo_name):
                continue
            current = rows_by_code.get(context.oktmo_code)
            if current is None or (score, exact) > (current[1], current[3]):
                rows_by_code[context.oktmo_code] = (context, score, matched, exact)

    rows = sorted(
        rows_by_code.values(),
        key=lambda item: _candidate_rank(item[0], item[1], item[3], subject_scope, municipality),
    )
    payloads = [_candidate_payload(context, score=score, matched_text=matched) for context, score, matched, _exact in rows[:limit]]
    if payloads:
        by_region_name: dict[tuple[str, str], int] = {}
        for item in payloads:
            key = (str(item.get("subject_scope") or item.get("subject_ter") or ""), _normalize_name(str(item.get("clean_name") or item.get("name") or "")))
            by_region_name[key] = by_region_name.get(key, 0) + 1
        for item in payloads:
            key = (str(item.get("subject_scope") or item.get("subject_ter") or ""), _normalize_name(str(item.get("clean_name") or item.get("name") or "")))
            item["unambiguous_in_region"] = by_region_name.get(key, 0) == 1
    return payloads


def oktmo_context_by_code(data_dir: Path, code: str | None) -> OktmoLookupContext | None:
    """Return a loaded OKTMO context for a GUI-selected code."""
    _ensure_index(data_dir)
    return _context_for_code(code)


def oktmo_key_terms_for_code(data_dir: Path, code: str | None) -> dict[str, Any]:
    """Build search-key terms for one selected OKTMO locality/MO code."""
    context = oktmo_context_by_code(data_dir, code)
    if context is None:
        raise ValueError(f"OKTMO entry was not found: {code}")
    kind = _candidate_kind(context)
    terms: list[str] = []
    if context.municipality:
        terms.extend(_municipality_terms(context.municipality))
    if kind == "settlement":
        terms.extend(_locality_terms(context.oktmo_name))
    else:
        terms.extend(_municipality_terms(context.oktmo_name))
    return {
        "kind": kind,
        "terms": _unique_terms(terms),
        "context": _candidate_payload(context, score=100, matched_text=context.oktmo_name),
    }


def region_scope_options(data_dir: Path) -> list[dict[str, str]]:
    """Return OKTMO region choices for GUI search narrowing."""

    with _OKTMO_CACHE_LOCK:
        return _region_scope_options_locked(data_dir)


def _region_scope_options_locked(data_dir: Path) -> list[dict[str, str]]:
    global _REGION_SCOPE_OPTIONS_CACHE
    csv_path = _discover_csv(data_dir)
    source_key = (_csv_source_key(csv_path), OKTMO_SCOPE_OPTIONS_VERSION)
    if _REGION_SCOPE_OPTIONS_CACHE and _REGION_SCOPE_OPTIONS_CACHE[0] == source_key:
        return list(_REGION_SCOPE_OPTIONS_CACHE[1])
    options = [scope.as_option() for scope in _subject_scopes(data_dir)]
    _REGION_SCOPE_OPTIONS_CACHE = (source_key, options)
    return list(options)


def municipality_scope_options(data_dir: Path, subject_ter: str | None = None) -> list[dict[str, str]]:
    """Return unique OKTMO municipality choices for an optional subject scope."""

    with _OKTMO_CACHE_LOCK:
        return _municipality_scope_options_locked(data_dir, subject_ter)


def _municipality_scope_options_locked(data_dir: Path, subject_ter: str | None = None) -> list[dict[str, str]]:
    csv_path = _discover_csv(data_dir)
    source_key = (_csv_source_key(csv_path), OKTMO_SCOPE_OPTIONS_VERSION)
    selected_scope = _resolve_subject_scope(data_dir, subject_ter)
    if not selected_scope:
        return []
    cache_key = (source_key, selected_scope.value)
    cached = _MUNICIPALITY_SCOPE_OPTIONS_CACHE.get(cache_key)
    if cached is not None:
        return list(cached)
    if not csv_path:
        _MUNICIPALITY_SCOPE_OPTIONS_CACHE[cache_key] = []
        return []

    rows: list[dict[str, str]] = []
    section1_by_code: dict[str, str] = {}
    municipality_heading_by_code: dict[str, str] = {}
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        for raw in csv.reader(handle, delimiter=";"):
            parsed = _scope_row(raw)
            if not parsed:
                continue
            rows.append(parsed)
            if parsed["section"] == "1":
                name1 = parsed["name1"]
                if name1 and not _is_catalog_group_heading(name1):
                    section1_by_code[parsed["code"]] = name1
            elif parsed["section"] == "2":
                heading = _municipality_from_group_heading(parsed["name1"])
                if heading:
                    municipality_heading_by_code[parsed["parent_code"]] = heading

    by_name: dict[str, dict[str, str]] = {}
    for row in rows:
        if not _scope_allows_row(selected_scope, row):
            continue
        municipality, municipality_code = _municipality_catalog_row_choice(row, section1_by_code, municipality_heading_by_code)
        name = str(municipality or "").strip()
        if not name:
            continue
        if not _looks_like_scope_municipality(name):
            continue
        key = _municipality_match_key(name)
        if not key:
            continue
        current = by_name.get(key)
        code = municipality_code or row["code"]
        if current and len(str(current.get("code") or "")) >= len(code):
            continue
        label = f"{name} | {code}" if code else name
        by_name[key] = {
            "value": code or name,
            "label": label,
            "label_ru": label,
            "code": code,
            "name": name,
        }
    options = sorted(by_name.values(), key=lambda item: str(item.get("label_ru") or item.get("label") or item.get("value")))
    _MUNICIPALITY_SCOPE_OPTIONS_CACHE[cache_key] = options
    return list(options)


def _subject_scopes(data_dir: Path) -> list[OktmoSubjectScope]:
    with _OKTMO_CACHE_LOCK:
        return _subject_scopes_locked(data_dir)


def _subject_scopes_locked(data_dir: Path) -> list[OktmoSubjectScope]:
    global _SUBJECT_SCOPE_CACHE
    csv_path = _discover_csv(data_dir)
    source_key = (_csv_source_key(csv_path), OKTMO_SCOPE_OPTIONS_VERSION)
    if _SUBJECT_SCOPE_CACHE and _SUBJECT_SCOPE_CACHE[0] == source_key:
        return list(_SUBJECT_SCOPE_CACHE[1])
    if not csv_path:
        _SUBJECT_SCOPE_CACHE = (source_key, [])
        return []

    regions = load_region_entries(data_dir)
    kod1_by_ter: dict[str, set[int]] = {}
    scopes_by_value: dict[str, OktmoSubjectScope] = {}
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.reader(handle, delimiter=";"):
            parsed = _scope_row(row)
            if not parsed or parsed["section"] != "1" or parsed["ter"] == "00":
                continue
            kod1_value = _kod1_int(parsed.get("kod1"))
            if kod1_value is not None:
                kod1_by_ter.setdefault(parsed["ter"], set()).add(kod1_value)
            if parsed["kod1"] != "000" or parsed["kod2"] != "000" or parsed["kod3"] != "000":
                continue
            subject = _subject_from_top_heading(parsed["name1"])
            if not subject:
                continue
            region = best_region_match(subject, regions)
            if _is_non_subject_scope(parsed["ter"], subject, region):
                continue
            rule = _parent_scope_rule(parsed["ter"], subject, region)
            name = _scope_display_name(rule, region, subject)
            scope = OktmoSubjectScope(
                value=rule.value if rule else parsed["ter"],
                ter=parsed["ter"],
                name=name,
                region_id=(rule.region_id if rule else (region.region_id if region else "")),
                include_kod1=rule.include_kod1 if rule else (),
                exclude_kod1=rule.exclude_kod1 if rule else (),
            )
            scopes_by_value.setdefault(scope.value, scope)

    regions_by_id = {region.region_id: region for region in regions}
    for rule in _AUTONOMOUS_SUBJECT_SCOPE_RULES:
        if not _scope_rule_has_rows(kod1_by_ter, rule):
            continue
        region = regions_by_id.get(rule.region_id)
        scope = OktmoSubjectScope(
            value=rule.value,
            ter=rule.ter,
            name=region.display_name if region else rule.display_name,
            region_id=rule.region_id,
            include_kod1=rule.include_kod1,
            exclude_kod1=rule.exclude_kod1,
        )
        scopes_by_value.setdefault(scope.value, scope)

    scopes = sorted(scopes_by_value.values(), key=lambda item: (_normalize_name(item.name), item.value))
    _SUBJECT_SCOPE_CACHE = (source_key, scopes)
    return list(scopes)


def _parent_scope_rule(ter: str, subject: str | None, region: RegionEntry | None) -> _SubjectScopeRule | None:
    if region and region.region_id in _PARENT_SUBJECT_SCOPE_BY_REGION_ID:
        return _PARENT_SUBJECT_SCOPE_BY_REGION_ID[region.region_id]
    rule = _PARENT_SUBJECT_SCOPE_BY_TER.get(ter)
    if not rule:
        return None
    subject_key = region_key(subject)
    if rule.region_id == "arkhangelskaya_oblast" and "архангельск" in subject_key:
        return rule
    if rule.region_id == "tyumenskaya_oblast" and "тюмен" in subject_key:
        return rule
    return None


def _scope_display_name(rule: _SubjectScopeRule | None, region: RegionEntry | None, fallback: str) -> str:
    if region:
        return region.display_name
    if rule:
        return rule.display_name
    return fallback


def _scope_rule_has_rows(kod1_by_ter: dict[str, set[int]], rule: _SubjectScopeRule) -> bool:
    values = kod1_by_ter.get(rule.ter) or set()
    return any(_kod1_in_ranges(kod1, rule.include_kod1) for kod1 in values)


def _is_non_subject_scope(ter: str, subject: str | None, region: RegionEntry | None) -> bool:
    text = " ".join((subject or "", region.display_name if region else "")).lower().replace("ё", "е")
    return "федеральная территория" in text or (ter == "02" and "сириус" in text)


def _scope_row(row: list[str]) -> dict[str, str] | None:
    if len(row) < 8 or str(row[5]).strip() not in {"1", "2"}:
        return None
    ter = str(row[0]).strip().zfill(2)
    kod1 = str(row[1]).strip().zfill(3)
    kod2 = str(row[2]).strip().zfill(3)
    kod3 = str(row[3]).strip().zfill(3)
    parent_code = ter + kod1 + kod2
    code = parent_code if str(row[5]).strip() == "1" else parent_code + kod3
    return {
        "ter": ter,
        "kod1": kod1,
        "kod2": kod2,
        "kod3": kod3,
        "section": str(row[5]).strip(),
        "name1": _clean_catalog_name(row[6]),
        "name2": _clean_catalog_name(row[7]),
        "parent_code": parent_code,
        "district_code": ter + kod1 + "000",
        "code": code,
    }


def _kod1_int(value: str | None) -> int | None:
    try:
        return int(str(value or "").strip().zfill(3))
    except ValueError:
        return None


def _kod1_in_ranges(kod1: int | None, ranges: tuple[tuple[int, int], ...]) -> bool:
    if kod1 is None:
        return False
    return any(start <= kod1 <= end for start, end in ranges)


def _scope_allows_kod1(scope: OktmoSubjectScope | None, kod1: int | None) -> bool:
    if not scope:
        return True
    if scope.include_kod1 and not _kod1_in_ranges(kod1, scope.include_kod1):
        return False
    if scope.exclude_kod1 and _kod1_in_ranges(kod1, scope.exclude_kod1):
        return False
    return True


def _scope_allows_code(scope: OktmoSubjectScope | None, code: str | None, ter: str | None = None) -> bool:
    if not scope:
        return True
    code_digits = _digits_only(code)
    row_ter = _valid_subject_ter(ter) or (code_digits[:2] if len(code_digits) >= 2 else "")
    if row_ter != scope.ter:
        return False
    kod1 = _kod1_int(code_digits[2:5] if len(code_digits) >= 5 else None)
    return _scope_allows_kod1(scope, kod1)


def _scope_allows_row(scope: OktmoSubjectScope | None, row: dict[str, str]) -> bool:
    if not scope:
        return True
    if row.get("ter") != scope.ter:
        return False
    return _scope_allows_kod1(scope, _kod1_int(row.get("kod1")))


def _oktmo_row_in_subject_scope(row: tuple[str, str, str], scope: OktmoSubjectScope | None) -> bool:
    return _scope_allows_code(scope, row[0], row[2])


def _municipality_key_row_in_subject_scope(row: tuple[str, str, str], scope: OktmoSubjectScope | None) -> bool:
    return _scope_allows_code(scope, row[2], row[1])


def _context_in_subject_scope(context: OktmoLookupContext | None, scope: OktmoSubjectScope | None) -> bool:
    return bool(context) and _scope_allows_code(scope, context.oktmo_code, context.subject_ter)


def _looks_like_scope_municipality(name: str | None) -> bool:
    if not name:
        return False
    text = name.lower().replace("ё", "е")
    return (
        _looks_like_primary_municipality(name)
        or "муниципальное образование" in text
        or "поселение" in text
        or "сельсовет" in text
        or "поссовет" in text
    )


def resolve_region_scope_ter(data_dir: Path, value: str | None) -> str | None:
    """Resolve a GUI region value to a two-digit OKTMO TER code."""
    scope = _resolve_subject_scope(data_dir, value)
    if scope:
        return scope.ter
    _ensure_index(data_dir)
    return _infer_subject_ter(value)


def resolve_region_scope_id(data_dir: Path, value: str | None) -> str | None:
    """Resolve a GUI region value to the canonical federal-subject scope id."""
    scope = _resolve_subject_scope(data_dir, value)
    return scope.value if scope else None


def _resolve_subject_scope(data_dir: Path, value: str | None) -> OktmoSubjectScope | None:
    text = str(value or "").strip()
    if not text:
        return None
    scopes = _subject_scopes(data_dir)
    if not scopes:
        direct_ter = _valid_subject_ter(text)
        return OktmoSubjectScope(value=direct_ter, ter=direct_ter, name="") if direct_ter else None
    direct = _subject_scope_by_value(scopes, text)
    if direct:
        return direct
    inferred = _infer_subject_scope(data_dir, text, scopes)
    if inferred:
        return inferred
    direct_ter = _valid_subject_ter(text)
    if direct_ter:
        return _subject_scope_by_value(scopes, direct_ter)
    return None


def _subject_scope_by_value(scopes: list[OktmoSubjectScope], value: str | None) -> OktmoSubjectScope | None:
    text = str(value or "").strip()
    if not text:
        return None
    text_key = _normalize_scope_value(text)
    ter = _valid_subject_ter(text)
    for scope in scopes:
        candidates = {
            _normalize_scope_value(scope.value),
            _normalize_scope_value(scope.name),
            _normalize_scope_value(scope.as_option().get("label")),
            _normalize_scope_value(scope.as_option().get("label_ru")),
            _normalize_scope_value(scope.as_option().get("code")),
        }
        if text_key in candidates:
            return scope
        if ter and scope.value == ter:
            return scope
    return None


def _normalize_scope_value(value: str | None) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\xa0", " ").strip()).lower().replace("ё", "е").replace("—", "-").replace("–", "-")


def resolve_municipality_scope_hint(data_dir: Path, value: str | None) -> str | None:
    """Resolve a GUI municipality value to the textual hint expected by lookup."""
    text = str(value or "").strip()
    if not text:
        return None
    digits = _digits_only(text)
    if digits:
        _ensure_index(data_dir)
        municipality = (_MUNICIPALITY_BY_CODE or {}).get(digits)
        if municipality:
            return municipality
    return re.sub(r"\s+\|\s+.+$", "", text).strip() or None


def oktmo_scope_key_profile(
    data_dir: Path,
    *,
    subject_ter_hint: str | None = None,
    municipality_hint: str | None = None,
) -> dict[str, Any]:
    """Build weighted OKTMO search keys for the selected scope.

    TER subject is a constraint frame, not a match trigger. Municipality adds
    medium-strength full/clean forms and expands to all locality forms in that
    municipality. Frequent one-word locality names require address/object context.
    """
    if not str(subject_ter_hint or "").strip() and not str(municipality_hint or "").strip():
        return _empty_scope_key_profile("no_scope")
    _ensure_index(data_dir)
    subject_scope = _resolve_subject_scope(data_dir, subject_ter_hint) or _infer_subject_scope(data_dir, subject_ter_hint)
    municipality = _selected_municipality_name(municipality_hint, subject_scope)
    cache_key = (_INDEX_SOURCE_KEY, subject_scope.value if subject_scope else "", _normalize_name(municipality or ""))
    cached = _SCOPE_KEY_PROFILE_CACHE.get(cache_key)
    if cached is not None:
        return cached
    weighted: list[WeightedOktmoKey] = []

    subject_name = _subject_name_for_scope(subject_scope)
    if subject_name:
        for term in _term_forms(subject_name):
            _append_weighted_key(
                weighted,
                term,
                weight=SUBJECT_CONSTRAINT_WEIGHT,
                source="subject",
                role="constraint",
                context_required=True,
            )

    if municipality:
        for term in _municipality_terms(municipality):
            _append_weighted_key(
                weighted,
                term,
                weight=MUNICIPALITY_KEY_WEIGHT,
                source="municipality",
                role="medium",
            )
        for context in _settlement_contexts_for_municipality(municipality, subject_scope):
            for term in _locality_terms(context.oktmo_name):
                contextual = _locality_requires_context(term)
                _append_weighted_key(
                    weighted,
                    term,
                    weight=CONTEXTUAL_LOCALITY_KEY_WEIGHT if contextual else LOCALITY_KEY_WEIGHT,
                    source="locality",
                    role="contextual" if contextual else "strong",
                    context_required=contextual,
                    code=context.oktmo_code,
                )

    flat_extra_keys = [
        item.value
        for item in weighted
        if item.weight > 0 and item.role != "constraint"
    ]
    profile = {
        "subject_ter": subject_scope.ter if subject_scope else "",
        "subject_scope": subject_scope.value if subject_scope else "",
        "subject": subject_name or "",
        "municipality": municipality or "",
        "extra_keys": flat_extra_keys,
        "weighted_extra_keys": [item.as_dict() for item in weighted],
        "counts": {
            "subject_constraint": sum(1 for item in weighted if item.source == "subject"),
            "municipality": sum(1 for item in weighted if item.source == "municipality"),
            "locality": sum(1 for item in weighted if item.source == "locality"),
            "context_required": sum(1 for item in weighted if item.context_required),
        },
        "morphology": morphology_status(),
    }
    _SCOPE_KEY_PROFILE_CACHE[cache_key] = profile
    return profile


def _empty_scope_key_profile(reason: str) -> dict[str, Any]:
    return {
        "subject_ter": "",
        "subject_scope": "",
        "subject": "",
        "municipality": "",
        "extra_keys": [],
        "weighted_extra_keys": [],
        "counts": {
            "subject_constraint": 0,
            "municipality": 0,
            "locality": 0,
            "context_required": 0,
        },
        "morphology": {"available": None, "engine": "", "skipped": reason},
    }


def _append_weighted_key(
    keys: list[WeightedOktmoKey],
    value: str | None,
    *,
    weight: float,
    source: str,
    role: str,
    context_required: bool = False,
    code: str | None = None,
) -> None:
    text = re.sub(r"\s+", " ", str(value or "").replace("\xa0", " ")).strip(" ,;")
    if not text:
        return
    key = _normalize_name(text)
    if not key:
        return
    for existing in keys:
        if _normalize_name(existing.value) == key and existing.source == source and existing.role == role:
            return
    keys.append(
        WeightedOktmoKey(
            value=text,
            weight=float(weight),
            source=source,
            role=role,
            context_required=bool(context_required),
            code=code,
        )
    )


def _term_forms(value: str | None, *, include_lemmas: bool = True) -> list[str]:
    terms: list[str] = []
    for seed in _unique_terms([value, *_clean_phrase_parts(value)]):
        terms.append(seed)
        terms.extend(phrase_case_forms(seed))
        if include_lemmas:
            terms.extend(phrase_lemmas(seed))
    return _unique_terms(terms)


def _municipality_terms(municipality: str | None) -> list[str]:
    clean = _clean_municipality_search_name(municipality)
    return _unique_terms([*_term_forms(municipality), *_term_forms(clean)])


def _locality_terms(locality: str | None) -> list[str]:
    clean = _clean_locality_search_name(locality)
    seeds = [clean] if clean else [locality]
    terms: list[str] = []
    for seed in seeds:
        terms.extend(_term_forms(seed, include_lemmas=False))
    return _unique_terms(terms)


def _subject_name_for_scope(subject_scope: OktmoSubjectScope | None) -> str | None:
    if not subject_scope:
        return None
    if subject_scope.name:
        return subject_scope.name
    ter = _valid_subject_ter(subject_scope.ter)
    if not ter or not _CONTEXT_BY_CODE:
        return None
    for context in _CONTEXT_BY_CODE.values():
        if context.subject_ter != ter or not _context_in_subject_scope(context, subject_scope):
            continue
        return context.parent_subject or context.subject
    return None


def _selected_municipality_name(municipality_hint: str | None, subject_scope: OktmoSubjectScope | None) -> str | None:
    hint = str(municipality_hint or "").strip()
    if not hint or not _MUNICIPALITY_BY_CODE:
        return None
    digits = _digits_only(hint)
    if digits:
        direct = _MUNICIPALITY_BY_CODE.get(digits)
        if direct and (not subject_scope or _context_in_subject_scope(_context_for_code(digits), subject_scope)):
            return direct
    candidates: list[str] = []
    for code, municipality in _MUNICIPALITY_BY_CODE.items():
        context = _context_for_code(code)
        if subject_scope and not _context_in_subject_scope(context, subject_scope):
            continue
        if _municipality_matches_hint(municipality, hint):
            candidates.append(municipality)
    if candidates:
        return max(_unique_terms(candidates), key=lambda item: _municipality_specificity(item))
    return re.sub(r"\s+\|\s+.+$", "", hint).strip() or None


def _settlement_contexts_for_municipality(
    municipality: str,
    subject_scope: OktmoSubjectScope | None,
) -> list[OktmoLookupContext]:
    if not _CONTEXT_BY_CODE:
        return []
    rows: list[OktmoLookupContext] = []
    seen_codes: set[str] = set()
    for context in _CONTEXT_BY_CODE.values():
        if context.oktmo_code in seen_codes:
            continue
        if subject_scope and not _context_in_subject_scope(context, subject_scope):
            continue
        if not _municipality_matches_hint(context.municipality, municipality):
            continue
        name = str(context.oktmo_name or "").strip()
        if not name or _is_catalog_group_heading(name) or _looks_like_parent_territory(name):
            continue
        if len(_digits_only(context.oktmo_code)) < 11:
            continue
        seen_codes.add(context.oktmo_code)
        rows.append(context)
    return sorted(rows, key=lambda item: (_clean_locality_search_name(item.oktmo_name), item.oktmo_code))


def _candidate_rows_for_key(
    key: str,
    subject_scope: OktmoSubjectScope | None,
    municipality: str | None,
) -> list[tuple[str, str, str]]:
    rows = list((_INDEX or {}).get(key, []))
    if subject_scope:
        rows = [row for row in rows if _oktmo_row_in_subject_scope(row, subject_scope)]
    if municipality:
        rows = [
            row
            for row in rows
            if _municipality_matches_hint((_context_for_code(row[0]) or OktmoLookupContext(row[0], row[1])).municipality, municipality)
        ]
    return rows


def _candidate_kind(context: OktmoLookupContext) -> str:
    code = _digits_only(context.oktmo_code)
    if len(code) >= 11 and not _looks_like_parent_territory(context.oktmo_name):
        return "settlement"
    return "municipality"


def _candidate_rank(
    context: OktmoLookupContext,
    score: int,
    exact: bool,
    subject_scope: OktmoSubjectScope | None,
    municipality: str | None,
) -> tuple[int, int, int, int, str]:
    kind = _candidate_kind(context)
    return (
        0 if exact else 1,
        0 if subject_scope and _context_in_subject_scope(context, subject_scope) else 1,
        0 if municipality and _municipality_matches_hint(context.municipality, municipality) else 1,
        0 if kind == "settlement" else 1,
        f"{100 - int(score):03d}:{_clean_locality_search_name(context.oktmo_name)}:{context.oktmo_code}",
    )


def _candidate_payload(context: OktmoLookupContext, *, score: int, matched_text: str) -> dict[str, Any]:
    kind = _candidate_kind(context)
    clean_name = _clean_locality_search_name(context.oktmo_name) if kind == "settlement" else _clean_municipality_search_name(context.oktmo_name)
    label = " | ".join(
        item
        for item in (
            context.oktmo_name,
            f"МО: {context.municipality}" if context.municipality else "",
            f"регион: {context.subject or context.parent_subject}" if (context.subject or context.parent_subject) else "",
            f"ОКТМО {context.oktmo_code}",
        )
        if item
    )
    return {
        "id": context.oktmo_code,
        "value": context.oktmo_code,
        "code": context.oktmo_code,
        "label": label,
        "label_ru": label,
        "name": context.oktmo_name,
        "clean_name": clean_name,
        "kind": kind,
        "municipality": context.municipality or "",
        "region": context.subject or context.parent_subject or "",
        "subject": context.subject or "",
        "parent_subject": context.parent_subject or "",
        "federal_district": context.federal_district or "",
        "autonomous_okrug": context.autonomous_okrug or "",
        "subject_ter": context.subject_ter or "",
        "subject_scope": context.subject_scope or "",
        "score": int(score),
        "matched_text": matched_text,
        "unambiguous_in_region": False,
    }


def _clean_municipality_search_name(value: str | None) -> str:
    text = str(value or "").strip(" ,;")
    if not text:
        return ""
    text = re.sub(
        r"(?i)\b(?:городской|муниципальный)\s+(?:округ|район)\b",
        " ",
        text,
    )
    text = re.sub(r"(?i)\bмуниципальное\s+образование\b", " ", text)
    text = re.sub(r"(?i)\bгород\s+", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" ,;")
    return text


def _clean_locality_search_name(value: str | None) -> str:
    text = str(value or "").strip(" ,;")
    if not text:
        return ""
    text = re.sub(
        r"(?i)^(?:город|г\.?|село|с\.?|деревня|д\.?|пос[её]лок|пос\.?|п\.?|"
        r"рабочий\s+пос[её]лок|р\.?\s*п\.?|пос[её]лок\s+городского\s+типа|пгт)\s+",
        "",
        text,
    )
    text = re.sub(r"\s+", " ", text).strip(" ,;")
    return text


def _locality_requires_context(value: str | None) -> bool:
    key = _normalize_name(_clean_locality_search_name(value))
    if not key:
        return True
    if key in FREQUENT_CONTEXT_LOCALITY_KEYS:
        return True
    parts = key.split()
    if len(parts) != 1:
        return False
    if lemmatize_word(parts[0]) in FREQUENT_CONTEXT_LOCALITY_KEYS:
        return True
    return False


def _clean_phrase_parts(value: str | None) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    clean_municipality = _clean_municipality_search_name(text)
    clean_locality = _clean_locality_search_name(text)
    return [item for item in (clean_municipality, clean_locality) if item and item != text]


def _unique_terms(values: list[str | None]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = re.sub(r"\s+", " ", str(value or "").replace("\xa0", " ")).strip(" ,;")
        key = _normalize_name(text) if text else ""
        if not text or not key or key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def _ensure_index(data_dir: Path) -> None:
    with _OKTMO_CACHE_LOCK:
        _ensure_index_locked(data_dir)


def _ensure_index_locked(data_dir: Path) -> None:
    global _INDEX, _INDEX_KEYS, _MUNICIPALITY_BY_CODE, _MUNICIPALITY_BY_LOCALITY_KEY
    global _CONTEXT_BY_CODE, _SUBJECT_TER_BY_REGION_KEY, _INDEX_SOURCE_KEY
    csv_path = _discover_csv(data_dir)
    source_key = _csv_source_key(csv_path)
    if _INDEX is not None and _INDEX_SOURCE_KEY == source_key:
        return
    _LOOKUP_OKTMO_CACHE.clear()
    _LOOKUP_MUNICIPALITY_CACHE.clear()
    _LOOKUP_CONTEXT_CACHE.clear()
    _SCOPE_KEY_PROFILE_CACHE.clear()
    _INDEX_SOURCE_KEY = source_key
    if not csv_path:
        _INDEX = {}
        _INDEX_KEYS = []
        _MUNICIPALITY_BY_CODE = {}
        _MUNICIPALITY_BY_LOCALITY_KEY = {}
        _CONTEXT_BY_CODE = {}
        _SUBJECT_TER_BY_REGION_KEY = {}
        return
    cached = _load_index_cache(data_dir, csv_path)
    if cached is not None:
        (
            _INDEX,
            _MUNICIPALITY_BY_CODE,
            _MUNICIPALITY_BY_LOCALITY_KEY,
            _CONTEXT_BY_CODE,
            _SUBJECT_TER_BY_REGION_KEY,
        ) = cached
        _INDEX_KEYS = list(_INDEX.keys())
        return
    regions = load_region_entries(data_dir)
    (
        _INDEX,
        _MUNICIPALITY_BY_CODE,
        _MUNICIPALITY_BY_LOCALITY_KEY,
        _CONTEXT_BY_CODE,
        _SUBJECT_TER_BY_REGION_KEY,
    ) = _build_index(csv_path, regions)
    _INDEX_KEYS = list(_INDEX.keys())
    _write_index_cache(
        data_dir,
        csv_path,
        _INDEX,
        _MUNICIPALITY_BY_CODE,
        _MUNICIPALITY_BY_LOCALITY_KEY,
        _CONTEXT_BY_CODE,
        _SUBJECT_TER_BY_REGION_KEY,
    )


def warm_oktmo_cache(data_dir: Path | str) -> dict[str, Any]:
    """Build or load the current disk index and prime the SUB option cache."""

    root = Path(data_dir)
    with _OKTMO_CACHE_LOCK:
        _ensure_index_locked(root)
        regions = _region_scope_options_locked(root)
        cache_path = _index_cache_path(root)
        return {
            "cache_path": str(cache_path),
            "cache_exists": cache_path.exists(),
            "cache_bytes": cache_path.stat().st_size if cache_path.exists() else 0,
            "index_keys": len(_INDEX or {}),
            "contexts": len(_CONTEXT_BY_CODE or {}),
            "municipalities": len(_MUNICIPALITY_BY_CODE or {}),
            "regions": len(regions),
        }


def _csv_source_key(path: Path | None) -> tuple[str, float, int] | None:
    if not path:
        return None
    try:
        return (str(path.resolve()), path.stat().st_mtime, OKTMO_LOOKUP_CACHE_VERSION)
    except OSError:
        return (str(path), 0.0, OKTMO_LOOKUP_CACHE_VERSION)


def _discover_csv(data_dir: Path) -> Path | None:
    rosstat_dir = data_dir / "rosstat"
    if not rosstat_dir.exists():
        return None
    candidates = [candidate for candidate in rosstat_dir.glob("data-*.csv") if candidate.is_file()]
    if not candidates:
        return None
    return max(candidates, key=_rosstat_data_file_sort_key)


def _rosstat_data_file_sort_key(path: Path) -> tuple[str, float, str]:
    """Prefer the latest monthly Rosstat snapshot by timestamp in data-* filename."""
    match = re.search(r"data-(\d{8}T\d{4})", path.name, flags=re.IGNORECASE)
    timestamp = match.group(1) if match else ""
    try:
        modified = path.stat().st_mtime
    except OSError:
        modified = 0.0
    return timestamp, modified, path.name.lower()


def _build_index(
    csv_path: Path,
    regions: tuple[RegionEntry, ...],
) -> tuple[
    dict[str, list[tuple[str, str, str]]],
    dict[str, str],
    dict[str, list[tuple[str, str, str]]],
    dict[str, OktmoLookupContext],
    dict[str, str],
]:
    try:
        import pandas as pd
    except ImportError:
        return {}, {}, {}, {}, {}
    try:
        df = pd.read_csv(
            csv_path,
            sep=";",
            header=None,
            dtype=str,
            encoding="utf-8",
            on_bad_lines="skip",
        )
    except Exception:
        return {}, {}, {}, {}, {}

    # Columns: 0=TER, 1=KOD1, 2=KOD2, 3=KOD3, 4=check, 5=section, 6=NAME1, 7=NAME2
    if df.shape[1] < 8:
        return {}, {}, {}, {}, {}

    df.columns = list(range(df.shape[1]))
    rows = df[df[5].isin(["1", "2"])].copy()
    rows["ter"] = rows[0].str.strip().str.zfill(2)
    rows["kod1"] = rows[1].str.strip().str.zfill(3)
    rows["kod2"] = rows[2].str.strip().str.zfill(3)
    rows["kod3"] = rows[3].str.strip().str.zfill(3)
    rows["parent_code"] = rows["ter"] + rows["kod1"] + rows["kod2"]
    rows["district_code"] = rows["ter"] + rows["kod1"] + "000"
    rows["code"] = rows["parent_code"]
    rows.loc[rows[5] == "2", "code"] = rows["code"] + rows[3].str.strip().str.zfill(3)

    subject_by_ter, federal_by_ter, subject_ter_by_region_key = _build_subject_maps(rows, regions)
    autonomous_by_code = _build_autonomous_context(rows, regions)

    section1_by_code: dict[str, str] = {}
    municipality_heading_by_code: dict[str, str] = {}
    for _, row in rows[rows[5] == "1"].iterrows():
        name1 = _clean_catalog_name(row[6])
        if not name1 or _is_catalog_group_heading(name1):
            continue
        section1_by_code[str(row["code"])] = name1
    for _, row in rows[rows[5] == "2"].iterrows():
        heading = _municipality_from_group_heading(_clean_catalog_name(row[6]))
        if heading:
            municipality_heading_by_code[str(row["parent_code"])] = heading

    index: dict[str, list[tuple[str, str, str]]] = {}
    municipality_by_code: dict[str, str] = {}
    municipality_by_locality_key: dict[str, list[tuple[str, str, str]]] = {}
    context_by_code: dict[str, OktmoLookupContext] = {}
    for _, row in rows.iterrows():
        code = str(row["code"])
        ter = str(row["ter"])
        name1 = _clean_catalog_name(row[6])
        name2 = _clean_catalog_name(row[7])
        if name1 and name1 not in {"nan", ""} and "населенные пункты" not in name1.lower():
            _add_index(index, name1, code, name1, ter)
        if name2 and name2 not in {"nan", ""}:
            _add_index(index, name2, code, name1 or name2, ter)

        municipality = _municipality_for_catalog_row(row, section1_by_code, municipality_heading_by_code)
        if not municipality:
            continue
        municipality_by_code[code] = municipality
        autonomous_okrug = _autonomous_okrug_for_code(code, autonomous_by_code)
        subject_scope = _subject_scope_value_for_code(code, ter, autonomous_okrug, subject_by_ter.get(ter))
        context_by_code[code] = OktmoLookupContext(
            oktmo_code=code,
            oktmo_name=name1 or name2,
            municipality=municipality,
            parent_subject=subject_by_ter.get(ter),
            subject=autonomous_okrug or subject_by_ter.get(ter),
            federal_district=federal_by_ter.get(ter),
            autonomous_okrug=autonomous_okrug,
            subject_ter=ter,
            subject_scope=subject_scope,
        )
        if name1 and not _is_catalog_group_heading(name1):
            _add_municipality_key(municipality_by_locality_key, name1, municipality, ter, code)
        if name2:
            _add_municipality_key(municipality_by_locality_key, name2, municipality, ter, code)
    return index, municipality_by_code, municipality_by_locality_key, context_by_code, subject_ter_by_region_key


def _add_index(index: dict[str, list[tuple[str, str, str]]], raw_key: str, code: str, display_name: str, ter: str) -> None:
    key = _normalize_name(raw_key)
    if not key:
        return
    index.setdefault(key, [])
    row = (code, display_name, ter)
    if row not in index[key]:
        index[key].append(row)


def _add_municipality_key(
    index: dict[str, list[tuple[str, str, str]]],
    raw_key: str,
    municipality: str,
    ter: str,
    code: str,
) -> None:
    key = _normalize_name(raw_key)
    if not key:
        return
    index.setdefault(key, [])
    row = (municipality, ter, code)
    if row not in index[key]:
        index[key].append(row)


def _build_subject_maps(rows, regions: tuple[RegionEntry, ...]) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    subject_by_ter: dict[str, str] = {}
    federal_by_ter: dict[str, str] = {}
    subject_ter_by_region_key: dict[str, str] = {}
    top_rows = rows[
        (rows["kod1"] == "000")
        & (rows["kod2"] == "000")
        & (rows["kod3"] == "000")
        & (rows[5] == "1")
        & (rows["ter"] != "00")
    ]
    for _, row in top_rows.iterrows():
        ter = str(row["ter"])
        subject = _subject_from_top_heading(_clean_catalog_name(row[6]))
        if not subject:
            continue
        region = best_region_match(subject, regions)
        display = region.display_name if region else subject
        subject_by_ter[ter] = display
        if region and region.federal_district:
            federal_by_ter[ter] = region.federal_district
        for key in _subject_keys(subject, region):
            subject_ter_by_region_key.setdefault(key, ter)
    return subject_by_ter, federal_by_ter, subject_ter_by_region_key


def _build_autonomous_context(rows, regions: tuple[RegionEntry, ...]) -> dict[str, str]:
    contexts: dict[str, str] = {}
    autonomous_regions = tuple(region for region in regions if region.is_autonomous_okrug)
    if not autonomous_regions:
        return contexts
    for _, row in rows[rows[5] == "1"].iterrows():
        name = _clean_catalog_name(row[6])
        if "автоном" not in name.lower().replace("ё", "е"):
            continue
        region = best_region_match(name, autonomous_regions)
        if not region:
            continue
        code = str(row["code"])
        contexts[code] = region.display_name
        ter = str(row["ter"])
        kod1 = str(row["kod1"])
        rule = _AUTONOMOUS_SUBJECT_SCOPE_BY_REGION_ID.get(region.region_id)
        if rule:
            for start, end in rule.include_kod1:
                contexts[f"{ter}:{start:03d}-{end:03d}"] = region.display_name
        elif kod1 != "000":
            contexts[f"{ter}:{kod1}"] = region.display_name
    return contexts


def _autonomous_okrug_for_code(code: str, autonomous_by_code: dict[str, str]) -> str | None:
    digits = _digits_only(code)
    if len(digits) >= 5:
        ter = digits[:2]
        kod1 = _kod1_int(digits[2:5])
        for key, value in autonomous_by_code.items():
            if ":" not in key or "-" not in key:
                continue
            key_ter, raw_range = key.split(":", 1)
            if key_ter != ter:
                continue
            start_text, end_text = raw_range.split("-", 1)
            if _kod1_in_ranges(kod1, ((_kod1_int(start_text) or 0, _kod1_int(end_text) or 0),)):
                return value
        block_key = f"{ter}:{digits[2:5]}"
        if block_key in autonomous_by_code:
            return autonomous_by_code[block_key]
    numeric_contexts = [(context_code, value) for context_code, value in autonomous_by_code.items() if ":" not in context_code]
    for context_code, value in sorted(numeric_contexts, key=lambda item: len(item[0]), reverse=True):
        if digits.startswith(context_code):
            return value
    return None


def _subject_scope_value_for_code(
    code: str,
    ter: str,
    autonomous_okrug: str | None,
    parent_subject: str | None,
) -> str:
    digits = _digits_only(code)
    kod1 = _kod1_int(digits[2:5] if len(digits) >= 5 else None)
    for rule in _AUTONOMOUS_SUBJECT_SCOPE_RULES:
        if rule.ter == ter and _kod1_in_ranges(kod1, rule.include_kod1):
            return rule.value
    parent_key = region_key(parent_subject)
    for rule in _PARENT_SUBJECT_SCOPE_RULES:
        if rule.ter != ter:
            continue
        if rule.region_id == "arkhangelskaya_oblast" and "архангельск" in parent_key:
            return rule.value
        if rule.region_id == "tyumenskaya_oblast" and "тюмен" in parent_key:
            return rule.value
    return ter


def _subject_from_top_heading(name: str | None) -> str | None:
    text = str(name or "").strip(" /")
    if not text:
        return None
    text = re.sub(r"^муниципальные\s+образования\s+", "", text, flags=re.IGNORECASE)
    text = re.sub(
        r"^населенные\s+пункты,?\s+входящие\s+в\s+состав\s+муниципальных\s+образований\s+",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\s+", " ", text).strip(" ,/")
    return text or None


def _subject_keys(subject: str, region: RegionEntry | None) -> tuple[str, ...]:
    variants = [subject]
    if region:
        variants.extend([region.display_name, region.short_name, *region.aliases])
    return tuple(key for key in (region_key(value) for value in variants) if key)


def _context_for_code(code: str | None) -> OktmoLookupContext | None:
    if not code or not _CONTEXT_BY_CODE:
        return None
    digits = _digits_only(code)
    if digits in _CONTEXT_BY_CODE:
        return _CONTEXT_BY_CODE[digits]
    for length in range(len(digits), 1, -1):
        candidate = digits[:length]
        if candidate in _CONTEXT_BY_CODE:
            return _CONTEXT_BY_CODE[candidate]
    return None


def _municipality_for_catalog_row(
    row,
    section1_by_code: dict[str, str],
    municipality_heading_by_code: dict[str, str],
) -> str | None:
    return _municipality_catalog_row_choice(row, section1_by_code, municipality_heading_by_code)[0]


def _municipality_catalog_row_choice(
    row,
    section1_by_code: dict[str, str],
    municipality_heading_by_code: dict[str, str],
) -> tuple[str | None, str]:
    # Both candidates are derived from Rosstat OKTMO rows. Source text may
    # narrow lookup elsewhere, but it must not invent the municipality level.
    parent_code = str(row["parent_code"])
    district_code = str(row["district_code"])
    immediate = _prefer_typed_municipality_name(
        section1_by_code.get(parent_code),
        municipality_heading_by_code.get(parent_code),
    )
    district = _prefer_typed_municipality_name(
        section1_by_code.get(district_code),
        municipality_heading_by_code.get(district_code),
    )
    if immediate and district and parent_code != district_code:
        if _looks_like_local_settlement(immediate) and _looks_like_primary_municipality(district):
            return district, district_code
    if immediate:
        return immediate, parent_code
    if district:
        return district, district_code
    return None, ""


def _prefer_typed_municipality_name(section_name: str | None, heading_name: str | None) -> str | None:
    if not section_name:
        return heading_name
    if not heading_name:
        return section_name
    if _looks_like_primary_municipality(section_name):
        return section_name
    if _looks_like_local_settlement(section_name) and _looks_like_primary_municipality(heading_name):
        return heading_name
    if _looks_like_primary_municipality(heading_name) and _municipality_matches_hint(heading_name, section_name):
        return heading_name
    return section_name


def _municipality_from_group_heading(name: str | None) -> str | None:
    text = str(name or "").strip(" /")
    if not text:
        return None
    match = re.search(r"населенные пункты,\s*входящие\s+в\s+состав\s+(.+)$", text, flags=re.IGNORECASE)
    if not match:
        return None
    body = re.sub(r"\s+", " ", match.group(1)).strip(" ,")
    if not body:
        return None

    ordered_patterns = (
        (r"\bгородского\s+округа\s+(.+)$", "городской округ"),
        (r"\bмуниципального\s+округа\s+(.+)$", "муниципальный округ"),
        (r"\bмуниципального\s+района\s+(.+)$", "муниципальный район"),
    )
    for pattern, prefix in ordered_patterns:
        ordered = re.search(pattern, body, flags=re.IGNORECASE)
        if ordered:
            tail = _clean_municipality_tail(ordered.group(1))
            return f"{prefix} {tail}" if tail else prefix

    trailing_patterns = (
        (r"\b([А-ЯЁA-Z][А-ЯЁа-яёA-Za-z-]+)\s+муниципального\s+округа\b", "муниципальный округ"),
        (r"\b([А-ЯЁA-Z][А-ЯЁа-яёA-Za-z-]+)\s+муниципального\s+района\b", "муниципальный район"),
        (r"\b([А-ЯЁA-Z][А-ЯЁа-яёA-Za-z-]+)\s+городского\s+округа\b", "городской округ"),
    )
    for pattern, suffix in trailing_patterns:
        matches = list(re.finditer(pattern, body, flags=re.IGNORECASE))
        if not matches:
            continue
        adjective = _genitive_adjective_to_nominative(matches[-1].group(1))
        return f"{adjective} {suffix}".strip()

    return None


def _clean_municipality_tail(value: str | None) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip(" ,")
    text = re.sub(r"\s+(?:области|края|республики|автономного округа)$", "", text, flags=re.IGNORECASE)
    return text.strip(" ,")


def _genitive_adjective_to_nominative(value: str | None) -> str:
    word = str(value or "").strip()
    lower = word.lower().replace("ё", "е")
    replacements = (
        ("ского", "ский"),
        ("цкого", "цкий"),
        ("кого", "кий"),
        ("ого", "ый"),
        ("его", "ий"),
    )
    for old, new in replacements:
        if lower.endswith(old):
            return word[: -len(old)] + new
    return word


def _clean_catalog_name(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return ""
    return text.rstrip("/").strip()


def _is_catalog_group_heading(name: str) -> bool:
    text = name.lower().replace("ё", "е").strip()
    return text.startswith("населенные пункты") or text.startswith("городские поселения") or text.startswith(
        "сельские поселения"
    )


def _looks_like_local_settlement(name: str | None) -> bool:
    if not name:
        return False
    text = name.lower().replace("ё", "е")
    return any(
        marker in text
        for marker in (
            "сельсовет",
            "поссовет",
            "сельское поселение",
            "городское поселение",
            "рабочий поселок",
            "поселок городского типа",
            "городской поселок",
            "курортный поселок",
            "дачный поселок",
        )
    )


def _looks_like_primary_municipality(name: str | None) -> bool:
    if not name:
        return False
    text = name.lower().replace("ё", "е")
    return (
        "муниципальный район" in text
        or "муниципальный округ" in text
        or "городской округ" in text
        or text.startswith("город ")
    )


def _select_best_oktmo_row(rows: list[tuple[str, str, str]]) -> tuple[str, str, str]:
    """Prefer a concrete locality over its parent municipality for the same match key."""
    return max(rows, key=_oktmo_row_specificity)


def _oktmo_row_specificity(row: tuple[str, str, str]) -> tuple[int, int]:
    code, display_name, _ = row
    parent_penalty = 0 if _looks_like_parent_territory(display_name) else 1
    return (parent_penalty, len(str(code)))


def _looks_like_parent_territory(name: str | None) -> bool:
    if not name:
        return False
    text = name.lower().replace("ё", "е")
    return any(
        marker in text
        for marker in (
            "сельсовет",
            "поселение",
            "муниципаль",
            "городской округ",
            "муниципальный округ",
            "район",
            "рабочий поселок",
            "поселок городского типа",
            "городской поселок",
            "курортный поселок",
            "дачный поселок",
        )
    )


def _keys_for_subject_scope(subject_scope: OktmoSubjectScope | None) -> list[str]:
    if not _INDEX or not _INDEX_KEYS:
        return []
    if not subject_scope:
        return _INDEX_KEYS
    return [key for key in _INDEX_KEYS if any(_oktmo_row_in_subject_scope(row, subject_scope) for row in _INDEX.get(key, []))]


def _municipality_keys_for_subject_scope(subject_scope: OktmoSubjectScope | None) -> list[str]:
    if not _MUNICIPALITY_BY_LOCALITY_KEY:
        return []
    keys = list(_MUNICIPALITY_BY_LOCALITY_KEY.keys())
    if not subject_scope:
        return keys
    return [
        key
        for key in keys
        if any(_municipality_key_row_in_subject_scope(row, subject_scope) for row in _MUNICIPALITY_BY_LOCALITY_KEY.get(key, []))
    ]


def _select_best_municipality(rows: list[tuple[str, str, str]]) -> tuple[str, str, str]:
    return max(rows, key=lambda row: _municipality_specificity(row[0]))


def _prefer_oktmo_rows_for_municipality(
    rows: list[tuple[str, str, str]],
    municipality_hint: str | None,
) -> list[tuple[str, str, str]]:
    if not rows or not municipality_hint or not _MUNICIPALITY_BY_CODE:
        return rows
    preferred = [
        row
        for row in rows
        if _municipality_matches_hint(_MUNICIPALITY_BY_CODE.get(_digits_only(row[0])), municipality_hint)
    ]
    return preferred or rows


def _prefer_municipality_rows(
    rows: list[tuple[str, str, str]],
    municipality_hint: str | None,
) -> list[tuple[str, str, str]]:
    if not rows or not municipality_hint:
        return rows
    preferred = [row for row in rows if _municipality_matches_hint(row[0], municipality_hint)]
    return preferred or rows


def _municipality_matches_hint(value: str | None, hint: str | None) -> bool:
    value_key = _municipality_match_key(value)
    hint_key = _municipality_match_key(hint)
    if not value_key or not hint_key:
        return False
    return value_key == hint_key or value_key in hint_key or hint_key in value_key


def _municipality_match_key(value: str | None) -> str:
    text = str(value or "").lower().replace("ё", "е")
    text = re.sub(
        r"\b(муниципальн(?:ый|ого|ом|ая|ой|ое|ые|ых)?|городск(?:ой|ого|ом|ая|ой|ое|ие|их)?|"
        r"округ|округа|округе|район|района|районе|сельск(?:ий|ого|ом|ая|ой|ое|ие|их)?|"
        r"поселение|поселения|сельсовет|поссовет)\b",
        " ",
        text,
    )
    text = re.sub(r"[^а-яa-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _municipality_specificity(name: str) -> tuple[int, int]:
    text = name.lower().replace("ё", "е")
    if text.startswith("город "):
        tier = 6
    elif "муниципальный округ" in text or "городской округ" in text:
        tier = 5
    elif _looks_like_local_settlement(name):
        tier = 4
    elif "муниципальный район" in text:
        tier = 3
    else:
        tier = 4
    return tier, len(name)


def _infer_subject_ter(text: str | None) -> str | None:
    if not text:
        return None
    key = region_key(text)
    if key and _SUBJECT_TER_BY_REGION_KEY:
        direct = _SUBJECT_TER_BY_REGION_KEY.get(key)
        if direct:
            return direct
        try:
            from rapidfuzz import process as fz_process

            result = fz_process.extractOne(key, list(_SUBJECT_TER_BY_REGION_KEY), score_cutoff=86)
            if result:
                return _SUBJECT_TER_BY_REGION_KEY.get(result[0])
        except ImportError:
            pass
    normalized = text.lower().replace("ё", "е")
    for marker, ter in _SUBJECT_TER_HINTS.items():
        if marker in normalized:
            return ter
    if any(marker in normalized for marker in ("чугуевский", "чугуевка")):
        return "05"
    if any(marker in normalized for marker in ("усть-кут", "усть кут", "устькут", "киренск", "киренский")):
        return "25"
    return None


def _infer_subject_scope(
    data_dir: Path,
    text: str | None,
    scopes: list[OktmoSubjectScope] | None = None,
) -> OktmoSubjectScope | None:
    if not text:
        return None
    scopes = scopes if scopes is not None else _subject_scopes(data_dir)
    if not scopes:
        return None
    normalized = str(text).lower().replace("ё", "е")
    for marker, scope_value in _SUBJECT_SCOPE_HINTS.items():
        if marker in normalized:
            return _subject_scope_by_value(scopes, scope_value)

    key = region_key(text)
    if key:
        regions = {region.region_id: region for region in load_region_entries(data_dir)}
        scope_keys: dict[str, OktmoSubjectScope] = {}
        for scope in scopes:
            variants = [scope.name]
            region = regions.get(scope.region_id)
            if region:
                variants.extend([region.display_name, region.short_name, *region.aliases])
            for variant in variants:
                variant_key = region_key(variant)
                if variant_key:
                    scope_keys.setdefault(variant_key, scope)
        direct = scope_keys.get(key)
        if direct:
            return direct
        try:
            from rapidfuzz import process as fz_process

            result = fz_process.extractOne(key, list(scope_keys), score_cutoff=86)
            if result:
                return scope_keys.get(result[0])
        except ImportError:
            pass

    ter = _infer_subject_ter(text)
    return _subject_scope_by_value(scopes, ter)


def _valid_subject_ter(value: str | None) -> str | None:
    if value and re.fullmatch(r"\d{2}", str(value)):
        return str(value)
    return None


def _normalize_name(text: str) -> str:
    t = text.lower().replace("ё", "е")
    t = re.sub(r"\bж\s*[./-]?\s*-?\s*д\.?\s*(?:ст|рзд|станция|разъезд)\.?", " ", t)
    t = re.sub(r"\bп\.?\s*(?:/|\.)?\s*ст\.?", " ", t)
    t = re.sub(r"\b(?:г\.?\s*п\.?|р\.?\s*п\.?|к\.?\s*п\.?|д\.?\s*п\.?|н\.?\s*п\.?|п\.?\s*г\.?\s*т\.?)\b", " ", t)
    t = re.sub(
        r"\b(?:рабочий|городской|курортный|дачный)\s+пос[её]лок\b|"
        r"\bпос[её]лок\s+городского\s+типа\b|"
        r"\bпос[её]лок\s+(?:при\s+)?станции\b|"
        r"\bнасел[её]нный\s+пункт\b",
        " ",
        t,
    )
    t = re.sub(
        r"\b(гп|дп|кп|г|гор|город|р-н|район|обл|область|кр|край|мо|мун|округ|ао|"
        r"мкр|пгт|рп|пос|поселок|с|село|д|деревня|ст-ца|ст|станица|х|хутор|рзд|"
        r"разъезд|аул|аал|арбан|улус|у|нп|н|п|м|местечко|кишлак|к|ул|пр-т|пр-кт|пр-д)\b\.?",
        " ",
        t,
    )
    t = re.sub(r"[^а-яa-z0-9]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _digits_only(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\D+", "", value)


def _linear_best(query: str, keys: list[str]) -> tuple[str, int, int] | None:
    if not keys:
        return None
    best_score = 0
    best_key = None
    for key in keys:
        score = _simple_similarity(query, key)
        if score > best_score:
            best_score = score
            best_key = key
    if best_score < _FUZZY_THRESHOLD or best_key is None:
        return None
    return (best_key, best_score, 0)


def _simple_similarity(a: str, b: str) -> int:
    words_a = set(a.split())
    words_b = set(b.split())
    if not words_a or not words_b:
        return 0
    intersection = words_a & words_b
    union = words_a | words_b
    return int(100 * len(intersection) / len(union))
