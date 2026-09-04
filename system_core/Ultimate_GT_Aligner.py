import pandas as pd
import re
import time
import sys
import json
from pathlib import Path
from rapidfuzz import process, fuzz
from tqdm import tqdm
from collections import defaultdict

try:
    from system_core.address_engine import AddressNormalizer as _AddressNormalizer
    from system_core.address_engine.audion_address_core import parse_address_components as _core_parse_address_components
    from system_core.address_engine.normalizer_runtime import normalizer_oktmo_key_profile as _normalizer_oktmo_key_profile
    from system_core.address_engine.source_table_assembly import collect_address_match_candidates_from_file as _collect_address_match_candidates_from_file
except Exception:  # pragma: no cover - direct script execution fallback
    from address_engine import AddressNormalizer as _AddressNormalizer
    from address_engine.audion_address_core import parse_address_components as _core_parse_address_components
    from address_engine.normalizer_runtime import normalizer_oktmo_key_profile as _normalizer_oktmo_key_profile
    from address_engine.source_table_assembly import collect_address_match_candidates_from_file as _collect_address_match_candidates_from_file

tqdm.pandas()

ROOT = Path(__file__).resolve().parents[1]
PROJECT_CONFIG_PATH = ROOT / "config" / "project.yaml"


def _load_yaml_or_json(path):
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return json.loads(text)
    try:
        import yaml  # type: ignore
    except Exception as exc:
        raise RuntimeError(f"PyYAML is required to read {path.name}. Install package: pyyaml") from exc
    data = yaml.safe_load(text) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config file must contain a mapping: {path}")
    return data


def _aligner_config():
    config = _load_yaml_or_json(PROJECT_CONFIG_PATH)
    section = config.get("address_aligner", {})
    return section if isinstance(section, dict) else {}


CONFIG = _aligner_config()

# ============================================================
# Ultimate GT Aligner v5
# ============================================================
# Stages 1-4: Precision (strict street + house + mods)
# Stage 5:    Best-effort relaxed (street + house_base only,
#             ignore mods, fill ONLY empty cells)
# ============================================================

MAX_ALIGN_COLUMNS = int(CONFIG.get("max_auto_align_columns", 5) or 5)
COLLECTED_DOCUMENT_COLUMN = "__Collected_Address__"

# ┌──────────────────────────────────────────────────────────┐
# │  НАСТРОЙКА: название города для удаления из адресов.     │
# │  Менять при работе с другим городом.                     │
# └──────────────────────────────────────────────────────────┘
CITY_NAME = str(CONFIG.get("city", "тюмень") or "")

STREET_TYPE_PATTERN = (
    r'улица|ул\.?|переулок|пер\.?|проспект|пр-т\.?|просп\.?|'
    r'бульвар|б-р\.?|бульв\.?|тракт|шоссе|ш\.?|тупик|туп\.?|'
    r'проезд|пр-д\.?|аллея|линия|набережная|наб\.?|площадь|пл\.?|'
    r'квартал|кв-л\.?|микрорайон|мкр\.?|км\.?|автодорог\w*'
)
TERRITORY_TYPE_PATTERN = r'тер\.?|территория|снт|сосн|днт|тсн'
RAILWAY_ABBR_PATTERN = r'ж\s*[./-]?\s*-?\s*д\.?'
STANITSA_ABBR_PATTERN = r'ст\s*[\.-]?\s*ца\.?'
P_STATION_ABBR_PATTERN = r'п\.?\s*(?:/|\.)?\s*ст\.?'
RZD_ABBR_PATTERN = r'р\.?\s*зд\.?'
SETTLEMENT_COMPACT_PATTERN = (
    r'г\.?\s*п\.?|р\.?\s*п\.?|к\.?\s*п\.?|д\.?\s*п\.?|'
    r'п\.?\s*г\.?\s*т\.?|н\.?\s*п\.?'
)
SETTLEMENT_TYPE_PATTERN = (
    rf'п\s+{RAILWAY_ABBR_PATTERN}\s+ст\.?|п\s+{RAILWAY_ABBR_PATTERN}\s+{RZD_ABBR_PATTERN}|'
    rf'{RAILWAY_ABBR_PATTERN}\s+остановочн\w*\s+пункт|{RAILWAY_ABBR_PATTERN}\s+блокпост|'
    rf'{RAILWAY_ABBR_PATTERN}\s+будка|{RAILWAY_ABBR_PATTERN}\s+ветка|{RAILWAY_ABBR_PATTERN}\s+казарма|'
    rf'{RAILWAY_ABBR_PATTERN}\s+платформа|{RAILWAY_ABBR_PATTERN}\s+площадка|'
    rf'{RAILWAY_ABBR_PATTERN}\s+путевой\s+пост|{RAILWAY_ABBR_PATTERN}\s+{RZD_ABBR_PATTERN}|'
    rf'{RAILWAY_ABBR_PATTERN}\s+ст\.?|'
    rf'{P_STATION_ABBR_PATTERN}|п\s+станци[ия]|пос[её]лок\s+при\s+станции|пос[её]лок\s+станции|'
    r'городской\s+пос[её]лок|рабочий\s+пос[её]лок|курортный\s+пос[её]лок|'
    r'дачный\s+пос[её]лок|пос[её]лок\s+городского\s+типа|насел[её]нный\s+пункт|'
    rf'{SETTLEMENT_COMPACT_PATTERN}|{RZD_ABBR_PATTERN}|разъезд|'
    r'город|г\.?|пос[её]лок|пос\.?|п\.?|деревня|д\.?|село|с\.?|'
    rf'слобода|сл\.?|станица|{STANITSA_ABBR_PATTERN}|станция|ст\.?|хутор|х\.?|'
    r'улус|у\.?|местечко|м\.?|кишлак|к\.?|'
    r'аул|аал|арбан|починок|выселок|выселки|заимка|кордон|маяк|'
    r'погост|слободка|усадьба|лесоучасток|метеостанция'
)
STREET_OR_TERRITORY_RE = re.compile(
    rf'\b(?:{STREET_TYPE_PATTERN}|{TERRITORY_TYPE_PATTERN})\b',
    re.IGNORECASE,
)
SETTLEMENT_SEGMENT_RE = re.compile(
    rf'^\s*(?:{SETTLEMENT_TYPE_PATTERN})\s+(?P<name>[^,]+?)\s*$',
    re.IGNORECASE,
)
SETTLEMENT_LEADING_RE = re.compile(
    rf'^\s*(?:{SETTLEMENT_TYPE_PATTERN})\s+'
    rf'(?P<name>.+?)'
    rf'(?=\s+(?:{STREET_TYPE_PATTERN}|{TERRITORY_TYPE_PATTERN})\b|,|$)',
    re.IGNORECASE,
)
SETTLEMENT_ADMIN_RE = re.compile(
    rf'\b(?:'
    rf'городской\s+пос[её]лок|рабочий\s+пос[её]лок|курортный\s+пос[её]лок|'
    rf'дачный\s+пос[её]лок|пос[её]лок\s+городского\s+типа|насел[её]нный\s+пункт|'
    rf'пос[её]лок|деревня|село|слобода|станица|станция|хутор|улус|местечко|кишлак|'
    rf'{SETTLEMENT_COMPACT_PATTERN}|{RZD_ABBR_PATTERN}|{STANITSA_ABBR_PATTERN}'
    rf')\b',
    re.IGNORECASE,
)

ADDRESS_MARKER_RE = re.compile(
    rf'(?:{STREET_TYPE_PATTERN}|{TERRITORY_TYPE_PATTERN}|{SETTLEMENT_TYPE_PATTERN}|д\.|дом|'
    r'обл|область|район|р-н|'
    r'площадь|пл\.|набережная|наб\.|корп\.|корпус)',
    re.IGNORECASE,
)
OBJECT_WORD_RE = re.compile(
    r'(?:школа|сош|лицей|гимназия|детск\w*\s+сад|садик|больниц\w*|'
    r'поликлиник\w*|гбуз|гауз|маоу|мбоу|мдоу|мку|учрежден\w*|'
    r'hospital|school|clinic|kindergarten)',
    re.IGNORECASE,
)
HOUSE_TAIL_RE = re.compile(
    r'(?P<base>\d+)(?P<tail>\s*(?:'
    r'[а-яa-z](?!\d)|'
    r'[/\-]\s*\d+[а-яa-z]?|'
    r'(?:к\.?|корп\.?|корпус)\s*\d+[а-яa-z]?|'
    r'(?:с\.?|стр\.?|строение)\s*\d+[а-яa-z]?|'
    r'(?:лит\.?а?|литера)\s*[а-яa-z]'
    r')*)\s*$',
    re.IGNORECASE,
)


