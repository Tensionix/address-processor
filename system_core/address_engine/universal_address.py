from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import re

from . import audion_address_core as address_core
from .address_slots import build_address_parts, render_address_core
from .models import AddressParts
from .oktmo_lookup import lookup_municipality, lookup_oktmo_context


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"


@dataclass(frozen=True)
class NormalizedAddress:
    raw: str | None
    normalized: str | None
    postal_index: str | None
    territory_key: str
    street_words: str
    street_numbers: frozenset[str]
    house_base: str
    house_mods: str
    oktmo_code: str | None
    oktmo_name: str | None
    parent_subject: str | None
    subject: str | None
    federal_district: str | None
    autonomous_okrug: str | None
    municipality: str | None
    parts: AddressParts

    @property
    def has_address_core(self) -> bool:
        return bool(
            self.street_words
            or self.house_base
            or (self.parts.locality and (self.parts.street or self.parts.house))
        )

    @property
    def strict_key(self) -> tuple[str, str, frozenset[str], str, str]:
        return (
            self.territory_key,
            self.street_words,
            self.street_numbers,
            self.house_base,
            self.house_mods,
        )

    @property
    def relaxed_key(self) -> tuple[str, str, frozenset[str], str]:
        return (
            self.territory_key,
            self.street_words,
            self.street_numbers,
            self.house_base,
        )

    @property
    def match_key(self) -> str:
        numbers = ",".join(sorted(self.street_numbers))
        return "|".join(
            part
            for part in (
                self.territory_key,
                self.street_words,
                numbers,
                self.house_base,
                self.house_mods,
            )
            if part
        )

    def slot_dict(self) -> dict[str, Any]:
        data = self.parts.as_dict()
        data.update(
            {
                "postal_index": self.postal_index,
                "oktmo_code": self.oktmo_code,
                "oktmo_name": self.oktmo_name,
                "parent_subject": self.parent_subject or data.get("parent_subject"),
                "subject": self.subject or data.get("subject"),
                "federal_district": self.federal_district or data.get("federal_district"),
                "autonomous_okrug": self.autonomous_okrug or data.get("autonomous_okrug"),
                "municipality": self.municipality or data.get("municipality"),
                "territory_key": self.territory_key,
                "match_key": self.match_key,
            }
        )
        return data


