from __future__ import annotations

from functools import lru_cache
from typing import Any
import re


CYRILLIC_WORD_RE = re.compile(r"^[а-яё-]+$", re.IGNORECASE)
PHRASE_TOKEN_RE = re.compile(r"[а-яё-]+", re.IGNORECASE)
RUSSIAN_CASES = ("nomn", "gent", "datv", "accs", "ablt", "loct")
SERVICE_TYPE_LEMMAS = {
    "автономный",
    "город",
    "городской",
    "край",
    "муниципальный",
    "область",
    "образование",
    "округ",
    "район",
    "республика",
    "село",
    "сельсовет",
    "поселение",
    "поселок",
}


def _clean_token(value: Any) -> str:
    token = str(value or "").strip().lower().replace("ё", "е")
    token = re.sub(r"[^0-9a-zа-я-]+", "", token)
    return token


@lru_cache(maxsize=1)
def _load_analyzer() -> tuple[str, Any] | None:
    try:
        import pymorphy3  # type: ignore

        try:
            return "pymorphy3", pymorphy3.MorphAnalyzer(lang="ru")
        except TypeError:
            return "pymorphy3", pymorphy3.MorphAnalyzer()
    except Exception:
        pass
    try:
        import pymorphy2  # type: ignore

        return "pymorphy2", pymorphy2.MorphAnalyzer()
    except Exception:
        return None


@lru_cache(maxsize=100_000)
def lemmatize_word(value: Any) -> str:
    token = _clean_token(value)
    if not token or not CYRILLIC_WORD_RE.fullmatch(token):
        return token
    loaded = _load_analyzer()
    if loaded is None:
        return token
    _, analyzer = loaded
    try:
        parsed = analyzer.parse(token)
    except Exception:
        return token
    if not parsed:
        return token
    normal = _clean_token(getattr(parsed[0], "normal_form", "") or token)
    return normal or token


@lru_cache(maxsize=100_000)
def inflect_word_cases(value: Any) -> tuple[str, ...]:
    token = _clean_token(value)
    if not token or not CYRILLIC_WORD_RE.fullmatch(token):
        return (token,) if token else ()
    loaded = _load_analyzer()
    if loaded is None:
        return (token,)
    _, analyzer = loaded
    try:
        parsed = analyzer.parse(token)
    except Exception:
        return (token,)
    if not parsed:
        return (token,)

    forms: list[str] = []
    seen: set[str] = set()
    for parse in parsed[:2]:
        for case in RUSSIAN_CASES:
            try:
                inflected = parse.inflect({case})
            except Exception:
                inflected = None
            word = _clean_token(getattr(inflected, "word", "") if inflected else "")
            if word and word not in seen:
                seen.add(word)
                forms.append(word)
    if token and token not in seen:
        forms.insert(0, token)
    return tuple(forms)


def phrase_case_forms(value: Any) -> list[str]:
    text = re.sub(r"\s+", " ", str(value or "").replace("\xa0", " ")).strip(" ,;")
    if not text:
        return []
    tokens = PHRASE_TOKEN_RE.findall(text)
    if len(tokens) != 1:
        return [text]
    token = tokens[0]
    return [_title_like(form, token) for form in inflect_word_cases(token) if form]


def phrase_lemmas(value: Any) -> list[str]:
    text = re.sub(r"\s+", " ", str(value or "").replace("\xa0", " ")).strip(" ,;")
    if not text:
        return []
    lemmas = [lemmatize_word(token) for token in PHRASE_TOKEN_RE.findall(text)]
    lemmas = [lemma for lemma in lemmas if lemma and lemma not in SERVICE_TYPE_LEMMAS]
    return [" ".join(lemmas)] if lemmas else []


def morphology_status() -> dict[str, Any]:
    loaded = _load_analyzer()
    if loaded is None:
        return {"available": False, "engine": ""}
    return {"available": True, "engine": loaded[0]}


def _title_like(value: str, sample: str) -> str:
    if sample[:1].isupper():
        return "-".join(part[:1].upper() + part[1:] for part in value.split("-") if part)
    return value
