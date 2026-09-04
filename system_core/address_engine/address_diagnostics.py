from __future__ import annotations

from collections import Counter
from typing import Any, Iterable
import re


STREET_MARKER_RE = re.compile(
    r"\b(?:ул\.?|улица|пер\.?|переулок|пр-?кт|проспект|шоссе|проезд|пр-д\.?|"
    r"б-?р|бульвар|наб\.?|набережная|пл\.?|площадь|тупик|аллея|линия)\b",
    re.IGNORECASE,
)
HOUSE_MARKER_RE = re.compile(r"\b(?:д\.?|дом|зд\.?|здание|стр\.?|строение)\s*\d", re.IGNORECASE)
OBJECT_CONTEXT_RE = re.compile(
    r"\b(?:школа|сош|оош|ноо|лицей|гимназия|детск\w*\s+сад|садик|доу|"
    r"колледж|техникум|училищ\w*|университет|академия|институт|"
    r"учрежден\w*|организац\w*)\b",
    re.IGNORECASE,
)
ROUTE_CONTEXT_RE = re.compile(
    r"\b(?:автобусн\w*\s+маршрут|маршрут|остановочн\w+\s+пункт|остановка|"
    r"дорога\s+к\s+|трасса|автодорог\w*)\b",
    re.IGNORECASE,
)
MICRODISTRICT_RE = re.compile(r"\b(?:мкр\.?|микрорайон|квартал|кв-л\.?)\b", re.IGNORECASE)


def record_issue_codes(record: Any, raw: Any = None) -> tuple[str, ...]:
    row = _row_from_record(record, raw=raw)
    return row_issue_codes(row)


def row_issue_codes(row: dict[str, Any]) -> tuple[str, ...]:
    issues: list[str] = []
    address = _clean(row.get("Normalized_Address")) or _clean(row.get("Raw_Address")) or ""
    raw = _clean(row.get("Raw_Address")) or address
    if not address:
        return ("empty_address",)
    if len(address) > 700:
        issues.append("address_too_long")
    if _is_subject_only_address(address):
        issues.append("subject_only_address")

    street = _clean(row.get("Street"))
    territory = _clean(row.get("Territory"))
    microdistrict = _clean(row.get("Microdistrict"))
    house = _clean(row.get("House"))
    house_base = _clean(row.get("House_Base")) or _house_base_from_house(house)

    if _is_too_general_location(address, street=street, territory=territory, microdistrict=microdistrict, house_base=house_base):
        issues.append("too_general_location")
    if not house_base:
        if street or territory or microdistrict:
            issues.append("street_without_house")
        else:
            issues.append("no_house")
    elif _is_invalid_house_base(house_base):
        issues.append("invalid_house_number")
    elif not (street or territory or microdistrict):
        issues.append("house_without_street_or_territory")

    if _contains_org_context(address):
        issues.append("object_name_in_address")
    if _looks_like_route_fragment(address) or _looks_like_route_fragment(raw):
        issues.append("route_fragment_in_address")
    if _has_unbalanced_brackets(address) or _has_unbalanced_brackets(street):
        issues.append("unbalanced_address_fragment")
    return tuple(dict.fromkeys(issues))


def diagnostic_summary(rows_or_records: Iterable[Any]) -> dict[str, Any]:
    counter: Counter[str] = Counter()
    total = 0
    clean = 0
    samples: dict[str, list[str]] = {}
    for item in rows_or_records:
        total += 1
        if isinstance(item, dict):
            issues = row_issue_codes(item)
            sample = _clean(item.get("Normalized_Address")) or _clean(item.get("Raw_Address")) or ""
        else:
            issues = record_issue_codes(item)
            sample = _clean(getattr(item, "normalized", None)) or _clean(getattr(item, "raw", None)) or ""
        if not issues:
            clean += 1
            continue
        counter.update(issues)
        for issue in issues:
            bucket = samples.setdefault(issue, [])
            if sample and len(bucket) < 5:
                bucket.append(sample)
    return {
        "total": total,
        "clean": clean,
        "issue_rows": total - clean,
        "issues": dict(counter),
        "samples": samples,
    }


def _row_from_record(record: Any, raw: Any = None) -> dict[str, Any]:
    parts = getattr(record, "parts", None)
    slots = record.slot_dict() if hasattr(record, "slot_dict") else {}
    return {
        "Raw_Address": raw if raw is not None else getattr(record, "raw", None),
        "Normalized_Address": getattr(record, "normalized", None),
        "Subject": getattr(record, "subject", None) or slots.get("subject"),
        "Municipality": getattr(record, "municipality", None) or slots.get("municipality"),
        "Locality": slots.get("locality"),
        "Territory": slots.get("territory"),
        "Microdistrict": slots.get("microdistrict"),
        "Street": slots.get("street"),
        "House": slots.get("house"),
        "House_Base": slots.get("house_base") or getattr(record, "house_base", None),
        "Premise": slots.get("premise"),
        "OKTMO_Code": getattr(record, "oktmo_code", None),
        "OKTMO_Name": getattr(record, "oktmo_name", None),
        "Parts_Rendered": getattr(parts, "rendered", None) if parts is not None else None,
    }


def _is_too_general_location(
    address: str,
    *,
    street: str | None,
    territory: str | None,
    microdistrict: str | None,
    house_base: str | None,
) -> bool:
    if street or territory or microdistrict or house_base:
        return False
    text = _clean(address) or ""
    if not text:
        return False
    if STREET_MARKER_RE.search(text) or MICRODISTRICT_RE.search(text) or HOUSE_MARKER_RE.search(text):
        return False
    key = _norm(text)
    markers = (
        "федеральный округ",
        "область",
        "край",
        "республика",
        "автономный округ",
        "муниципальный округ",
        "муниципальный район",
        "городской округ",
        "город ",
        "г ",
    )
    return any(marker in key for marker in markers)


def _is_subject_only_address(value: Any) -> bool:
    text = _norm(value)
    if not text:
        return False
    return bool(
        re.fullmatch(
            r"(?:[а-я ]+\s+)?(?:область|край|республика|автономный округ|федеральный округ)",
            text,
        )
    )


def _is_invalid_house_base(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return bool(re.fullmatch(r"0+[а-яa-z]?", text, flags=re.IGNORECASE))


def _house_base_from_house(value: Any) -> str | None:
    match = re.search(r"\b(?:д\.?|дом)?\s*(\d+[а-яa-z]?)\b", str(value or ""), flags=re.IGNORECASE)
    return match.group(1).lower() if match else None


def _contains_org_context(value: Any) -> bool:
    return bool(OBJECT_CONTEXT_RE.search(str(value or "")))


def _looks_like_route_fragment(value: Any) -> bool:
    return bool(ROUTE_CONTEXT_RE.search(str(value or "")))


def _has_unbalanced_brackets(value: Any) -> bool:
    text = str(value or "")
    return text.count("(") != text.count(")") or text.count("[") != text.count("]")


def _clean(value: Any) -> str | None:
    text = str(value or "").replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text).strip(" ,;")
    if not text or text.lower() == "nan":
        return None
    return text


def _norm(value: Any) -> str:
    text = str(value or "").lower().replace("ё", "е")
    text = re.sub(r"[^0-9a-zа-я]+", " ", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()