def _normalize_house_mods(tail):
    text = str(tail or '').lower().replace('ё', 'е')
    text = re.sub(r'(?:корпус|корп\.?|к\.)\s*', 'к', text)
    text = re.sub(r'(?:строение|стр\.?|с\.)\s*', 'с', text)
    text = re.sub(r'(?:лит\.?а?|литера)\s*', 'лит', text)
    text = re.sub(r'[\s,;]+', '', text)

    mods = ''
    while text:
        if text[0] in '/-':
            m = re.match(r'[/\-](\d+[а-яa-z]?)', text)
            if not m:
                break
            mods += 'к' + m.group(1)
            text = text[m.end():]
            continue
        if text.startswith('лит'):
            m = re.match(r'лит([а-яa-z])', text)
            if not m:
                break
            mods += m.group(1)
            text = text[m.end():]
            continue
        m = re.match(r'к(\d+[а-яa-z]?)', text)
        if m:
            mods += 'к' + m.group(1)
            text = text[m.end():]
            continue
        m = re.match(r'с(\d+[а-яa-z]?)', text)
        if m:
            mods += 'с' + m.group(1)
            text = text[m.end():]
            continue
        m = re.match(r'([а-яa-z])', text)
        if m:
            mods += m.group(1)
            text = text[m.end():]
            continue
        break
    return mods


def _find_trailing_house(text):
    match = HOUSE_TAIL_RE.search(text)
    if not match:
        return None
    prefix = text[:match.start()]
    if not re.search(r'[а-яa-z]', prefix):
        return None
    previous = text[match.start() - 1] if match.start() > 0 else ''
    if previous and not (previous.isspace() or previous in ',.;:' or re.match(r'[а-яa-z]', previous, re.IGNORECASE)):
        return None
    return match.start(), match.group('base'), _normalize_house_mods(match.group('tail'))


def _extract_mods(after):
    """Извлекает модификаторы дома из хвоста. /N → кN."""
    tail = str(after).strip()
    if OBJECT_WORD_RE.match(tail):
        return ''
    return _normalize_house_mods(after)


