from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
import csv
import re
import xml.etree.ElementTree as ET
import zipfile

import pandas as pd

from .source_cleanup import is_office_temp_file
from .audion_address_core import looks_like_address_text, parse_address_components


SUPPORTED_SOURCE_SUFFIXES = {".xlsx", ".docx", ".odt", ".txt", ".csv", ".md", ".markdown", ".pdf"}
LEGACY_OFFICE_SUFFIXES = {".doc", ".xls"}
WORD_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
ODT_NS = {
    "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
}
ODT_REPEAT_ATTR = f"{{{ODT_NS['table']}}}number-columns-repeated"
REFERENCE_HEADER_SCORES = {
    "normalizedaddress": 280.0,
    "normalizedadress": 280.0,
    "нормализованныйадрес": 280.0,
    "нормализованныиадрес": 280.0,
    "эталонныйадрес": 260.0,
    "эталонныиадрес": 260.0,
    "адресэталон": 250.0,
    "referenceaddress": 250.0,
    "groundtruth": 240.0,
    "gt": 220.0,
    "rawaddress": 170.0,
    "исходныйадрес": 160.0,
    "исходныиадрес": 160.0,
    "адрес": 120.0,
}
REFERENCE_HELPER_HEADERS = {
    "postalindex",
    "индекс",
    "oktmo",
    "oktmocode",
    "oktmoname",
    "октмо",
    "кодоктмо",
    "municipality",
    "муниципалитет",
    "locality",
    "населенныйпункт",
    "населенныипункт",
    "street",
    "улица",
    "house",
    "дом",
    "matchkey",
    "ключсопоставления",
    "sourcecount",
    "sources",
    "rawexamples",
}
ADDRESS_MARKER_RE = re.compile(
    r"\b(?:ул\.?|улица|пер\.?|переулок|пр-?кт|проспект|д\.?|дом|с\.?|село|д\.?|деревня|"
    r"п\.?|пос\.?|поселок|посёлок|пгт|рп|город|г\.?|тер\.?|снт|днт|тсн)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SourceCandidate:
    value: str
    source_file: Path
    source_kind: str
    locator: str


@dataclass(frozen=True)
class ReferenceColumnChoice:
    column_index: int
    data_start_row: int
    score: float
    label: str
    source: str


@dataclass(frozen=True)
class ReferenceColumnSelection:
    indices: frozenset[int]
    data_start_row: int
    source: str


def discover_source_files(folder: Path) -> list[Path]:
    return sorted(
        path
        for path in folder.rglob("*")
        if path.is_file()
        and not is_office_temp_file(path)
        and path.suffix.lower() in SUPPORTED_SOURCE_SUFFIXES
    )


def discover_legacy_office_files(folder: Path) -> list[Path]:
    return sorted(
        path
        for path in folder.rglob("*")
        if path.is_file()
        and not is_office_temp_file(path)
        and path.suffix.lower() in LEGACY_OFFICE_SUFFIXES
    )


def extract_source_candidates(
    path: Path,
    *,
    source_columns: str | None = None,
) -> tuple[list[SourceCandidate], list[str]]:
    suffix = path.suffix.lower()
    try:
        if suffix == ".xlsx":
            return _extract_xlsx_candidates(path, source_columns=source_columns), []
        if suffix == ".docx":
            return _extract_docx_candidates(path), []
        if suffix == ".odt":
            return _extract_odt_candidates(path), []
        if suffix in {".txt", ".csv", ".md", ".markdown"}:
            return _extract_text_candidates(path), []
        if suffix == ".pdf":
            return _extract_pdf_candidates(path), []
    except Exception as exc:
        return [], [f"{path.name}: {exc}"]
    return [], [f"{path.name}: unsupported source type"]


def extract_reference_candidates(
    path: Path,
    *,
    reference_columns: str | None = None,
) -> tuple[list[SourceCandidate], list[str]]:
    suffix = path.suffix.lower()
    try:
        if suffix == ".xlsx":
            return _extract_reference_xlsx_candidates(path, reference_columns=reference_columns), []
    except Exception as exc:
        return [], [f"{path.name}: {exc}"]
    return extract_source_candidates(path, source_columns=reference_columns)


def _extract_xlsx_candidates(path: Path, *, source_columns: str | None) -> list[SourceCandidate]:
    workbook = pd.read_excel(path, sheet_name=None, header=None, dtype=object)
    candidates: list[SourceCandidate] = []
    for sheet_name, frame in workbook.items():
        if frame.empty:
            continue
        selected = _selected_column_indices(source_columns, frame)
        for row_index, row in frame.iterrows():
            for col_index, value in row.items():
                if selected is not None and int(col_index) not in selected:
                    continue
                text = _clean(value)
                if not text:
                    continue
                candidates.append(
                    SourceCandidate(
                        value=text,
                        source_file=path,
                        source_kind="xlsx_cell",
                        locator=f"{sheet_name}!{excel_column_letter(int(col_index))}{int(row_index) + 1}",
                    )
                )
    return candidates


def _extract_reference_xlsx_candidates(path: Path, *, reference_columns: str | None) -> list[SourceCandidate]:
    workbook = pd.read_excel(path, sheet_name=None, header=None, dtype=object)
    candidates: list[SourceCandidate] = []
    for sheet_name, frame in workbook.items():
        if frame.empty:
            continue
        selection = _reference_column_selection(reference_columns, frame)
        selected = selection.indices if selection else set(range(len(frame.columns)))
        data_start_row = selection.data_start_row if selection else 0
        for row_index in range(data_start_row, len(frame)):
            for col_index in sorted(selected):
                text = _clean(frame.iat[row_index, col_index])
                if not text:
                    continue
                candidates.append(
                    SourceCandidate(
                        value=text,
                        source_file=path,
                        source_kind=f"xlsx_reference_{selection.source if selection else 'all_columns'}",
                        locator=f"{sheet_name}!{excel_column_letter(col_index)}{row_index + 1}",
                    )
                )
    return candidates


def _reference_column_selection(value: str | None, frame: pd.DataFrame) -> ReferenceColumnSelection | None:
    manual = _manual_reference_column_selection(value, frame)
    if manual:
        return manual
    choice = detect_reference_column(frame)
    if not choice:
        return None
    return ReferenceColumnSelection(
        indices=frozenset({choice.column_index}),
        data_start_row=choice.data_start_row,
        source="auto_column",
    )


def _manual_reference_column_selection(value: str | None, frame: pd.DataFrame) -> ReferenceColumnSelection | None:
    tokens = [part.strip() for part in str(value or "").split(",") if part.strip()]
    if not tokens:
        return None
    indices: list[int] = []
    data_start_row = 0
    for token in tokens:
        index, header_row = _resolve_reference_column_token(token, frame)
        if index not in indices:
            indices.append(index)
        if header_row is not None:
            data_start_row = max(data_start_row, header_row + 1)
    return ReferenceColumnSelection(indices=frozenset(indices), data_start_row=data_start_row, source="manual_column")


def _resolve_reference_column_token(token: str, frame: pd.DataFrame) -> tuple[int, int | None]:
    text = str(token).strip()
    if text.isdigit():
        index = int(text) - 1
        return _validate_column_index(index, frame, token), None
    if re.fullmatch(r"[A-Za-z]{1,3}", text):
        index = excel_column_index(text)
        if 0 <= index < len(frame.columns):
            return index, None
    header_match = _find_header_column(text, frame)
    if header_match:
        return header_match
    raise ValueError(f"Reference column {token!r} was not found by letter, number, or header name.")


def _find_header_column(token: str, frame: pd.DataFrame) -> tuple[int, int] | None:
    needle = _header_key(token)
    if not needle:
        return None
    search_rows = min(20, len(frame))
    for row_index in range(search_rows):
        for col_index in range(len(frame.columns)):
            value = _clean(frame.iat[row_index, col_index])
            key = _header_key(value)
            if key and (key == needle or needle in key or key in needle):
                return col_index, row_index
    return None


def _validate_column_index(index: int, frame: pd.DataFrame, token: object) -> int:
    if index < 0 or index >= len(frame.columns):
        max_col = excel_column_letter(len(frame.columns) - 1) if len(frame.columns) else "A"
        raise ValueError(f"Column {token!r} is outside workbook width A:{max_col}.")
    return index


def detect_reference_column(frame: pd.DataFrame) -> ReferenceColumnChoice | None:
    if frame.empty or len(frame.columns) == 0:
        return None
    best: ReferenceColumnChoice | None = None
    for col_index in range(len(frame.columns)):
        header_score, header_row, header_label = _reference_header_score(frame, col_index)
        data_start_row = header_row + 1 if header_row is not None and header_score > 0 else 0
        value_score, metrics = _reference_value_score(frame, col_index, data_start_row)
        position_bonus = max(0.0, 8.0 - col_index * 0.75)
        score = header_score + value_score + position_bonus
        choice = ReferenceColumnChoice(
            column_index=col_index,
            data_start_row=data_start_row,
            score=score,
            label=header_label or excel_column_letter(col_index),
            source=(
                f"auto:fill={metrics['fill_ratio']:.1%};"
                f"address={metrics['address_ratio']:.1%};"
                f"score={score:.1f}"
            ),
        )
        if best is None or choice.score > best.score:
            best = choice
    return best


def _reference_header_score(frame: pd.DataFrame, col_index: int) -> tuple[float, int | None, str | None]:
    best_score = 0.0
    best_row: int | None = None
    best_label: str | None = None
    for row_index in range(min(12, len(frame))):
        label = _clean(frame.iat[row_index, col_index])
        key = _header_key(label)
        if not key:
            continue
        score = REFERENCE_HEADER_SCORES.get(key, 0.0)
        if not score:
            for header_key, header_score in REFERENCE_HEADER_SCORES.items():
                if header_key != "адрес" and (header_key in key or key in header_key):
                    score = max(score, header_score - 20.0)
        if key in REFERENCE_HELPER_HEADERS or any(helper in key for helper in REFERENCE_HELPER_HEADERS if len(helper) > 4):
            score -= 180.0
        if score > best_score:
            best_score = score
            best_row = row_index
            best_label = label
    return best_score, best_row, best_label


def _reference_value_score(frame: pd.DataFrame, col_index: int, data_start_row: int) -> tuple[float, dict[str, float]]:
    if data_start_row >= len(frame):
        return -1000.0, _empty_reference_metrics()
    series = frame.iloc[data_start_row:, col_index].dropna().astype(str).str.strip()
    values = series[series != ""]
    if values.empty:
        return -1000.0, _empty_reference_metrics()
    row_count = max(1, len(frame) - data_start_row)
    non_empty_count = len(values)
    fill_ratio = non_empty_count / row_count
    sample = values if non_empty_count <= 3000 else values.iloc[:: max(1, non_empty_count // 3000)]
    parsed = [parse_address_components(value) for value in sample]
    address_ratio = sum(1 for territory, street_words, _street_numbers, house_base, _house_mods in parsed if street_words or house_base or territory) / len(parsed)
    house_ratio = sum(1 for _territory, _street_words, _street_numbers, house_base, _house_mods in parsed if house_base) / len(parsed)
    street_ratio = sum(1 for _territory, street_words, _street_numbers, _house_base, _house_mods in parsed if street_words) / len(parsed)
    marker_ratio = sum(1 for value in sample if looks_like_address_text(value) or ADDRESS_MARKER_RE.search(str(value))) / len(sample)
    numeric_ratio = sample.str.match(r"^\d+\.?\d*$").sum() / len(sample)
    avg_len = float(sample.str.len().mean())
    score = (
        fill_ratio * 120.0
        + address_ratio * 80.0
        + house_ratio * 26.0
        + street_ratio * 20.0
        + marker_ratio * 16.0
        + min(avg_len, 110.0) * 0.12
        - numeric_ratio * 140.0
    )
    if fill_ratio >= 0.90 and address_ratio >= 0.55:
        score += 35.0
    if avg_len < 8:
        score -= 35.0
    return score, {
        "fill_ratio": fill_ratio,
        "address_ratio": address_ratio,
        "house_ratio": house_ratio,
        "street_ratio": street_ratio,
        "marker_ratio": marker_ratio,
        "numeric_ratio": numeric_ratio,
        "avg_len": avg_len,
    }


def _empty_reference_metrics() -> dict[str, float]:
    return {
        "fill_ratio": 0.0,
        "address_ratio": 0.0,
        "house_ratio": 0.0,
        "street_ratio": 0.0,
        "marker_ratio": 0.0,
        "numeric_ratio": 0.0,
        "avg_len": 0.0,
    }


def _header_key(value: str | None) -> str:
    text = str(value or "").lower().replace("ё", "е")
    text = text.replace("_", " ")
    text = re.sub(r"[^0-9a-zа-я]+", " ", text)
    text = re.sub(r"\b(?:column|колонка|столбец|поле)\b", " ", text)
    return re.sub(r"\s+", "", text).strip()


def _extract_text_candidates(path: Path) -> list[SourceCandidate]:
    text = _read_text_payload(path)
    candidates: list[SourceCandidate] = []
    suffix = path.suffix.lower().lstrip(".") or "txt"
    for line_number, raw_line in enumerate(text.replace("\r\n", "\n").replace("\r", "\n").split("\n"), start=1):
        line = _clean(raw_line)
        if not line:
            continue
        cells = _split_text_table_line(line, suffix=suffix)
        if len(cells) > 1:
            for index, cell in enumerate(cells, start=1):
                if cell:
                    candidates.append(
                        SourceCandidate(
                            value=cell,
                            source_file=path,
                            source_kind=f"{suffix}_cell",
                            locator=f"L{line_number}:C{index}",
                        )
                    )
        candidates.append(
            SourceCandidate(
                value=line,
                source_file=path,
                source_kind=f"{suffix}_line",
                locator=f"L{line_number}",
            )
        )
    return candidates


def _extract_docx_candidates(path: Path) -> list[SourceCandidate]:
    with zipfile.ZipFile(path) as archive:
        xml_bytes = archive.read("word/document.xml")
    root = ET.fromstring(xml_bytes)
    candidates: list[SourceCandidate] = []

    for row_index, row in enumerate(root.findall(".//w:tbl//w:tr", WORD_NS), start=1):
        cells = [_clean(_docx_node_text(cell)) for cell in row.findall("./w:tc", WORD_NS)]
        for col_index, cell in enumerate(cells, start=1):
            if cell:
                candidates.append(
                    SourceCandidate(
                        value=cell,
                        source_file=path,
                        source_kind="docx_table_cell",
                        locator=f"T{row_index}:C{col_index}",
                    )
                )
        row_text = _clean(" | ".join(cell for cell in cells if cell))
        if row_text:
            candidates.append(
                SourceCandidate(
                    value=row_text,
                    source_file=path,
                    source_kind="docx_table_row",
                    locator=f"T{row_index}",
                )
            )

    body = root.find("w:body", WORD_NS)
    if body is not None:
        paragraph_index = 0
        for child in list(body):
            if _local_name(child.tag) != "p":
                continue
            text = _clean(_docx_node_text(child))
            if not text:
                continue
            paragraph_index += 1
            candidates.append(
                SourceCandidate(
                    value=text,
                    source_file=path,
                    source_kind="docx_paragraph",
                    locator=f"P{paragraph_index}",
                )
            )
    return candidates


def _extract_odt_candidates(path: Path) -> list[SourceCandidate]:
    with zipfile.ZipFile(path) as archive:
        xml_bytes = archive.read("content.xml")
    root = ET.fromstring(xml_bytes)
    candidates: list[SourceCandidate] = []

    for row_index, row in enumerate(root.findall(".//table:table-row", ODT_NS), start=1):
        cells = _odt_row_cells(row)
        for col_index, cell in enumerate(cells, start=1):
            if cell:
                candidates.append(
                    SourceCandidate(
                        value=cell,
                        source_file=path,
                        source_kind="odt_table_cell",
                        locator=f"T{row_index}:C{col_index}",
                    )
                )
        row_text = _clean(" | ".join(cell for cell in cells if cell))
        if row_text:
            candidates.append(
                SourceCandidate(
                    value=row_text,
                    source_file=path,
                    source_kind="odt_table_row",
                    locator=f"T{row_index}",
                )
            )

    paragraph_index = 0
    table_ancestor_tags = {"table", "table-row", "table-cell"}
    for paragraph in root.findall(".//text:p", ODT_NS):
        if any(_local_name(parent.tag) in table_ancestor_tags for parent in _iter_parents(root, paragraph)):
            continue
        text = _clean(_xml_node_text(paragraph))
        if not text:
            continue
        paragraph_index += 1
        candidates.append(
            SourceCandidate(
                value=text,
                source_file=path,
                source_kind="odt_paragraph",
                locator=f"P{paragraph_index}",
            )
        )
    return candidates


def _extract_pdf_candidates(path: Path) -> list[SourceCandidate]:
    try:
        import pymupdf  # type: ignore
    except Exception:
        try:
            import fitz as pymupdf  # type: ignore[no-redef]
        except Exception as exc:
            raise RuntimeError("PyMuPDF is required for searchable PDF intake") from exc

    candidates: list[SourceCandidate] = []
    with pymupdf.open(path) as document:
        for page_index, page in enumerate(document, start=1):
            blocks = _extract_pdf_page_blocks(page)
            if not blocks:
                text = _normalize_pdf_text(page.get_text("text", sort=True))
                if text:
                    blocks = _split_text_blocks(text)
            for block_index, block in enumerate(blocks, start=1):
                candidates.append(
                    SourceCandidate(
                        value=block,
                        source_file=path,
                        source_kind="pdf_text_block",
                        locator=f"P{page_index}:B{block_index}",
                    )
                )
    if not candidates:
        raise RuntimeError("PDF has no searchable text layer; OCR or conversion is required.")
    return candidates


def _extract_pdf_page_blocks(page: Any) -> list[str]:
    blocks: list[tuple[float, float, str]] = []
    try:
        raw_blocks = page.get_text("blocks", sort=True)
    except TypeError:
        raw_blocks = page.get_text("blocks")
    for block in raw_blocks or []:
        if len(block) >= 7 and int(block[6]) != 0:
            continue
        text = _normalize_pdf_text(str(block[4] if len(block) >= 5 else ""))
        if not text:
            continue
        blocks.append((float(block[1]), float(block[0]), text))
    blocks.sort(key=lambda item: (item[0], item[1]))
    return [text for _, _, text in blocks]


def _read_text_payload(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp1251", "cp866"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _split_text_table_line(line: str, *, suffix: str) -> list[str]:
    stripped = line.strip()
    if not stripped:
        return []
    if stripped.startswith("|") and stripped.endswith("|"):
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
    elif "\t" in stripped:
        cells = [cell.strip() for cell in stripped.split("\t")]
    elif ";" in stripped:
        cells = next(csv.reader([stripped], delimiter=";"))
        cells = [cell.strip() for cell in cells]
    elif suffix == "csv" and "," in stripped and stripped.count(",") >= 2:
        cells = next(csv.reader([stripped], delimiter=","))
        cells = [cell.strip() for cell in cells]
    else:
        return [stripped]
    if _is_markdown_separator_row(cells):
        return []
    return [_clean(cell) or "" for cell in cells]


def _is_markdown_separator_row(cells: list[str]) -> bool:
    meaningful = [cell.strip() for cell in cells if cell.strip()]
    return bool(meaningful) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in meaningful)


def _docx_node_text(node: ET.Element) -> str:
    fragments: list[str] = []
    for child in node.iter():
        name = _local_name(child.tag)
        if name == "t":
            fragments.append(child.text or "")
        elif name in {"tab", "br", "cr"}:
            fragments.append(" ")
    return re.sub(r"\s+", " ", "".join(fragments)).strip()


def _odt_row_cells(row: ET.Element) -> list[str]:
    cells: list[str] = []
    for cell in row.findall("./table:table-cell", ODT_NS):
        value = _clean(_xml_node_text(cell)) or ""
        repeat = int(cell.attrib.get(ODT_REPEAT_ATTR, "1") or "1")
        repeat = max(1, min(repeat, 50))
        cells.extend([value] * repeat)
    return cells


def _xml_node_text(node: ET.Element) -> str:
    fragments: list[str] = []
    for child in node.iter():
        if child.text:
            fragments.append(child.text)
        if _local_name(child.tag) in {"tab", "line-break"}:
            fragments.append(" ")
        if child.tail:
            fragments.append(child.tail)
    return re.sub(r"\s+", " ", "".join(fragments)).strip()


def _iter_parents(root: ET.Element, target: ET.Element) -> Iterable[ET.Element]:
    parents: list[ET.Element] = []

    def walk(node: ET.Element, stack: list[ET.Element]) -> bool:
        if node is target:
            parents.extend(stack)
            return True
        for child in list(node):
            if walk(child, [*stack, node]):
                return True
        return False

    walk(root, [])
    return parents


def _normalize_pdf_text(text: str) -> str:
    value = str(text or "").replace("\xa0", " ").replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", value)
    value = re.sub(r"(?m)^[ \t]*\d+[.)]\s+(?=(?:[А-ЯЁA-Z]|\d{2}:))", "", value)
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def _split_text_blocks(text: str) -> list[str]:
    normalized = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    parts = [part.strip() for part in re.split(r"\n\s*\n+", normalized) if part.strip()]
    if parts:
        return parts
    single = re.sub(r"\s+", " ", normalized).strip()
    return [single] if single else []


def _selected_column_indices(value: str | None, df: pd.DataFrame) -> set[int] | None:
    tokens = [part.strip() for part in str(value or "").split(",") if part.strip()]
    if not tokens:
        return None
    result: set[int] = set()
    for token in tokens:
        index = excel_column_index(token) if re.fullmatch(r"[A-Za-z]+", token) else int(token) - 1
        if index < 0 or index >= len(df.columns):
            raise ValueError(f"Column {token!r} is outside workbook width.")
        result.add(index)
    return result


def excel_column_index(value: str) -> int:
    text = str(value).strip().upper()
    if not re.fullmatch(r"[A-Z]+", text):
        raise ValueError(f"Column must be an Excel letter: {value!r}")
    index = 0
    for char in text:
        index = index * 26 + (ord(char) - 64)
    return index - 1


def excel_column_letter(index: int) -> str:
    result = ""
    index = int(index)
    while True:
        result = chr(65 + index % 26) + result
        index = index // 26 - 1
        if index < 0:
            break
    return result


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value).replace("\xa0", " ")).strip(" ,")
    if not text or text.lower() == "nan":
        return None
    return text


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]
