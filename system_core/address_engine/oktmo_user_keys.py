from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from .oktmo_lookup import (
    oktmo_key_terms_for_code,
    oktmo_scope_key_profile,
    region_scope_options,
    resolve_municipality_scope_hint,
    resolve_region_scope_id,
    resolve_region_scope_ter,
    settlement_scope_candidates,
)
from .russian_morphology import phrase_case_forms, phrase_lemmas


CURRENT_KEYS_NAME = "oktmo_current_keys.txt"
REGION_PINS_NAME = "oktmo_region_pins.json"
MUNICIPALITY_PINS_NAME = "oktmo_municipality_pins.json"
PINS_BUNDLE_NAME = "oktmo_pins_bundle.json"


def clean_key(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\xa0", " ")).strip(" ,;\t\r\n")


def normalize_key(value: Any) -> str:
    text = clean_key(value).lower().replace("ё", "е")
    text = re.sub(r"[^0-9a-zа-я]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def unique_keys(values: Iterable[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = clean_key(value)
        key = normalize_key(text)
        if not text or not key or key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def split_keys(value: Any) -> list[str]:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    return unique_keys(re.split(r"[\n;]+", text))


def project_root_from_data_dir(data_dir: Path | str | None) -> Path:
    path = Path(data_dir or Path.cwd()).resolve()
    if path.name.lower() == "rosstat":
        path = path.parent
    if path.name.lower() == "data":
        return path.parent
    return path


def config_dir(project_root: Path | str) -> Path:
    return Path(project_root).resolve() / "config"


def current_keys_path(project_root: Path | str) -> Path:
    return config_dir(project_root) / CURRENT_KEYS_NAME


def region_pins_path(project_root: Path | str) -> Path:
    return config_dir(project_root) / REGION_PINS_NAME


def municipality_pins_path(project_root: Path | str) -> Path:
    return config_dir(project_root) / MUNICIPALITY_PINS_NAME


def pins_bundle_path(project_root: Path | str) -> Path:
    return config_dir(project_root) / PINS_BUNDLE_NAME


def load_current_keys(project_root: Path | str) -> list[str]:
    path = current_keys_path(project_root)
    if not path.exists():
        return []
    return split_keys(path.read_text(encoding="utf-8"))


def write_current_keys(project_root: Path | str, keys: Iterable[Any]) -> dict[str, Any]:
    normalized = unique_keys(keys)
    path = current_keys_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(normalized) + ("\n" if normalized else ""), encoding="utf-8")
    return {"path": str(path), "keys": len(normalized)}


def add_current_keys(project_root: Path | str, keys: Iterable[Any]) -> dict[str, Any]:
    return write_current_keys(project_root, [*load_current_keys(project_root), *list(keys)])


def clear_current_keys(project_root: Path | str) -> dict[str, Any]:
    return write_current_keys(project_root, [])


def _forms(value: Any) -> list[str]:
    text = clean_key(value)
    if not text:
        return []
    return unique_keys([text, *phrase_case_forms(text), *phrase_lemmas(text)])


def _region_label(data_dir: Path, region_value: str) -> str:
    text = clean_key(region_value)
    scope_id = resolve_region_scope_id(data_dir, text)
    ter = resolve_region_scope_ter(data_dir, text)
    for option in region_scope_options(data_dir):
        option_values = {
            clean_key(option.get("value")),
            clean_key(option.get("label")),
            clean_key(option.get("label_ru")),
            clean_key(option.get("code")),
        }
        if text in option_values or (scope_id and clean_key(option.get("value")) == scope_id) or (ter and clean_key(option.get("ter")) == ter and not scope_id):
            return clean_key(option.get("label_ru") or option.get("label") or option.get("value"))
    return text


def region_key_terms(data_dir: Path | str, region_value: str) -> list[str]:
    data_path = Path(data_dir).resolve()
    label = _region_label(data_path, region_value)
    if not label:
        raise ValueError("Выберите регион ОКТМО перед добавлением ключей.")
    return _forms(label)


def municipality_key_terms(data_dir: Path | str, region_value: str, municipality_value: str) -> list[str]:
    data_path = Path(data_dir).resolve()
    municipality = resolve_municipality_scope_hint(data_path, municipality_value)
    if not municipality:
        raise ValueError("Выберите муниципалитет ОКТМО перед добавлением ключей.")
    subject_scope = resolve_region_scope_id(data_path, region_value) or resolve_region_scope_ter(data_path, region_value)
    profile = oktmo_scope_key_profile(
        data_path,
        subject_ter_hint=subject_scope,
        municipality_hint=municipality,
    )
    return unique_keys([municipality, *profile.get("extra_keys", [])])


def settlement_candidate_options(
    data_dir: Path | str,
    values: dict[str, Any] | None = None,
    *,
    limit: int = 40,
) -> list[dict[str, Any]]:
    values = values or {}
    data_path = Path(data_dir).resolve()
    region = clean_key(values.get("oktmo_scope_region") or values.get("subject_ter_hint"))
    municipality = clean_key(values.get("oktmo_scope_municipality") or values.get("municipality_hint"))
    query = clean_key(values.get("oktmo_settlement_query") or values.get("settlement") or values.get("locality"))
    subject_scope = resolve_region_scope_id(data_path, region) or resolve_region_scope_ter(data_path, region) or region
    municipality_hint = resolve_municipality_scope_hint(data_path, municipality) or municipality
    return settlement_scope_candidates(
        data_path,
        query,
        subject_ter_hint=subject_scope,
        municipality_hint=municipality_hint,
        limit=limit,
    )


def candidate_options_from_values(values: dict[str, Any] | None = None) -> list[dict[str, str]]:
    values = values or {}
    raw = values.get("oktmo_candidate_options")
    if not isinstance(raw, list):
        return []
    options: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        value = clean_key(item.get("value") or item.get("code"))
        label = clean_key(item.get("label_ru") or item.get("label") or value)
        if value and label:
            options.append({"value": value, "label": label, "label_ru": label})
    return options


def candidate_key_terms(data_dir: Path | str, candidate_code: str) -> dict[str, Any]:
    data_path = Path(data_dir).resolve()
    code = clean_key(candidate_code)
    if not code:
        raise ValueError("Выберите найденный населённый пункт ОКТМО перед добавлением ключей.")
    result = oktmo_key_terms_for_code(data_path, code)
    result["terms"] = unique_keys(result.get("terms", []))
    return result


def _load_pin_data(path: Path, list_key: str) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "items": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "items": []}
    if not isinstance(data, dict):
        return {"version": 1, "items": []}
    items = data.get("items", data.get(list_key, []))
    if not isinstance(items, list):
        items = []
    return {"version": 1, "items": [item for item in items if isinstance(item, dict)]}