def _strip_object_noise(text):
    text = re.sub(r'\b(?:школа|сош|лицей|гимназия|детск\w*\s+сад|садик)\s*(?:№|#)?\s*\d+[а-яa-z]?\b', ' ', text)
    text = re.sub(r'\b(?:маоу|мбоу|мдоу|мку|гбуз|гауз|ано|аоу|сош|доу|оош)\b', ' ', text)
    text = re.sub(r'\b(?:школа|лицей|гимназия|больниц\w*|поликлиник\w*|учрежден\w*)\b', ' ', text)
    text = re.sub(r'\b(?:hospital|school|clinic|kindergarten)\b', ' ', text)
    text = re.sub(r'(?:№|#)\s*\d+[а-яa-z]?', ' ', text)
    text = re.sub(r'\b(?:имени|им\.?|филиал|отделение|корпус)\b', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def _normalize_named_words(value):
    text = str(value or '').lower().replace('ё', 'е')
    text = re.sub(r'[\"\'«»\u201c\u201d\u2018\u2019]', '', text)
    text = re.sub(r'[^\w\s]', ' ', text)
    words = [word for word in text.split() if len(word) > 1 or word.isdigit()]
    return ' '.join(sorted(words))


def _settlement_territory_from_name(name):
    territory = _normalize_named_words(name)
    if not territory:
        return ''
    if CITY_NAME and territory == _normalize_named_words(CITY_NAME):
        return ''
    return territory


def _settlement_territory_from_segment(segment):
    match = SETTLEMENT_SEGMENT_RE.match(str(segment or '').strip())
    if not match:
        return ''
    return _settlement_territory_from_name(match.group('name'))


def _strip_leading_settlement_prefix(text):
    value = str(text or '').strip()
    match = SETTLEMENT_LEADING_RE.match(value)
    if not match:
        return '', value
    territory = _settlement_territory_from_name(match.group('name'))
    rest = value[match.end():].lstrip(' ,')
    return territory, rest or value


def _merge_territory_parts(*parts):
    words = []
    seen = set()
    for part in parts:
        for word in str(part or '').split():
            if word and word not in seen:
                seen.add(word)
                words.append(word)
    return ' '.join(sorted(words))


def parse_address(address):
    if pd.isna(address):
        return ('', '', frozenset(), '', '')
    territory, street_words, street_numbers, house_base, house_mods = _core_parse_address_components(address)
    if CITY_NAME and territory == _normalize_named_words(CITY_NAME):
        territory = ''
    return (territory, street_words, street_numbers, house_base, house_mods)


def _bool_config(value, default=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if not text:
        return default
    return text in {"1", "true", "yes", "on", "да"}


def _aligner_data_dir(value):
    text = str(value or "").strip().strip('"')
    if not text:
        return None
    path = Path(text).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    if path.name.lower() == "rosstat":
        return path.parent
    return path


def _address_normalizer_from_config(aligner_config=None):
    effective_config = dict(CONFIG)
    if aligner_config is not None:
        effective_config.update(aligner_config)
    return _AddressNormalizer(
        city_name=str(effective_config.get("city") or CITY_NAME or "").strip(),
        data_dir=_aligner_data_dir(effective_config.get("oktmo_data_dir")),
        use_oktmo=_bool_config(effective_config.get("use_oktmo"), True),
        subject_ter_hint=str(effective_config.get("subject_ter_hint") or "").strip() or None,
        municipality_hint=str(effective_config.get("municipality_hint") or "").strip() or None,
    )


def _normalizer_from_config(aligner_config=None):
    effective_config = dict(CONFIG)
    if aligner_config is not None:
        effective_config.update(aligner_config)
    if not (
        _bool_config(effective_config.get("normalize_before_match"), False)
        or _bool_config(effective_config.get("collect_before_match"), False)
    ):
        return None
    return _address_normalizer_from_config(effective_config)


def _post_match_normalizer_from_config(aligner_config=None):
    effective_config = dict(CONFIG)
    if aligner_config is not None:
        effective_config.update(aligner_config)
    if not _bool_config(effective_config.get("normalize_after_match"), False):
        return None
    return _address_normalizer_from_config(effective_config)


def _normalizer_scope_profile(normalizer):
    if normalizer is None:
        return {}
    try:
        return _normalizer_oktmo_key_profile(normalizer)
    except Exception as exc:
        print(f"[WARN] Could not build OKTMO scope key profile: {exc}")
        return {}


def _scope_profile_enabled(profile):
    return bool((profile or {}).get("weighted_extra_keys"))


def _record_for_match(value, normalizer=None):
    if normalizer is None or pd.isna(value):
        return None
    return normalizer.normalize(value)


def _parse_address_for_match(value, normalizer=None):
    if pd.isna(value):
        return ('', '', frozenset(), '', '')
    if normalizer is not None:
        record = _record_for_match(value, normalizer)
        return record.strict_key if record is not None else ('', '', frozenset(), '', '')
    return parse_address(value)


def _string_key_for_match(value, normalizer=None):
    if pd.isna(value):
        return ""
    if normalizer is not None:
        record = _record_for_match(value, normalizer)
        value = (record.normalized or record.raw or "") if record is not None else ""
    text = str(value).strip().lower().replace('ё', 'е').replace('\xa0', ' ')
    return re.sub(r'[\"\'«»\u201c\u201d\u2018\u2019]', '', text)


def _scope_digits(value):
    return re.sub(r"\D+", "", str(value or ""))


def _scope_norm(value):
    text = str(value or "").lower().replace("ё", "е")
    text = re.sub(r"[^0-9a-zа-я]+", " ", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()


def _record_slot(record, name):
    if record is None:
        return None
    parts = getattr(record, "parts", None)
    return getattr(parts, name, None) if parts is not None else None


def _alignment_scope_search_text(value, record):
    values = [
        value,
        getattr(record, "raw", None),
        getattr(record, "normalized", None),
        getattr(record, "municipality", None),
        getattr(record, "oktmo_name", None),
        getattr(record, "subject", None),
        getattr(record, "parent_subject", None),
        _record_slot(record, "municipality"),
        _record_slot(record, "locality"),
        _record_slot(record, "territory"),
        _record_slot(record, "microdistrict"),
        _record_slot(record, "street"),
        _record_slot(record, "house"),
    ]
    return _scope_norm(" | ".join(str(item or "") for item in values if str(item or "").strip()))


def _alignment_scope_term_matches(normalized_text, term):
    key = _scope_norm(term)
    if not key:
        return False
    return re.search(rf"(?<![0-9a-zа-я]){re.escape(key)}(?![0-9a-zа-я])", normalized_text) is not None


def _alignment_scope_has_context(value, record):
    if record is not None and getattr(record, "house_base", ""):
        return True
    if _record_slot(record, "street") or _record_slot(record, "house") or _record_slot(record, "territory") or _record_slot(record, "microdistrict"):
        return True
    text = " | ".join(
        str(item or "")
        for item in (
            value,
            getattr(record, "raw", None),
            getattr(record, "normalized", None),
        )
        if str(item or "").strip()
    )
    return bool(ADDRESS_MARKER_RE.search(text) or OBJECT_WORD_RE.search(text))


def _alignment_scope_match(value, record, key_profile):
    weighted_keys = list((key_profile or {}).get("weighted_extra_keys") or [])
    if not weighted_keys:
        return {}
    searchable = _alignment_scope_search_text(value, record)
    if not searchable:
        return {}
    has_context = _alignment_scope_has_context(value, record)
    record_code = _scope_digits(getattr(record, "oktmo_code", ""))
    matches = []
    seen = set()
    for item in weighted_keys:
        if str(item.get("source") or "") == "subject":
            continue
        weight = float(item.get("weight") or 0.0)
        if weight <= 0:
            continue
        value_text = str(item.get("value") or "").strip()
        code = _scope_digits(item.get("code"))
        matched_by_code = bool(code and record_code and code == record_code)
        if not matched_by_code and not _alignment_scope_term_matches(searchable, value_text):
            continue
        context_required = bool(item.get("context_required"))
        valid = matched_by_code or not context_required or has_context
        key = (_scope_norm(value_text), str(item.get("role") or ""), code)
        if key in seen:
            continue
        seen.add(key)
        matches.append(
            {
                "value": value_text,
                "weight": weight,
                "role": str(item.get("role") or ""),
                "source": str(item.get("source") or ""),
                "context_required": context_required,
                "valid": valid,
                "code": code,
                "matched_by_code": matched_by_code,
            }
        )
    if not matches:
        return {}
    valid_matches = [item for item in matches if item["valid"]]
    ranked = sorted(valid_matches or matches, key=lambda item: (float(item["weight"]), len(str(item["value"]))), reverse=True)
    return {
        "valid": bool(valid_matches),
        "has_context": has_context,
        "best": ranked[0],
        "matches": matches,
    }


def _scope_codes_compatible(left, right):
    left_digits = _scope_digits(left)
    right_digits = _scope_digits(right)
    if not left_digits or not right_digits:
        return True
    return left_digits == right_digits or left_digits.startswith(right_digits) or right_digits.startswith(left_digits)


def _alignment_scope_pair_blocked(gt_record, target_record):
    gt_code = _scope_digits(getattr(gt_record, "oktmo_code", ""))
    target_code = _scope_digits(getattr(target_record, "oktmo_code", ""))
    return bool(gt_code and target_code and not _scope_codes_compatible(gt_code, target_code))


def _alignment_scope_pair_score(gt_scope, target_scope, gt_record=None, target_record=None):
    if _alignment_scope_pair_blocked(gt_record, target_record):
        return -80.0
    gt_code = _scope_digits(getattr(gt_record, "oktmo_code", ""))
    target_code = _scope_digits(getattr(target_record, "oktmo_code", ""))
    if gt_code and target_code and _scope_codes_compatible(gt_code, target_code):
        return 14.0
    if not gt_scope or not target_scope:
        return 0.0
    gt_matches = [item for item in gt_scope.get("matches", []) if item.get("valid")]
    target_matches = [item for item in target_scope.get("matches", []) if item.get("valid")]
    if not gt_matches or not target_matches:
        return 0.0
    best = 0.0
    for left in gt_matches:
        for right in target_matches:
            left_code = _scope_digits(left.get("code"))
            right_code = _scope_digits(right.get("code"))
            if left_code and right_code and not _scope_codes_compatible(left_code, right_code):
                best = max(best, 0.0)
                continue
            if left_code and right_code:
                best = max(best, min(float(left.get("weight") or 0.0), float(right.get("weight") or 0.0)) / 6.0)
                continue
            if _scope_norm(left.get("value")) == _scope_norm(right.get("value")):
                best = max(best, min(float(left.get("weight") or 0.0), float(right.get("weight") or 0.0)) / 10.0)
            elif left.get("role") == right.get("role") == "medium":
                best = max(best, 4.5)
    return min(best, 16.0)


def _has_address(value):
    return _looks_like_address_value(value)


def _looks_like_address_value(value):
    if pd.isna(value):
        return False
    text = str(value).strip()
    if not text:
        return False
    if not re.search(r"\d", text) and re.fullmatch(r"[A-Za-zА-Яа-яЁё\s_-]{1,80}", text):
        return False

    ter, sw, sn, hb, hm = parse_address(text)
    has_marker = bool(ADDRESS_MARKER_RE.search(text))
    has_object_word = bool(OBJECT_WORD_RE.search(text))

    if has_marker and (sw or hb):
        return True
    if sw and hb:
        return True
    return False


def _read_excel_rows(input_file):
    df = pd.read_excel(input_file, header=None)
    if df.empty:
        return df, None

    first_row = df.iloc[0]
    has_text = any(not pd.isna(value) and str(value).strip() for value in first_row)
    has_address = any(_has_address(value) for value in first_row)
    if has_text and not has_address:
        header_values = [None if pd.isna(value) else value for value in first_row.tolist()]
        return df.iloc[1:].reset_index(drop=True), header_values
    return df, None


def _normalized_key_from_parts(ter, sw, sn, hb, hm):
    return (ter, sw, frozenset(sn), hb, hm)


def _normalized_key_from_pool_item(item):
    return _normalized_key_from_parts(item['ter'], item['sw'], item['sn'], item['hb'], item['hm'])


def _relaxed_key_from_parts(ter, sw, sn, hb):
    return (ter, sw, frozenset(sn), hb)


def _relaxed_key_from_pool_item(item):
    return _relaxed_key_from_parts(item['ter'], item['sw'], item['sn'], item['hb'])


def _column_index_from_letter(value):
    text = str(value).strip().upper()
    if not re.fullmatch(r"[A-Z]+", text):
        raise ValueError(f"Column must be an Excel letter like B or C: {value!r}")
    idx = 0
    for char in text:
        idx = idx * 26 + (ord(char) - 64)
    return idx - 1


def _iter_column_tokens(value):
    if value is None or value == "":
        return []
    if isinstance(value, (list, tuple)):
        tokens = []
        for item in value:
            tokens.extend(_iter_column_tokens(item))
        return tokens
    return [part.strip() for part in str(value).split(",") if part.strip()]


def _resolve_column_token(token, df, setting_name):
    if isinstance(token, int):
        idx = token - 1
    else:
        text = str(token).strip()
        if text.isdigit():
            idx = int(text) - 1
        else:
            idx = _column_index_from_letter(text)
    if idx < 0 or idx >= len(df.columns):
        max_col = col_letter(len(df.columns) - 1)
        raise ValueError(f"{setting_name}: column {token!r} is outside the sheet (available A:{max_col})")
    return idx, df.columns[idx]


def _resolve_target_columns(value, df):
    resolved = []
    seen = set()
    for token in _iter_column_tokens(value):
        idx, col = _resolve_column_token(token, df, "target_columns")
        if col not in seen:
            seen.add(col)
            resolved.append((idx, col))
    return resolved


def _resolve_column_selection(df, aligner_config=None):
    effective_config = dict(CONFIG)
    source_label = "config"
    if aligner_config is not None:
        effective_config.update(aligner_config)
        source_label = "gui"

    gt_setting = effective_config.get("ground_truth_column")
    targets_setting = effective_config.get("target_columns")
    max_align_columns = int(effective_config.get("max_auto_align_columns", MAX_ALIGN_COLUMNS) or MAX_ALIGN_COLUMNS)

    if gt_setting:
        gt_col_idx, gt_col_name = _resolve_column_token(gt_setting, df, "ground_truth_column")
        gt_source = source_label
    else:
        gt_col_idx, gt_col_name = detect_gt_column(df)
        gt_source = "auto"

    explicit_targets = _resolve_target_columns(targets_setting, df)
    if explicit_targets:
        target_cols = []
        for target_idx, target_col in explicit_targets:
            if target_idx == gt_col_idx:
                raise ValueError("target_columns must not include the ground_truth_column")
            target_cols.append(target_col)
        target_source = source_label
    else:
        all_cols_after_gt = [c for i, c in enumerate(df.columns) if i > gt_col_idx]
        target_cols = all_cols_after_gt[:max_align_columns]
        target_source = "auto"

    return gt_col_idx, gt_col_name, target_cols, gt_source, target_source


COMPANION_MODE_ALIASES = {
    "auto": "auto",
    "automatic": "auto",
    "": "auto",
    "none": "none",
    "off": "none",
    "no": "none",
    "left": "left",
    "right": "right",
    "between": "between",
    "block": "between",
    "left_block": "between",
    "right_block": "between",
}


def _normalize_companion_mode(value):
    return COMPANION_MODE_ALIASES.get(str(value or "auto").strip().lower(), "auto")


def _companion_mode_from_config(aligner_config=None):
    effective_config = dict(CONFIG)
    if aligner_config is not None:
        effective_config.update(aligner_config)
    return _normalize_companion_mode(
        effective_config.get("companion_mode", effective_config.get("linked_columns_mode", "auto"))
    )


def _effective_config(aligner_config=None):
    effective_config = dict(CONFIG)
    if aligner_config is not None:
        effective_config.update(aligner_config)
    return effective_config


def _collect_before_match_enabled(aligner_config=None):
    return _bool_config(_effective_config(aligner_config).get("collect_before_match"), False)


def _collect_whole_document_enabled(aligner_config=None):
    return _bool_config(_effective_config(aligner_config).get("collect_whole_document"), False)


def _collection_targets(df, gt_col_idx, target_cols, target_source, aligner_config=None):
    if not _collect_before_match_enabled(aligner_config):
        return target_cols, target_source, {}
    if not _collect_whole_document_enabled(aligner_config):
        mapping = {}
        for col in target_cols:
            if col in df.columns:
                mapping[col] = col_letter(list(df.columns).index(col))
        return target_cols, "assembled_columns" if mapping else target_source, mapping
    if target_source == "auto":
        return [COLLECTED_DOCUMENT_COLUMN], "assembled_document", {COLLECTED_DOCUMENT_COLUMN: None}
    output_col = target_cols[0] if target_cols else COLLECTED_DOCUMENT_COLUMN
    return [output_col], "assembled_document", {output_col: None}


def _display_column_label(df, col):
    if col in df.columns:
        return col_letter(list(df.columns).index(col))
    return str(col)


def _satellite_spec_from_config(aligner_config=None):
    effective_config = _effective_config(aligner_config)
    return str(
        effective_config.get("satellite_columns")
        or effective_config.get("companion_columns")
        or ""
    ).strip()


def _resolve_column_tokens_or_ranges(value, df, setting_name):
    result = []
    seen = set()
    for part in [item.strip() for item in str(value or "").split(",") if item.strip()]:
        range_match = re.fullmatch(r"([A-Za-z]+|\d+)\s*:\s*([A-Za-z]+|\d+)", part)
        if range_match:
            start_idx, _start_col = _resolve_column_token(range_match.group(1), df, setting_name)
            end_idx, _end_col = _resolve_column_token(range_match.group(2), df, setting_name)
            step = 1 if end_idx >= start_idx else -1
            for idx in range(start_idx, end_idx + step, step):
                col = df.columns[idx]
                if col not in seen:
                    seen.add(col)
                    result.append((idx, col))
            continue
        idx, col = _resolve_column_token(part, df, setting_name)
        if col not in seen:
            seen.add(col)
            result.append((idx, col))
    return result


def _explicit_companion_columns(df, target_cols, satellite_spec):
    spec = str(satellite_spec or "").strip()
    if not spec:
        return None
    companion_map = {}
    for group in [part.strip() for part in spec.split(";") if part.strip()]:
        if "=" in group:
            target_expr, satellite_expr = group.split("=", 1)
            target_expr = target_expr.strip()
        else:
            target_expr, satellite_expr = "", group
        if not satellite_expr.strip():
            continue
        if not target_expr:
            if len(target_cols) != 1:
                raise ValueError("satellite_columns without a target can be used only when one address target column is selected.")
            group_targets = [(None, target_cols[0])]
        elif target_expr in {"*", "all", "ALL"}:
            group_targets = [(None, col) for col in target_cols]
        else:
            group_targets = _resolve_column_tokens_or_ranges(target_expr, df, "satellite_columns target")
        satellites = _resolve_column_tokens_or_ranges(satellite_expr, df, "satellite_columns")
        for _target_idx, target_col in group_targets:
            if target_col not in target_cols:
                continue
            satellite_idxs = []
            satellite_cols = []
            for satellite_idx, satellite_col in satellites:
                if satellite_col == target_col:
                    continue
                if satellite_col in satellite_cols:
                    continue
                satellite_idxs.append(satellite_idx)
                satellite_cols.append(satellite_col)
            if not satellite_cols:
                continue
            companion_map[target_col] = {
                "side": "explicit",
                "idxs": satellite_idxs,
                "cols": satellite_cols,
            }
    return (companion_map, "explicit") if companion_map else None


def _df_index_from_source_row(source_row, output_headers):
    if source_row is None:
        return None
    index = int(source_row)
    if output_headers is not None:
        index -= 1
    return index


def _clean_satellite_value(value):
    if pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", str(value).replace("\xa0", " ")).strip()


def _candidate_satellite_signature(candidate, df, output_headers, companion_cols):
    df_row = _df_index_from_source_row(candidate.source_row, output_headers)
    if df_row is None or df_row not in df.index:
        return tuple("" for _column in companion_cols)
    return tuple(_clean_satellite_value(df.at[df_row, column]) for column in companion_cols)


def _candidate_address_signature(candidate, normalizer=None):
    ter, sw, sn, hb, hm = _parse_address_for_match(candidate.address, normalizer)
    if ter or sw or hb:
        return ("core", ter, sw, tuple(sorted(sn)), hb, hm)
    return ("text", _string_key_for_match(candidate.address, normalizer))


def _dedupe_collected_match_candidates(candidates, df, output_headers, companion_cols, normalizer=None):
    seen = set()
    result = []
    for candidate in candidates:
        address_key = _candidate_address_signature(candidate, normalizer)
        satellite_key = _candidate_satellite_signature(candidate, df, output_headers, companion_cols)
        key = (address_key, satellite_key)
        if key in seen:
            continue
        seen.add(key)
        result.append(candidate)
    return result


def _output_header_for_column(column, output_headers):
    if isinstance(column, str):
        return column
    try:
        index = int(column)
    except Exception:
        return column
    if 0 <= index < len(output_headers):
        return output_headers[index]
    return column


def _excel_column_name(column):
    try:
        index = int(column)
    except Exception:
        return str(column)
    if index < 0:
        return str(column)
    index += 1
    letters = []
    while index:
        index, remainder = divmod(index - 1, 26)
        letters.append(chr(65 + remainder))
    return "".join(reversed(letters))


def _normalize_output_address(value, normalizer):
    if normalizer is None or pd.isna(value):
        return value, None
    text = str(value).strip()
    if not text:
        return value, None
    record = normalizer.normalize(text)
    normalized_text = record.normalized or text
    original_parts = parse_address(text)
    normalized_parts = parse_address(normalized_text)
    original_has_street = bool(original_parts[1])
    original_has_house = bool(original_parts[3])
    normalized_has_street = bool(normalized_parts[1])
    normalized_has_house = bool(normalized_parts[3])
    if (
        (original_has_street and not normalized_has_street)
        or (original_has_house and not normalized_has_house)
        or (original_has_street and original_has_house and not (normalized_has_street and normalized_has_house))
    ):
        return text, {
            "reason": "post_normalization_lost_address_core",
            "original": text,
            "normalized": normalized_text,
        }
    return normalized_text, None


def _normalize_result_address_columns(result_df, target_cols, normalizer):
    if normalizer is None:
        return result_df, []
    normalized = result_df.copy()
    rejected = []
    for col in target_cols:
        if col not in normalized.columns:
            continue
        values = []
        for row_number, value in enumerate(normalized[col], start=1):
            next_value, issue = _normalize_output_address(value, normalizer)
            values.append(next_value)
            if issue is not None:
                issue = dict(issue)
                issue["row"] = row_number
                issue["column"] = col
                rejected.append(issue)
        normalized[col] = values
    if rejected:
        print(
            "[WARN] Post-normalization rejected "
            f"{len(rejected)} value(s) because address core would be degraded."
        )
        for issue in rejected[:10]:
            print(
                "[WARN]   "
                f"row={issue['row']} col={issue['column']}: "
                f"{issue['original']!r} -> {issue['normalized']!r}"
            )
    return normalized, rejected


def _normalization_audit_rows(rejected, output_headers=None):
    audit_rows = []
    for issue in rejected or []:
        column = issue.get("column")
        if output_headers is None:
            column_label = _excel_column_name(column)
        else:
            column_label = _output_header_for_column(column, output_headers)
        audit_rows.append(
            {
                "Audit_Type": "post_normalization_rejected",
                "Reason": issue.get("reason", ""),
                "Action": "kept_original_value",
                "Row": issue.get("row", ""),
                "Column": column_label,
                "Column_Key": column,
                "Original_Value": issue.get("original", ""),
                "Rejected_Normalized_Value": issue.get("normalized", ""),
            }
        )
    return audit_rows


def _write_result_workbook(output_file, result_df, *, header, audit_rows=None):
    if audit_rows:
        with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
            result_df.to_excel(writer, index=False, header=header, sheet_name="Sheet1")
            pd.DataFrame(audit_rows).to_excel(
                writer,
                index=False,
                sheet_name="AUDIT_CONFLICTS",
            )
        print(f"[INFO] Audit sheet written: AUDIT_CONFLICTS ({len(audit_rows)} row(s))")
    else:
        result_df.to_excel(output_file, index=False, header=header)


def _between_companion_columns(df, leading_idxs, target_idxs, target_cols, excluded_idxs):
    companion_map = {}
    if not target_idxs:
        return companion_map, "none"
    if len(target_idxs) != 1:
        raise ValueError("companion_mode=between requires exactly one target column.")

    target_idx = target_idxs[0]
    anchor_idx = max(leading_idxs) if leading_idxs else -1
    if target_idx > anchor_idx + 1:
        companion_idxs = [
            idx for idx in range(anchor_idx + 1, target_idx)
            if idx not in excluded_idxs
        ]
        side = "left_block"
    elif target_idx < anchor_idx - 1:
        companion_idxs = [
            idx for idx in range(target_idx + 1, anchor_idx)
            if idx not in excluded_idxs
        ]
        side = "right_block"
    else:
        companion_idxs = []
        side = "between"

    if companion_idxs:
        companion_map[target_cols[0]] = {
            "side": side,
            "idxs": companion_idxs,
            "cols": [df.columns[idx] for idx in companion_idxs],
        }
    return companion_map, side if companion_idxs else "none"


def _adjacent_companion_columns(df, target_cols, target_idxs, excluded_idxs, side_lock):
    companion_map = {}
    if side_lock not in {"left", "right"}:
        return companion_map, side_lock

    excluded = set(excluded_idxs)
    for target_col, target_idx in zip(target_cols, target_idxs):
        companion_idx = target_idx - 1 if side_lock == "left" else target_idx + 1
        if companion_idx < 0 or companion_idx >= len(df.columns):
            continue
        if companion_idx in excluded:
            continue
        companion_col = df.columns[companion_idx]
        companion_map[target_col] = {
            "side": side_lock,
            "idxs": [companion_idx],
            "cols": [companion_col],
        }
        excluded.add(companion_idx)

    return companion_map, side_lock


def _detect_companion_columns(df, leading_cols, target_cols, companion_mode="auto"):
    mode = _normalize_companion_mode(companion_mode)
    target_idxs = [list(df.columns).index(c) for c in target_cols]
    target_idx_set = set(target_idxs)
    leading_idxs = {list(df.columns).index(c) for c in leading_cols}
    excluded_idxs = target_idx_set | set(leading_idxs)

    if mode == "none":
        return {}, "none"
    if mode == "between":
        return _between_companion_columns(df, leading_idxs, target_idxs, target_cols, excluded_idxs)
    if mode in {"left", "right"}:
        return _adjacent_companion_columns(df, target_cols, target_idxs, excluded_idxs, mode)

    if len(target_idxs) == 1:
        companion_map, side = _between_companion_columns(df, leading_idxs, target_idxs, target_cols, excluded_idxs)
        if companion_map:
            return companion_map, side

    side_lock = _infer_companion_side(df, target_idxs, excluded_idxs, leading_idxs)
    if side_lock is None:
        return {}, side_lock
    return _adjacent_companion_columns(df, target_cols, target_idxs, excluded_idxs, side_lock)


def _infer_companion_side(df, target_idxs, excluded_idxs, leading_idxs):
    if not target_idxs:
        return None

    side_scores = {}
    for side in ("left", "right"):
        score = 0.0
        available_count = 0
        for target_idx in target_idxs:
            companion_idx = target_idx - 1 if side == "left" else target_idx + 1
            if companion_idx < 0 or companion_idx >= len(df.columns):
                continue
            if companion_idx in excluded_idxs:
                continue
            available_count += 1
            score += _column_fill_ratio(df, df.columns[companion_idx])
        side_scores[side] = (score, available_count)

    left_score, left_count = side_scores["left"]
    right_score, right_count = side_scores["right"]
    if len(target_idxs) > 1:
        if left_count < len(target_idxs):
            left_score = 0
        if right_count < len(target_idxs):
            right_score = 0
    if left_score <= 0 and right_score <= 0:
        return None
    if abs(left_score - right_score) > 0.05:
        return "left" if left_score > right_score else "right"
    if left_count != right_count:
        return "left" if left_count > right_count else "right"

    first_target = target_idxs[0]
    max_leading = max(leading_idxs) if leading_idxs else -1
    return "left" if first_target - max_leading > 1 else "right"


def _column_fill_ratio(df, col):
    values = df[col].dropna().astype(str).str.strip()
    values = values[values != '']
    return len(values) / max(1, len(df))


def detect_gt_column(df):
    if df.empty or len(df.columns) == 0:
        raise ValueError("Cannot detect ground truth column in an empty sheet.")

    row_count = max(1, len(df))
    best = None
    for col_idx, col in enumerate(df.columns):
        values = df[col].dropna().astype(str).str.strip()
        values = values[values != '']
        non_empty_count = len(values)
        if non_empty_count == 0:
            metrics = {
                "score": -1000.0,
                "fill_ratio": 0.0,
                "address_ratio": 0.0,
                "house_ratio": 0.0,
                "street_ratio": 0.0,
                "numeric_ratio": 0.0,
                "avg_len": 0.0,
            }
        else:
            fill_ratio = non_empty_count / row_count
            numeric_ratio = values.str.match(r'^\d+\.?\d*$').sum() / non_empty_count
            avg_len = float(values.str.len().mean())
            sample = values if non_empty_count <= 3000 else values.iloc[::max(1, non_empty_count // 3000)]

            parsed = [parse_address(value) for value in sample]
            address_ratio = sum(1 for ter, sw, sn, hb, hm in parsed if sw or hb) / len(parsed)
            house_ratio = sum(1 for ter, sw, sn, hb, hm in parsed if hb) / len(parsed)
            street_ratio = sum(1 for ter, sw, sn, hb, hm in parsed if sw) / len(parsed)
            marker_ratio = sample.str.contains(ADDRESS_MARKER_RE).sum() / len(sample)

            score = (
                fill_ratio * 140.0
                + address_ratio * 60.0
                + house_ratio * 25.0
                + street_ratio * 20.0
                + marker_ratio * 15.0
                + min(avg_len, 80.0) * 0.15
                - numeric_ratio * 120.0
            )
            if fill_ratio >= 0.98 and address_ratio >= 0.75:
                score += 60.0
            elif fill_ratio >= 0.90 and address_ratio >= 0.60:
                score += 30.0
            if avg_len < 8:
                score -= 30.0

            metrics = {
                "score": score,
                "fill_ratio": fill_ratio,
                "address_ratio": address_ratio,
                "house_ratio": house_ratio,
                "street_ratio": street_ratio,
                "numeric_ratio": numeric_ratio,
                "avg_len": avg_len,
            }

        if best is None or metrics["score"] > best["score"]:
            best = {"col_idx": col_idx, **metrics}

    assert best is not None
    print(
        "[INFO] Auto GT score: "
        f"Column {col_letter(best['col_idx'])}, "
        f"fill={best['fill_ratio']:.1%}, "
        f"address={best['address_ratio']:.1%}, "
        f"numeric={best['numeric_ratio']:.1%}, "
        f"score={best['score']:.1f}"
    )
    return best["col_idx"], df.columns[best["col_idx"]]


def col_letter(idx):
    result = ""
    while True:
        result = chr(65 + idx % 26) + result
        idx = idx // 26 - 1
        if idx < 0:
            break
    return result


def _strict_house_check(hb_gt, hm_gt, hb_tgt, hm_tgt):
    """Строгая проверка: base + mods."""
    if hb_gt and hb_tgt:
        return hb_gt == hb_tgt and hm_gt == hm_tgt
    if hb_gt and not hb_tgt:
        return False
    if not hb_gt and hb_tgt:
        return False
    return True


def _relaxed_house_check(hb_gt, hm_gt, hb_tgt, hm_tgt):
    """Мягкая проверка улицы, но не модификаторов дома.

    Литера, корпус, строение и похожие хвосты нельзя схлопывать с чистым
    номером дома: GT 10к2 не должен забирать target 10, и наоборот.
    """
    if hb_gt and hb_tgt:
        return hb_gt == hb_tgt and (hm_gt or "") == (hm_tgt or "")
    if hb_gt and not hb_tgt:
        return False
    if not hb_gt and hb_tgt:
        return False
    return True


def process_file(input_file, output_file, aligner_config=None):
    start_time = time.time()
    match_normalizer = _normalizer_from_config(aligner_config)
    post_match_normalizer = _post_match_normalizer_from_config(aligner_config)
    scope_profile = _normalizer_scope_profile(match_normalizer)
    print(f"\n{'='*60}")
    print(f"  Ultimate GT Aligner v5")
    print(f"  City: {CITY_NAME or '(not set)'}")
    print(f"{'='*60}")
    print(f"[INFO] Address normalizer for matching: {'ON' if match_normalizer else 'OFF'}")
    print(f"[INFO] Address normalizer after matching: {'ON' if post_match_normalizer else 'OFF'}")
    if match_normalizer is not None:
        print(f"[INFO] OKTMO data root: {match_normalizer.data_dir}")
        print(
            "[INFO] Match scope: "
            f"TER={match_normalizer.subject_ter_hint or '-'}, "
            f"municipality={match_normalizer.municipality_hint or '-'}"
        )
        if _scope_profile_enabled(scope_profile):
            counts = scope_profile.get("counts") or {}
            print(
                "[INFO] Weighted OKTMO scope: "
                f"municipality={counts.get('municipality', 0)}, "
                f"locality={counts.get('locality', 0)}, "
                f"context_required={counts.get('context_required', 0)}"
            )
    print(f"\n[INFO] Loading {input_file.name}...")
    df, output_headers = _read_excel_rows(input_file)
    
    gt_col_idx, gt_col_name, target_cols, gt_source, target_source = _resolve_column_selection(df, aligner_config)
    target_cols, target_source, collection_sources = _collection_targets(
        df,
        gt_col_idx,
        target_cols,
        target_source,
        aligner_config,
    )
    companion_mode = _companion_mode_from_config(aligner_config)
    print(f"[INFO] Ground Truth: Column {col_letter(gt_col_idx)} ({gt_source})")
    print(f"[INFO] Rows: {len(df)}")
    
    leading_cols = [df.columns[i] for i in range(gt_col_idx + 1)]
    explicit_companion = _explicit_companion_columns(df, target_cols, _satellite_spec_from_config(aligner_config))
    if explicit_companion:
        companion_map, companion_side = explicit_companion
    elif all(col in df.columns for col in target_cols):
        companion_map, companion_side = _detect_companion_columns(df, leading_cols, target_cols, companion_mode)
    else:
        companion_map, companion_side = {}, "none"
    companion_cols = [col for item in companion_map.values() for col in item["cols"]]
    skip_cols = [c for c in df.columns if c not in leading_cols and c not in target_cols and c not in companion_cols]
    
    print(f"[INFO] Aligning {len(target_cols)} column(s) ({target_source}): {', '.join(_display_column_label(df, c) for c in target_cols)}")
    print(f"[INFO] Linked columns mode: {companion_mode}")
    if companion_map:
        print(f"[INFO] Companion object columns: side={companion_side}")
        for target_col, companion in companion_map.items():
            target_letter = _display_column_label(df, target_col)
            companion_letters = [col_letter(idx) for idx in companion["idxs"]]
            fill_values = [_column_fill_ratio(df, comp_col) for comp_col in companion["cols"]]
            avg_fill = sum(fill_values) / max(1, len(fill_values))
            if len(companion_letters) == 1:
                label = companion_letters[0]
            else:
                label = f"{companion_letters[0]}:{companion_letters[-1]}"
            print(f"[INFO]   {label} -> {target_letter} (avg fill={avg_fill:.1%})")
    collection_pools = {}
    if collection_sources:
        if match_normalizer is None:
            raise RuntimeError("collect_before_match requires address normalization runtime.")
        print("[INFO] Address candidate collection before matching: ON")
        for target_col, source_columns in collection_sources.items():
            candidates, collection_stats = _collect_address_match_candidates_from_file(
                input_file,
                normalizer=match_normalizer,
                source_columns=source_columns,
                clean_duplicates=False,
            )
            companion_cols_for_target = companion_map.get(target_col, {}).get("cols", [])
            before_satellite_dedupe = len(candidates)
            candidates = _dedupe_collected_match_candidates(
                candidates,
                df,
                output_headers,
                companion_cols_for_target,
                normalizer=match_normalizer,
            )
            collection_stats = dict(collection_stats)
            collection_stats["normalized_rows"] = len(candidates)
            collection_stats["duplicate_rows"] = int(collection_stats.get("duplicate_rows") or 0) + max(
                0,
                before_satellite_dedupe - len(candidates),
            )
            collection_pools[target_col] = candidates
            source_label = source_columns or "whole document"
            print(
                f"[INFO]   {source_label} -> {_display_column_label(df, target_col)}: "
                f"{collection_stats.get('normalized_rows', 0)} clean candidate(s), "
                f"{collection_stats.get('rejected_rows', 0)} rejected, "
                f"{collection_stats.get('duplicate_rows', 0)} duplicate"
            )
    
    print(f"\n[INFO] Parsing Ground Truth...")
    gt_parsed = df[gt_col_name].progress_apply(lambda value: _parse_address_for_match(value, match_normalizer))
    gt_ter = [p[0] for p in gt_parsed]
    gt_sw  = [p[1] for p in gt_parsed]
    gt_sn  = [p[2] for p in gt_parsed]
    gt_hb  = [p[3] for p in gt_parsed]
    gt_hm  = [p[4] for p in gt_parsed]
    gt_records = [
        _record_for_match(df.iloc[i][gt_col_name], match_normalizer)
        for i in range(len(df))
    ] if match_normalizer is not None else [None] * len(df)
    gt_scopes = [
        _alignment_scope_match(df.iloc[i][gt_col_name], gt_records[i], scope_profile)
        for i in range(len(df))
    ] if _scope_profile_enabled(scope_profile) else [{} for _ in range(len(df))]
    gt_keys = {
        _normalized_key_from_parts(gt_ter[i], gt_sw[i], gt_sn[i], gt_hb[i], gt_hm[i])
        for i in range(len(df))
        if gt_sw[i] or gt_hb[i]
    }
    
    result_df = pd.DataFrame()
    for col in leading_cols:
        result_df[col] = df[col]
    
    unmatched_tails = {col: [] for col in target_cols}
    companion_tails = {col: [] for companion in companion_map.values() for col in companion["cols"]}
    
    for col_num, col in enumerate(target_cols):
        col_idx = list(df.columns).index(col) if col in df.columns else None
        col_ltr = col_letter(col_idx) if col_idx is not None else str(col)
        
        print(f"\n{'='*55}")
        print(f"  Aligning Column {col_ltr} ({col_num+1}/{len(target_cols)})")
        print(f"{'='*55}\n")
        
        companion = companion_map.get(col)
        companion_cols_for_target = companion["cols"] if companion else []
        collected_candidates = collection_pools.get(col)
        if collected_candidates is not None:
            target_items = [
                (candidate_index, candidate.address, candidate.source_row, candidate)
                for candidate_index, candidate in enumerate(collected_candidates)
                if str(candidate.address or "").strip()
            ]
        else:
            target_data = df[[col]].copy().dropna()
            target_items = [
                (idx, orig, idx, None)
                for idx, orig in target_data[col].items()
            ]
        pool = {}
        string_pool = defaultdict(list)
        hash_pool = defaultdict(list)
        relaxed_hash_pool = defaultdict(list)
        core_hash_pool = defaultdict(list)
        
        for idx, orig, source_row, collected_candidate in target_items:
            record = _record_for_match(orig, match_normalizer)
            ter, sw, sn, hb, hm = _parse_address_for_match(orig, match_normalizer)
            df_source_row = _df_index_from_source_row(source_row, output_headers) if collected_candidate is not None else source_row
            companion_values = {
                comp_col: df.at[df_source_row, comp_col]
                for comp_col in companion_cols_for_target
                if df_source_row is not None and df_source_row in df.index
            }
            pool[idx] = {
                'orig': orig,
                'companions': companion_values,
                'ter': ter,
                'sw': sw,
                'sn': sn,
                'hb': hb,
                'hm': hm,
                'record': record,
                'scope': _alignment_scope_match(orig, record, scope_profile) if _scope_profile_enabled(scope_profile) else {},
                'source_candidate': collected_candidate,
                'source_row': df_source_row,
            }
            val = _string_key_for_match(orig, match_normalizer)
            string_pool[val].append(idx)
            hash_pool[(ter, sw, sn, hb, hm)].append(idx)
            relaxed_hash_pool[(ter, sw, sn, hb)].append(idx)
            if sw and hb:
                core_hash_pool[(sw, sn, hb, hm)].append(idx)
        
        aligned = [None] * len(df)
        aligned_companions = {
            comp_col: [None] * len(df)
            for comp_col in companion_cols_for_target
        }
        stats = {'s0': 0, 's1': 0, 's2': 0, 's2r': 0, 's2c': 0, 's3': 0, 's4': 0, 's5': 0}

        def place_match(row_i, pool_idx):
            aligned[row_i] = pool[pool_idx]['orig']
            for comp_col, comp_aligned in aligned_companions.items():
                comp_aligned[row_i] = pool[pool_idx]['companions'].get(comp_col)

        def scope_pair_score(row_i, target_item):
            if not _scope_profile_enabled(scope_profile):
                return 0.0
            return _alignment_scope_pair_score(
                gt_scopes[row_i],
                target_item.get('scope'),
                gt_records[row_i],
                target_item.get('record'),
            )

        def scope_pair_blocked(row_i, target_item):
            return _scope_profile_enabled(scope_profile) and _alignment_scope_pair_blocked(
                gt_records[row_i],
                target_item.get('record'),
            )

        def row_core_match(row_i, target_item):
            t, sw, sn, hb, hm = gt_ter[row_i], gt_sw[row_i], gt_sn[row_i], gt_hb[row_i], gt_hm[row_i]
            if not sw or not hb:
                return False
            if sw != target_item['sw'] or sn != target_item['sn']:
                return False
            if not _relaxed_house_check(hb, hm, target_item['hb'], target_item['hm']):
                return False
            return not scope_pair_blocked(row_i, target_item)

        if collected_candidates is not None:
            print("[0/5] Source Row Core Match...")
            source_row_pool = defaultdict(list)
            for idx, item in pool.items():
                source_row = item.get('source_row')
                if source_row is not None:
                    source_row_pool[source_row].append(idx)
            for i in tqdm(range(len(df)), desc="  Stage 0"):
                if aligned[i] is not None:
                    continue
                for idx in list(source_row_pool.get(i, [])):
                    if idx in pool and row_core_match(i, pool[idx]):
                        place_match(i, idx)
                        del pool[idx]
                        stats['s0'] += 1
                        break
            print(f"   → {stats['s0']}")
        
        # ─── Stage 1 ───
        print("[1/5] Exact String Match...")
        for i in tqdm(range(len(df)), desc="  Stage 1"):
            gt_orig = df.iloc[i][gt_col_name]
            if pd.isna(gt_orig): continue
            val = _string_key_for_match(gt_orig, match_normalizer)
            if val in string_pool:
                while string_pool[val]:
                    idx = string_pool[val].pop()
                    if idx in pool:
                        place_match(i, idx)
                        del pool[idx]
                        stats['s1'] += 1
                        break
        print(f"   → {stats['s1']}")
        
        # ─── Stage 2 ───
        print("[2/5] Component Hash...")
        remaining = []
        for i in tqdm(range(len(df)), desc="  Stage 2"):
            if aligned[i] is not None: continue
            t, sw, sn, hb, hm = gt_ter[i], gt_sw[i], gt_sn[i], gt_hb[i], gt_hm[i]
            if not sw and not hb:
                remaining.append(i); continue
            key = (t, sw, sn, hb, hm)
            found = False
            if key in hash_pool:
                while hash_pool[key]:
                    idx = hash_pool[key].pop()
                    if idx in pool:
                        place_match(i, idx)
                        del pool[idx]
                        stats['s2'] += 1
                        found = True; break
            if not found:
                remaining.append(i)
        print(f"   → {stats['s2']}")

        # ─── Stage 2R ───
        print("[2R/5] Relaxed Component Hash...")
        remaining_3 = []
        for i in tqdm(remaining, desc="  Stage 2R"):
            if aligned[i] is not None: continue
            t, sw, sn, hb, hm = gt_ter[i], gt_sw[i], gt_sn[i], gt_hb[i], gt_hm[i]
            if not sw and not hb:
                remaining_3.append(i); continue
            key = (t, sw, sn, hb)
            found = False
            if key in relaxed_hash_pool:
                while relaxed_hash_pool[key]:
                    idx = relaxed_hash_pool[key].pop()
                    if idx in pool:
                        tgt = pool[idx]
                        if not _relaxed_house_check(hb, hm, tgt['hb'], tgt['hm']):
                            continue
                        place_match(i, idx)
                        del pool[idx]
                        stats['s2r'] += 1
                        found = True; break
            if not found:
                remaining_3.append(i)
        print(f"   → {stats['s2r']}")

        if collected_candidates is not None:
            # ─── Stage 2C ───
            print("[2C/5] Core Hash (street + house, no territory)...")
            remaining_3c = []
            for i in tqdm(remaining_3, desc="  Stage 2C"):
                if aligned[i] is not None:
                    continue
                sw, sn, hb, hm = gt_sw[i], gt_sn[i], gt_hb[i], gt_hm[i]
                if not sw or not hb:
                    remaining_3c.append(i)
                    continue
                key = (sw, sn, hb, hm)
                found = False
                if key in core_hash_pool:
                    while core_hash_pool[key]:
                        idx = core_hash_pool[key].pop()
                        if idx not in pool:
                            continue
                        tgt = pool[idx]
                        if scope_pair_blocked(i, tgt):
                            continue
                        if sn != tgt['sn']:
                            continue
                        if not _strict_house_check(hb, hm, tgt['hb'], tgt['hm']):
                            continue
                        place_match(i, idx)
                        del pool[idx]
                        stats['s2c'] += 1
                        found = True
                        break
                if not found:
                    remaining_3c.append(i)
            print(f"   → {stats['s2c']}")
        else:
            remaining_3c = remaining_3
        
        # ─── Stage 3 ───
        print("[3/5] Fuzzy Strict (intra-territory)...")
        territory_clusters = defaultdict(dict)
        for idx, v in pool.items():
            territory_clusters[v['ter']][idx] = v['sw']
        remaining_4 = []
        for i in tqdm(remaining_3c, desc="  Stage 3"):
            if not pool: remaining_4.append(i); continue
            t, sw, sn, hb, hm = gt_ter[i], gt_sw[i], gt_sn[i], gt_hb[i], gt_hm[i]
            if not sw and not hb: remaining_4.append(i); continue
            cluster = territory_clusters.get(t, {})
            if not cluster: remaining_4.append(i); continue
            if not sw and hb:
                fk = None
                for k in list(cluster.keys()):
                    if k in pool and scope_pair_blocked(i, pool[k]):
                        continue
                    if k in pool and pool[k]['hb']==hb and pool[k]['hm']==hm and pool[k]['sn']==sn:
                        fk = k; break
                if fk is not None:
                    place_match(i, fk)
                    del pool[fk]; cluster.pop(fk,None); stats['s3'] += 1
                else: remaining_4.append(i)
                continue
            matches = process.extract(sw, cluster, scorer=fuzz.token_set_ratio, score_cutoff=75, limit=50)
            bk, bw = None, -1
            for _,sc,key in matches:
                if key not in pool: continue
                tgt = pool[key]
                if scope_pair_blocked(i, tgt): continue
                if sn != tgt['sn']: continue
                if not _strict_house_check(hb,hm,tgt['hb'],tgt['hm']): continue
                w = sc + (50 if hb and tgt['hb'] and hb==tgt['hb'] else 0)
                w += scope_pair_score(i, tgt)
                if w > bw: bw=w; bk=key
            if bk is not None:
                place_match(i, bk)
                del pool[bk]; cluster.pop(bk,None); stats['s3'] += 1
            else: remaining_4.append(i)
        print(f"   → {stats['s3']}")
        
        # ─── Stage 4 ───
        print("[4/5] Fuzzy Strict (cross-territory)...")
        remaining_5 = []
        if remaining_4 and pool:
            pool_sw = {k: v['sw'] for k, v in pool.items()}
            for i in tqdm(remaining_4, desc="  Stage 4"):
                if not pool: remaining_5.append(i); continue
                t, sw, sn, hb, hm = gt_ter[i], gt_sw[i], gt_sn[i], gt_hb[i], gt_hm[i]
                if not sw and not hb: remaining_5.append(i); continue
                if not sw and hb:
                    fk = None
                    fw = -1
                    for k, v in pool.items():
                        if scope_pair_blocked(i, v):
                            continue
                        if v['hb']==hb and v['hm']==hm and v['sn']==sn:
                            w = 100 + scope_pair_score(i, v)
                            if w > fw:
                                fw = w; fk = k
                    if fk is not None:
                        place_match(i, fk)
                        del pool[fk]; pool_sw.pop(fk,None); stats['s4'] += 1
                    else: remaining_5.append(i)
                    continue
                matches = process.extract(sw, pool_sw, scorer=fuzz.token_set_ratio, score_cutoff=85, limit=100)
                bk, bw = None, -1
                for _,sc,key in matches:
                    if key not in pool: continue
                    tgt = pool[key]
                    if scope_pair_blocked(i, tgt): continue
                    if sn != tgt['sn']: continue
                    if not _strict_house_check(hb,hm,tgt['hb'],tgt['hm']): continue
                    w = sc
                    if hb and tgt['hb'] and hb==tgt['hb']: w += 50
                    if t and tgt['ter'] and t==tgt['ter']: w += 30
                    w += scope_pair_score(i, tgt)
                    if w > bw: bw=w; bk=key
                if bk is not None:
                    place_match(i, bk)
                    del pool[bk]; pool_sw.pop(bk,None); stats['s4'] += 1
                else: remaining_5.append(i)
        else:
            remaining_5 = remaining_4
        print(f"   → {stats['s4']}")
        
        # ─── Stage 5: RELAXED ───
        print("[5/5] Relaxed Match (street + protected house mods)...")
        if remaining_5 and pool:
            pool_sw_r = {k: v['sw'] for k, v in pool.items()}
            for i in tqdm(remaining_5, desc="  Stage 5"):
                if not pool: break
                t, sw, sn, hb, hm = gt_ter[i], gt_sw[i], gt_sn[i], gt_hb[i], gt_hm[i]
                if not sw and not hb: continue
                if not sw and hb:
                    fk, fw = None, -1
                    for k, v in pool.items():
                        if scope_pair_blocked(i, v):
                            continue
                        if _relaxed_house_check(hb, hm, v['hb'], v['hm']) and v['sn']==sn:
                            w = 100 + (30 if t and v['ter'] and t==v['ter'] else 0)
                            w += scope_pair_score(i, v)
                            if w > fw: fw=w; fk=k
                    if fk is not None:
                        place_match(i, fk)
                        del pool[fk]; pool_sw_r.pop(fk,None); stats['s5'] += 1
                    continue
                matches = process.extract(sw, pool_sw_r, scorer=fuzz.token_set_ratio, score_cutoff=80, limit=200)
                bk, bw = None, -1
                for _,sc,key in matches:
                    if key not in pool: continue
                    tgt = pool[key]
                    if scope_pair_blocked(i, tgt): continue
                    if sn != tgt['sn']: continue
                    if not _relaxed_house_check(hb, hm, tgt['hb'], tgt['hm']): continue
                    w = sc
                    if hb and tgt['hb'] and hb==tgt['hb']: w += 50
                    if t and tgt['ter'] and t==tgt['ter']: w += 30
                    if hm and tgt['hm'] and hm==tgt['hm']: w += 20
                    w += scope_pair_score(i, tgt)
                    if w > bw: bw=w; bk=key
                if bk is not None:
                    place_match(i, bk)
                    del pool[bk]; pool_sw_r.pop(bk,None); stats['s5'] += 1
        print(f"   → {stats['s5']}")
        
        total = sum(stats.values())
        precise = stats['s0'] + stats['s1'] + stats['s2'] + stats['s2c'] + stats['s3'] + stats['s4']
        relaxed_total = stats['s2r'] + stats['s5']
        unmatched = len(pool)
        tail_items = []
        duplicate_tail_skips = 0
        for v in pool.values():
            if _normalized_key_from_pool_item(v) in gt_keys:
                duplicate_tail_skips += 1
            else:
                tail_items.append(v['orig'])
                for comp_col in companion_cols_for_target:
                    companion_tails[comp_col].append(v['companions'].get(comp_col))
        print(f"\n   ┌─ Column {col_ltr} Summary ──────────────")
        print(f"   │ Stage 0 (Source Row):     {stats['s0']:>6}")
        print(f"   │ Stage 1 (Exact String):   {stats['s1']:>6}")
        print(f"   │ Stage 2 (Component Hash): {stats['s2']:>6}")
        print(f"   │ Stage 2R (Relaxed Hash):  {stats['s2r']:>6}")
        if collected_candidates is not None:
            print(f"   │ Stage 2C (Core Hash):     {stats['s2c']:>6}")
        print(f"   │ Stage 3 (Fuzzy Strict):   {stats['s3']:>6}")
        print(f"   │ Stage 4 (Cross Strict):   {stats['s4']:>6}")
        print(f"   │ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─")
        print(f"   │ Precise total:            {precise:>6}")
        print(f"   │ Stage 5 (Relaxed):        {stats['s5']:>6}")
        print(f"   │ Relaxed total:            {relaxed_total:>6}")
        print(f"   ├──────────────────────────────────")
        print(f"   │ Grand total:              {total:>6}")
        print(f"   │ Unmatched raw:            {unmatched:>6}")
        print(f"   │ Known duplicate tail:     {duplicate_tail_skips:>6}")
        print(f"   │ Unmatched tail:           {len(tail_items):>6}")
        print(f"   └──────────────────────────────────")
        
        unmatched_tails[col].extend(tail_items)
        if companion and companion["side"].startswith("left"):
            for comp_col in companion_cols_for_target:
                result_df[comp_col] = aligned_companions[comp_col]
            result_df[col] = aligned
        elif companion:
            result_df[col] = aligned
            for comp_col in companion_cols_for_target:
                result_df[comp_col] = aligned_companions[comp_col]
        else:
            result_df[col] = aligned
    
    for col in skip_cols:
        result_df[col] = df[col]

    max_tail = max((len(lst) for lst in unmatched_tails.values()), default=0)
    if max_tail > 0:
        print(f"\n[INFO] Appending unmatched tail ({max_tail} rows)...")
        tail_dict = {}
        for c in result_df.columns:
            if c in target_cols:
                lst = unmatched_tails[c].copy()
                lst.extend([None] * (max_tail - len(lst)))
                tail_dict[c] = lst
            elif c in companion_tails:
                lst = companion_tails[c].copy()
                lst.extend([None] * (max_tail - len(lst)))
                tail_dict[c] = lst
            else:
                tail_dict[c] = [None] * max_tail
        tail_df = pd.DataFrame(tail_dict)
        result_df = pd.concat([result_df, tail_df], ignore_index=True)

    normalization_rejections = []
    if post_match_normalizer is not None:
        print("[INFO] Normalizing aligned address columns after matching...")
        result_df, normalization_rejections = _normalize_result_address_columns(
            result_df,
            target_cols,
            post_match_normalizer,
        )

    print(f"\n[INFO] Saving...")
    if output_headers is None:
        audit_rows = _normalization_audit_rows(normalization_rejections)
        _write_result_workbook(output_file, result_df, header=False, audit_rows=audit_rows)
    else:
        result_df.columns = [
            _output_header_for_column(c, output_headers)
            for c in result_df.columns
        ]
        audit_rows = _normalization_audit_rows(normalization_rejections, output_headers)
        _write_result_workbook(output_file, result_df, header=True, audit_rows=audit_rows)
    elapsed = round(time.time() - start_time, 2)
    print(f"\n[SUCCESS] Done! Time: {elapsed}s")
    print(f"[INFO] Output: {output_file}")


def batch_process(input_dir, output_dir):
    in_path = Path(input_dir)
    out_path = Path(output_dir)
    in_path.mkdir(exist_ok=True)
    out_path.mkdir(exist_ok=True)
    files = list(in_path.glob("*.xlsx"))
    if not files:
        print("[WARN] No .xlsx files found in", in_path)
        return
    print(f"\n[INFO] Found {len(files)} file(s)")
    for f in files:
        out = out_path / f"Aligned_{f.name}"
        try:
            process_file(f, out)
            from system_core.excel_layout import format_workbook

            format_workbook(out)
            print(f"[INFO] Auto-layout applied: {out.name}")
        except Exception as e:
            print(f"\n[ERROR] {f.name}: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python Ultimate_GT_Aligner_v5.py <input_dir> <output_dir>")
        sys.exit(1)
    batch_process(sys.argv[1], sys.argv[2])
