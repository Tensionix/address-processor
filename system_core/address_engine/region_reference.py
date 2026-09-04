from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import re


FEDERAL_DISTRICT_BY_REGION_ID = {
    "adygeya": "Южный федеральный округ",
    "altay_republic": "Сибирский федеральный округ",
    "bashkortostan": "Приволжский федеральный округ",
    "buryatiya": "Дальневосточный федеральный округ",
    "dagestan": "Северо-Кавказский федеральный округ",
    "ingushetiya": "Северо-Кавказский федеральный округ",
    "kabardino_balkariya": "Северо-Кавказский федеральный округ",
    "kalmykiya": "Южный федеральный округ",
    "karachaevo_cherkesiya": "Северо-Кавказский федеральный округ",
    "kareliya": "Северо-Западный федеральный округ",
    "komi": "Северо-Западный федеральный округ",
    "crimea": "Южный федеральный округ",
    "mari_el": "Приволжский федеральный округ",
    "mordoviya": "Приволжский федеральный округ",
    "sakha_yakutiya": "Дальневосточный федеральный округ",
    "severnaya_osetiya_alaniya": "Северо-Кавказский федеральный округ",
    "tatarstan": "Приволжский федеральный округ",
    "tyva": "Сибирский федеральный округ",
    "udmurtiya": "Приволжский федеральный округ",
    "khakasiya": "Сибирский федеральный округ",
    "chechnya": "Северо-Кавказский федеральный округ",
    "chuvashiya": "Приволжский федеральный округ",
    "altayskiy_krai": "Сибирский федеральный округ",
    "zabaykalskiy_krai": "Дальневосточный федеральный округ",
    "kamchatskiy_krai": "Дальневосточный федеральный округ",
    "krasnodarskiy_krai": "Южный федеральный округ",
    "krasnoyarskiy_krai": "Сибирский федеральный округ",
    "permskiy_krai": "Приволжский федеральный округ",
    "primorskiy_krai": "Дальневосточный федеральный округ",
    "stavropolskiy_krai": "Северо-Кавказский федеральный округ",
    "khabarovskiy_krai": "Дальневосточный федеральный округ",
    "amurskaya_oblast": "Дальневосточный федеральный округ",
    "arkhangelskaya_oblast": "Северо-Западный федеральный округ",
    "astrakhanskaya_oblast": "Южный федеральный округ",
    "belgorodskaya_oblast": "Центральный федеральный округ",
    "bryanskaya_oblast": "Центральный федеральный округ",
    "vladimirskaya_oblast": "Центральный федеральный округ",
    "volgogradskaya_oblast": "Южный федеральный округ",
    "vologodskaya_oblast": "Северо-Западный федеральный округ",
    "voronezhskaya_oblast": "Центральный федеральный округ",
    "ivanovskaya_oblast": "Центральный федеральный округ",
    "irkutskaya_oblast": "Сибирский федеральный округ",
    "kaliningradskaya_oblast": "Северо-Западный федеральный округ",
    "kaluzhskaya_oblast": "Центральный федеральный округ",
    "kemerovskaya_oblast": "Сибирский федеральный округ",
    "kirovskaya_oblast": "Приволжский федеральный округ",
    "kostromskaya_oblast": "Центральный федеральный округ",
    "kurganskaya_oblast": "Уральский федеральный округ",
    "kurskaya_oblast": "Центральный федеральный округ",
    "leningradskaya_oblast": "Северо-Западный федеральный округ",
    "lipetskaya_oblast": "Центральный федеральный округ",
    "magadanskaya_oblast": "Дальневосточный федеральный округ",
    "moskovskaya_oblast": "Центральный федеральный округ",
    "murmanskaya_oblast": "Северо-Западный федеральный округ",
    "nizhny_novgorod_oblast": "Приволжский федеральный округ",
    "novgorodskaya_oblast": "Северо-Западный федеральный округ",
    "novosibirskaya_oblast": "Сибирский федеральный округ",
    "omskaya_oblast": "Сибирский федеральный округ",
    "orenburgskaya_oblast": "Приволжский федеральный округ",
    "orlovskaya_oblast": "Центральный федеральный округ",
    "penzenskaya_oblast": "Приволжский федеральный округ",
    "pskovskaya_oblast": "Северо-Западный федеральный округ",
    "rostovskaya_oblast": "Южный федеральный округ",
    "ryazanskaya_oblast": "Центральный федеральный округ",
    "samarskaya_oblast": "Приволжский федеральный округ",
    "saratovskaya_oblast": "Приволжский федеральный округ",
    "sakhalinskaya_oblast": "Дальневосточный федеральный округ",
    "sverdlovskaya_oblast": "Уральский федеральный округ",
    "smolenskaya_oblast": "Центральный федеральный округ",
    "tambovskaya_oblast": "Центральный федеральный округ",
    "tverskaya_oblast": "Центральный федеральный округ",
    "tomskaya_oblast": "Сибирский федеральный округ",
    "tulskaya_oblast": "Центральный федеральный округ",
    "tyumenskaya_oblast": "Уральский федеральный округ",
    "ulyanovskaya_oblast": "Приволжский федеральный округ",
    "chelyabinskaya_oblast": "Уральский федеральный округ",
    "yaroslavskaya_oblast": "Центральный федеральный округ",
    "moskva": "Центральный федеральный округ",
    "sankt_peterburg": "Северо-Западный федеральный округ",
    "sevastopol": "Южный федеральный округ",
    "evreyskaya_avtonomnaya_oblast": "Дальневосточный федеральный округ",
    "nenetskiy_ao": "Северо-Западный федеральный округ",
    "khanty_mansiyskiy_ao_yugra": "Уральский федеральный округ",
    "chukotskiy_ao": "Дальневосточный федеральный округ",
    "yamalo_nenetskiy_ao": "Уральский федеральный округ",
    "donetskaya_narodnaya_respublika": "Южный федеральный округ",
    "luganskaya_narodnaya_respublika": "Южный федеральный округ",
    "zaporozhskaya_oblast": "Южный федеральный округ",
    "khersonskaya_oblast": "Южный федеральный округ",
}
_SUBJECT_TYPE_WORDS = {
    "область",
    "край",
    "республика",
    "округ",
    "автономный",
    "автономная",
    "город",
    "федеральный",
    "значение",
}