def _write_pin_data(path: Path, items: list[dict[str, Any]], list_key: str) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"version": 1, "updated_at": _now(), list_key: items, "items": items}
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return {"path": str(path), "items": len(items)}


def _pin_identity(item: dict[str, Any], kind: str) -> tuple[str, str]:
    keys = sorted(_pin_compare_keys(item))
    primary = keys[0] if keys else ""
    scope = _pin_scope_key(item) if kind != "region" else ""
    return scope, primary


def _merge_pin_items(existing: list[dict[str, Any]], incoming: Iterable[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in [*incoming, *existing]:
        if not isinstance(item, dict):
            continue
        identity = _pin_identity(item, kind)
        if not identity[1] or identity in seen:
            continue
        seen.add(identity)
        result.append(dict(item))
    return result


def load_pins(project_root: Path | str, kind: str) -> list[dict[str, Any]]:
    if kind == "region":
        return _load_pin_data(region_pins_path(project_root), "regions")["items"]
    return _load_pin_data(municipality_pins_path(project_root), "municipalities")["items"]


def _pin_compare_keys(item: dict[str, Any]) -> set[str]:
    return {
        key
        for key in (
            normalize_key(item.get("value")),
            normalize_key(item.get("label")),
            normalize_key(item.get("label_ru")),
            normalize_key(item.get("code")),
        )
        if key
    }


def _pin_scope_key(item: dict[str, Any]) -> str:
    return normalize_key(item.get("scope") or item.get("subject_ter") or item.get("region") or item.get("region_code"))


def _pin_scope_matches(item: dict[str, Any], scope: str = "") -> bool:
    expected = normalize_key(scope)
    if not expected:
        return True
    item_scope = _pin_scope_key(item)
    return not item_scope or item_scope == expected


def is_pinned(project_root: Path | str, kind: str, value: str, *, scope: str = "") -> bool:
    key = normalize_key(value)
    return bool(
        key
        and any(
            _pin_scope_matches(item, scope) and key in _pin_compare_keys(item)
            for item in load_pins(project_root, kind)
        )
    )


def pin_value(project_root: Path | str, kind: str, value: str, label: str = "", code: str = "", scope: str = "") -> dict[str, Any]:
    text = clean_key(value)
    if not text:
        raise ValueError("Выберите значение перед закреплением.")
    item = {
        "value": text,
        "label": clean_key(label) or text,
        "label_ru": clean_key(label) or text,
        "code": clean_key(code),
        "pinned_at": _now(),
    }
    if kind != "region" and clean_key(scope):
        item["scope"] = clean_key(scope)
    text_key = normalize_key(text)
    scope_key = normalize_key(scope)
    items = [
        row
        for row in load_pins(project_root, kind)
        if not (
            text_key in _pin_compare_keys(row)
            and (kind == "region" or not scope_key or _pin_scope_matches(row, scope))
        )
    ]
    items.insert(0, item)
    path = region_pins_path(project_root) if kind == "region" else municipality_pins_path(project_root)
    return _write_pin_data(path, items, "regions" if kind == "region" else "municipalities")


def unpin_value(project_root: Path | str, kind: str, value: str, scope: str = "") -> dict[str, Any]:
    key = normalize_key(value)
    items = [
        row
        for row in load_pins(project_root, kind)
        if not (
            key in _pin_compare_keys(row)
            and (kind == "region" or not scope or _pin_scope_matches(row, scope))
        )
    ]
    path = region_pins_path(project_root) if kind == "region" else municipality_pins_path(project_root)
    return _write_pin_data(path, items, "regions" if kind == "region" else "municipalities")


def decorate_pinned_options(project_root: Path | str, kind: str, options: list[dict[str, object]], *, scope: str = "") -> list[dict[str, object]]:
    pins = load_pins(project_root, kind)
    result: list[dict[str, object]] = []
    seen: set[str] = set()
    by_key: dict[str, dict[str, object]] = {}
    for option in options:
        if not isinstance(option, dict):
            continue
        for key in _pin_compare_keys(option):
            by_key.setdefault(key, dict(option))
    for pin in pins:
        pin_keys = _pin_compare_keys(pin)
        option = next((by_key[item_key] for item_key in pin_keys if item_key in by_key), dict(pin))
        option_keys = _pin_compare_keys(option)
        key = normalize_key(option.get("value") or pin.get("value") or option.get("code") or pin.get("code"))
        if not key or key in seen or any(item_key in seen for item_key in option_keys):
            continue
        if kind != "region" and scope and not _pin_scope_matches(pin, scope) and not any(item_key in by_key for item_key in pin_keys):
            continue
        label = clean_key(option.get("label_ru") or option.get("label") or pin.get("label") or pin.get("value"))
        option["label"] = label
        option["label_ru"] = label
        option["pinned"] = "true"
        result.append(option)
        seen.update(_pin_compare_keys(option))
        seen.add(key)
    for option in options:
        option_keys = _pin_compare_keys(option)
        key = normalize_key(option.get("value") or option.get("label"))
        if (key and key in seen) or any(item_key in seen for item_key in option_keys):
            continue
        result.append(option)
        seen.update(option_keys)
        if key:
            seen.add(key)
    return result


def export_pins_bundle(project_root: Path | str, path: Path | str | None = None) -> dict[str, Any]:
    project = Path(project_root).resolve()
    bundle_path = Path(path).resolve() if path else pins_bundle_path(project)
    regions = load_pins(project, "region")
    municipalities = load_pins(project, "municipality")
    payload = {
        "schema_version": 1,
        "kind": "audion_address_processor_oktmo_pins",
        "updated_at": _now(),
        "regions": regions,
        "municipalities": municipalities,
        "files": {
            "regions": str(Path("config") / REGION_PINS_NAME),
            "municipalities": str(Path("config") / MUNICIPALITY_PINS_NAME),
        },
    }
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = bundle_path.with_suffix(bundle_path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(bundle_path)
    return {"path": str(bundle_path), "regions": len(regions), "municipalities": len(municipalities)}


def import_pins_bundle(project_root: Path | str, path: Path | str | None = None, *, merge: bool = True) -> dict[str, Any]:
    project = Path(project_root).resolve()
    bundle_path = Path(path).resolve() if path else pins_bundle_path(project)
    if not bundle_path.exists():
        return export_pins_bundle(project, bundle_path)
    try:
        payload = json.loads(bundle_path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise ValueError(f"Не удалось прочитать файл пинов ОКТМО: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Файл пинов ОКТМО должен быть JSON-объектом.")
    regions = payload.get("regions", payload.get("region_pins", []))
    municipalities = payload.get("municipalities", payload.get("municipality_pins", []))
    if not isinstance(regions, list):
        regions = []
    if not isinstance(municipalities, list):
        municipalities = []
    current_regions = load_pins(project, "region") if merge else []
    current_municipalities = load_pins(project, "municipality") if merge else []
    merged_regions = _merge_pin_items(current_regions, [item for item in regions if isinstance(item, dict)], "region")
    merged_municipalities = _merge_pin_items(
        current_municipalities,
        [item for item in municipalities if isinstance(item, dict)],
        "municipality",
    )
    _write_pin_data(region_pins_path(project), merged_regions, "regions")
    _write_pin_data(municipality_pins_path(project), merged_municipalities, "municipalities")
    return {"path": str(bundle_path), "regions": len(merged_regions), "municipalities": len(merged_municipalities)}


def clear_all_pins(project_root: Path | str) -> dict[str, Any]:
    project = Path(project_root).resolve()
    _write_pin_data(region_pins_path(project), [], "regions")
    _write_pin_data(municipality_pins_path(project), [], "municipalities")
    return export_pins_bundle(project)


def pin_file_status(project_root: Path | str) -> dict[str, Any]:
    project = Path(project_root).resolve()
    return {
        "path": str(pins_bundle_path(project)),
        "regions": len(load_pins(project, "region")),
        "municipalities": len(load_pins(project, "municipality")),
    }


def merge_current_keys_into_profile(profile: dict[str, Any], data_dir: Path | str | None) -> dict[str, Any]:
    project_root = project_root_from_data_dir(Path(data_dir) if data_dir else None)
    keys = load_current_keys(project_root)
    if not keys:
        return profile
    result = dict(profile or {})
    weighted = list(result.get("weighted_extra_keys") or [])
    existing = {normalize_key(item.get("value")) for item in weighted if isinstance(item, dict)}
    for key in keys:
        normalized = normalize_key(key)
        if not normalized or normalized in existing:
            continue
        existing.add(normalized)
        weighted.append(
            {
                "value": key,
                "weight": 35.0,
                "source": "user_key_file",
                "role": "manual",
                "context_required": True,
                "code": "",
            }
        )
    result["weighted_extra_keys"] = weighted
    result["extra_keys"] = unique_keys([*result.get("extra_keys", []), *keys])
    counts = dict(result.get("counts") or {})
    counts["user_key_file"] = len(keys)
    counts["context_required"] = sum(1 for item in weighted if isinstance(item, dict) and item.get("context_required"))
    result["counts"] = counts
    result["user_key_file"] = {"path": str(current_keys_path(project_root)), "keys": len(keys)}
    return result