class AddressNormalizer:
    def __init__(
        self,
        *,
        city_name: str | None = None,
        data_dir: str | Path | None = None,
        use_oktmo: bool = True,
        subject_ter_hint: str | None = None,
        subject_hint: str | None = None,
        municipality_hint: str | None = None,
    ) -> None:
        self.city_name = str(city_name or "").strip().lower().replace("ё", "е")
        self.data_dir = _coerce_data_dir(data_dir)
        self.use_oktmo = bool(use_oktmo)
        self.subject_ter_hint = _clean(subject_ter_hint)
        self.subject_hint = _clean(subject_hint)
        self.municipality_hint = _clean(municipality_hint)
        self._cache: dict[str, NormalizedAddress] = {}

    def normalize(self, value: Any) -> NormalizedAddress:
        raw = _clean(value)
        cache_key = raw or ""
        if cache_key in self._cache:
            return self._cache[cache_key]

        previous_city = address_core.CITY_NAME
        address_core.CITY_NAME = self.city_name
        try:
            result = self._normalize_uncached(raw)
        finally:
            address_core.CITY_NAME = previous_city

        self._cache[cache_key] = result
        return result

    def parse_for_match(self, value: Any) -> tuple[str, str, frozenset[str], str, str]:
        record = self.normalize(value)
        return record.strict_key

    def _normalize_uncached(self, raw: str | None) -> NormalizedAddress:
        if not raw:
            empty_parts = build_address_parts(None)
            return NormalizedAddress(
                raw=None,
                normalized=None,
                postal_index=None,
                territory_key="",
                street_words="",
                street_numbers=frozenset(),
                house_base="",
                house_mods="",
                oktmo_code=None,
                oktmo_name=None,
                parent_subject=None,
                subject=None,
                federal_district=None,
                autonomous_okrug=None,
                municipality=None,
                parts=empty_parts,
            )

        postal_index = extract_postal_index(raw)
        territory, street_words, street_numbers, house_base, house_mods = address_core.parse_address_components(raw)
        parts = build_address_parts(raw, postal_index=postal_index)
        oktmo_code: str | None = None
        oktmo_name: str | None = None
        parent_subject: str | None = None
        subject: str | None = None
        federal_district: str | None = None
        autonomous_okrug: str | None = None
        municipality: str | None = None
        explicit_locality = address_core.explicit_settlement_hint(raw)

        if self.use_oktmo and self.data_dir and (self.data_dir / "rosstat").exists():
            query = explicit_locality or parts.locality or territory or parts.territory
            if query:
                found = lookup_oktmo_context(
                    query,
                    self.data_dir,
                    subject_hint=self.subject_hint or raw,
                    subject_ter_hint=self.subject_ter_hint,
                    municipality_hint=self.municipality_hint,
                )
                if found:
                    oktmo_code = found.oktmo_code
                    oktmo_name = found.oktmo_name
                    municipality = found.municipality
                    parent_subject = found.parent_subject
                    subject = found.subject
                    federal_district = found.federal_district
                    autonomous_okrug = found.autonomous_okrug
            municipality = lookup_municipality(
                explicit_locality or territory or oktmo_name or parts.locality,
                self.data_dir,
                subject_hint=self.subject_hint or raw,
                subject_ter_hint=self.subject_ter_hint,
                oktmo_code=oktmo_code,
                municipality_hint=self.municipality_hint,
            ) or municipality
            parts = build_address_parts(
                raw,
                postal_index=postal_index,
                parent_subject=parent_subject,
                subject=subject,
                federal_district=federal_district,
                autonomous_okrug=autonomous_okrug,
                municipality=municipality,
                locality=None if oktmo_name else explicit_locality if (explicit_locality and municipality) else None,
                oktmo_name=oktmo_name,
            )

        normalized = render_address_core(parts, include_subject=bool(parts.subject or parts.parent_subject)) or raw
        final_territory, final_street_words, final_street_numbers, final_house_base, final_house_mods = (
            address_core.parse_address_components(normalized)
        )
        territory_key = _territory_key(oktmo_code, parts.locality, final_territory or territory)
        return NormalizedAddress(
            raw=raw,
            normalized=normalized,
            postal_index=postal_index,
            territory_key=territory_key,
            street_words=final_street_words or street_words,
            street_numbers=final_street_numbers or frozenset(street_numbers),
            house_base=final_house_base or house_base,
            house_mods=final_house_mods or house_mods,
            oktmo_code=oktmo_code,
            oktmo_name=oktmo_name,
            parent_subject=parent_subject,
            subject=subject,
            federal_district=federal_district,
            autonomous_okrug=autonomous_okrug,
            municipality=municipality,
            parts=parts,
        )


def extract_postal_index(value: Any) -> str | None:
    match = re.search(r"(?<!\d)(\d{6})(?!\d)", str(value or ""))
    return match.group(1) if match else None


def _territory_key(oktmo_code: str | None, locality: str | None, fallback: str | None) -> str:
    digits = re.sub(r"\D+", "", str(oktmo_code or ""))
    if digits:
        return f"oktmo:{digits}"
    locality_key = _norm(locality)
    if locality_key:
        return locality_key
    return _norm(fallback)


def _coerce_data_dir(value: str | Path | None) -> Path | None:
    if value in (None, ""):
        return DEFAULT_DATA_DIR
    path = Path(str(value)).expanduser()
    if path.name.lower() == "rosstat":
        return path.parent
    return path


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value).replace("\xa0", " ")).strip(" ,")
    if not text or text.lower() == "nan":
        return None
    return text


def _norm(value: str | None) -> str:
    text = str(value or "").lower().replace("ё", "е")
    text = re.sub(r"[^0-9a-zа-я]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()