@dataclass(frozen=True)
class RegionEntry:
    region_id: str
    display_name: str
    short_name: str
    subject_type: str
    aliases: tuple[str, ...]
    federal_district: str | None

    @property
    def is_autonomous_okrug(self) -> bool:
        return self.subject_type.lower().replace("ё", "е") == "автономный округ"


def load_region_entries(data_dir: Path) -> tuple[RegionEntry, ...]:
    path = data_dir / "regions_reference.yaml"
    if not path.exists():
        return ()
    try:
        import yaml

        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return ()
    result: list[RegionEntry] = []
    for item in payload.get("regions") or []:
        if not isinstance(item, dict):
            continue
        region_id = str(item.get("region_id") or "").strip()
        display_name = str(item.get("display_name") or "").strip()
        short_name = str(item.get("short_name") or display_name).strip()
        subject_type = str(item.get("subject_type") or "").strip()
        if not region_id or not display_name:
            continue
        aliases = tuple(str(alias).strip() for alias in item.get("aliases") or [] if str(alias).strip())
        federal_district = str(item.get("federal_district") or FEDERAL_DISTRICT_BY_REGION_ID.get(region_id) or "").strip()
        result.append(
            RegionEntry(
                region_id=region_id,
                display_name=display_name,
                short_name=short_name,
                subject_type=subject_type,
                aliases=aliases,
                federal_district=federal_district or None,
            )
        )
    return tuple(result)


def best_region_match(value: str | None, regions: tuple[RegionEntry, ...]) -> RegionEntry | None:
    key = region_key(value)
    if not key or not regions:
        return None
    candidates: list[tuple[int, RegionEntry]] = []
    for region in regions:
        for variant in _region_variants(region):
            variant_key = region_key(variant)
            if not variant_key:
                continue
            score = _score_region_key(key, variant_key)
            candidates.append((score, region))
    if not candidates:
        return None
    score, region = max(candidates, key=lambda item: (item[0], len(item[1].display_name)))
    return region if score >= 76 else None


def region_key(value: str | None) -> str:
    text = str(value or "").lower().replace("ё", "е")
    text = text.replace("—", "-").replace("–", "-")
    text = re.sub(r"\bмуниципальные\s+образования\b", " ", text)
    text = re.sub(r"\bнаселенные\s+пункты,?\s+входящие\s+в\s+состав\s+муниципальных\s+образований\b", " ", text)
    text = re.sub(r"\bгорода\s+федерального\s+значения\b", "город федерального значения", text)
    text = re.sub(r"\bобласти\b", "область", text)
    text = re.sub(r"\bкрая\b", "край", text)
    text = re.sub(r"\bреспублики\b", "республика", text)
    text = re.sub(r"\bавтономного\s+округа\b", "автономный округ", text)
    text = re.sub(r"\bавтономной\s+области\b", "автономная область", text)
    words = []
    for word in re.findall(r"[0-9a-zа-я-]+", text):
        words.append(_genitive_adjective_to_nominative(word))
    return " ".join(words)


def _region_variants(region: RegionEntry) -> tuple[str, ...]:
    return (
        region.display_name,
        region.short_name,
        *region.aliases,
        region.display_name.replace("(", "").replace(")", ""),
    )


def _score_region_key(left: str, right: str) -> int:
    if left == right:
        return 100
    left_words = set(left.split())
    right_words = set(right.split())
    left_types = left_words & _SUBJECT_TYPE_WORDS
    right_types = right_words & _SUBJECT_TYPE_WORDS
    if left_types and right_types and left_types.isdisjoint(right_types):
        return 0
    try:
        from rapidfuzz import fuzz

        score = int(fuzz.token_sort_ratio(left, right))
        if not left_types and not right_types:
            score = max(score, int(fuzz.partial_ratio(left, right)))
        return score
    except ImportError:
        if not left_words or not right_words:
            return 0
        return int(100 * len(left_words & right_words) / len(left_words | right_words))


def _genitive_adjective_to_nominative(value: str) -> str:
    replacements = (
        ("ской", "ская"),
        ("цкой", "цкая"),
        ("ского", "ский"),
        ("цкого", "цкий"),
        ("кого", "кий"),
        ("ого", "ый"),
        ("его", "ий"),
        ("ой", "ая"),
    )
    for old, new in replacements:
        if value.endswith(old) and len(value) > len(old) + 2:
            return value[: -len(old)] + new
    return value
