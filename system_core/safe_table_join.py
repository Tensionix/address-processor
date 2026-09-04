from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
import re
import shutil
from typing import Callable, Iterable

from system_core.excel_layout import format_excel_worksheet


_SPACE_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^0-9a-zа-яё]+", re.IGNORECASE)
_PREMISE_RE = re.compile(r"\b(?:кв(?:артира)?|kom|ком(?:ната)?|пом(?:ещение)?)[.\s№-]*\d+.*$", re.IGNORECASE)


@dataclass(frozen=True)
class JoinOptions:
    primary_file: Path
    source_file: Path
    output_file: Path
    primary_sheet: str
    source_sheets: tuple[str, ...]
    primary_start_row: int
    source_start_row: int
    primary_address_columns: tuple[int, ...]
    source_address_columns: tuple[int, ...]
    source_payload_columns: tuple[int, ...]
    output_header_row: int
    audit_sheet: str = "AUDIT_ADDRESS_JOIN"


@dataclass(frozen=True)
class ComparisonOptions:
    file_a: Path
    file_b: Path
    output_file: Path
    sheet_a: str
    sheet_b: str
    start_row_a: int
    start_row_b: int
    address_columns_a: tuple[int, ...]
    address_columns_b: tuple[int, ...]
    sort_addresses: bool = False


_ADDRESS_HEADER_PATTERNS = {
    "address": re.compile(r"\b(?:адрес|местополож|локац)", re.IGNORECASE),
    "street": re.compile(r"\b(?:улиц|переул|проспект|проезд|название\s+ул)", re.IGNORECASE),
    "house": re.compile(r"(?:№|\bномер)\s*дома|\bдом\b", re.IGNORECASE),
    "modifier": re.compile(r"\b(?:корпус|литера?|строение|владение)\b", re.IGNORECASE),
}


def detect_address_columns(
    matrix: tuple[tuple[object, ...], ...], start_row: int, first_excel_column: int = 1
) -> tuple[int, ...]:
    header_rows = matrix[: max(0, start_row - 1)]
    detected: list[tuple[int, str]] = []
    for index in range(len(matrix[0]) if matrix else 0):
        header = " ".join(str(row[index] or "").strip() for row in header_rows if str(row[index] or "").strip())
        kinds = [kind for kind, pattern in _ADDRESS_HEADER_PATTERNS.items() if pattern.search(header)]
        if kinds:
            detected.append((first_excel_column + index, kinds[0]))
    if not detected:
        raise ValueError("Could not auto-detect address columns from the worksheet headers; specify them manually.")
    address_columns = [column for column, kind in detected if kind == "address"]
    component_columns = [column for column, kind in detected if kind in {"street", "house", "modifier"}]
    if component_columns:
        return tuple(sorted(dict.fromkeys([*address_columns, *component_columns])))
    return (address_columns[0],)


def parse_column_spec(value: object) -> tuple[int, ...]:
    result: list[int] = []
    for token in re.split(r"[,;\s]+", str(value or "").strip()):
        if not token:
            continue
        if token.isdigit():
            index = int(token)
        else:
            index = 0
            for char in token.upper():
                if not "A" <= char <= "Z":
                    raise ValueError(f"Invalid Excel column: {token}")
                index = index * 26 + ord(char) - 64
        if index < 1:
            raise ValueError(f"Invalid Excel column: {token}")
        if index not in result:
            result.append(index)
    if not result:
        raise ValueError("At least one Excel column is required.")
    return tuple(result)


def normalized_building_key(parts: Iterable[object]) -> str:
    text = " ".join(str(value).strip() for value in parts if value not in (None, ""))
    text = text.lower().replace("ё", "е")
    text = _PREMISE_RE.sub("", text)
    text = re.sub(r"\b(?:г(?:ород)?|ул(?:ица)?|пер(?:еулок)?|пр-кт|проспект|д(?:ом)?|корп(?:ус)?|стр(?:оение)?)\.?\s*", " ", text)
    text = _PUNCT_RE.sub(" ", text)
    return _SPACE_RE.sub(" ", text).strip()


def merge_distinct(values: Iterable[object]) -> object:
    items: list[str] = []
    for value in values:
        if value in (None, ""):
            continue
        text = str(value).strip()
        if text and text not in items:
            items.append(text)
    return "\n".join(items)


def _matrix(value: object, rows: int, columns: int) -> tuple[tuple[object, ...], ...]:
    if rows == 1 and columns == 1:
        return ((value,),)
    if rows == 1:
        return (tuple(value),)
    if columns == 1:
        return tuple((item,) for item in value)
    return tuple(tuple(row) for row in value)


def _comparison_headers(matrix: tuple[tuple[object, ...], ...], start_row: int, prefix: str) -> list[str]:
    header_rows = matrix[: max(0, start_row - 1)]
    headers: list[str] = []
    width = len(matrix[0]) if matrix else 0
    for column in range(width):
        pieces: list[str] = []
        for row in header_rows:
            text = str(row[column] or "").strip()
            if text and text not in pieces:
                pieces.append(text)
        label = " / ".join(pieces) or f"Колонка {column + 1}"
        headers.append(f"{prefix}: {label}")
    return headers


def build_comparison_workbook(options: ComparisonOptions, log: Callable[[str], None] | None = None) -> dict[str, object]:
    if not options.file_a.exists() or not options.file_b.exists():
        raise FileNotFoundError("Workbook A or B was not found.")
    options.output_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        import pythoncom
        import win32com.client
    except ImportError as exc:
        raise RuntimeError("Microsoft Excel automation requires pywin32.") from exc

    pythoncom.CoInitialize()
    excel = book_a = book_b = output_book = None
    try:
        excel = win32com.client.DispatchEx("Excel.Application")
        excel.Visible = False
        excel.DisplayAlerts = False
        excel.ScreenUpdating = False
        book_a = excel.Workbooks.Open(str(options.file_a), 0, True)
        book_b = excel.Workbooks.Open(str(options.file_b), 0, True)
        sheet_a = book_a.Worksheets(options.sheet_a)
        sheet_b = book_b.Worksheets(options.sheet_b)
        range_a = sheet_a.UsedRange
        range_b = sheet_b.UsedRange
        data_a = _matrix(range_a.Value2, range_a.Rows.Count, range_a.Columns.Count)
        data_b = _matrix(range_b.Value2, range_b.Rows.Count, range_b.Columns.Count)
        offset_a = range_a.Row - 1
        offset_b = range_b.Row - 1

        columns_a = options.address_columns_a or detect_address_columns(data_a, options.start_row_a - offset_a, range_a.Column)
        columns_b = options.address_columns_b or detect_address_columns(data_b, options.start_row_b - offset_b, range_b.Column)
        if log:
            log(f"Address columns detected/selected: A={columns_a}, B={columns_b}")

        records_b: dict[str, list[tuple[int, tuple[object, ...]]]] = defaultdict(list)
        order_b: list[tuple[str, int, tuple[object, ...]]] = []
        for excel_row in range(options.start_row_b, offset_b + len(data_b) + 1):
            record = data_b[excel_row - offset_b - 1]
            parts = [record[col - range_b.Column] for col in columns_b if range_b.Column <= col < range_b.Column + len(record)]
            key = normalized_building_key(parts)
            if key:
                records_b[key].append((excel_row, record))
                order_b.append((key, excel_row, record))

        matched_rows: list[tuple[object, ...]] = []
        only_a_rows: list[tuple[object, ...]] = []
        only_b_rows: list[tuple[object, ...]] = []
        used_b_rows: set[int] = set()
        matched_a = unmatched_a = ambiguous_a = 0
        blank_b = tuple(None for _ in range(len(data_b[0])))
        blank_a = tuple(None for _ in range(len(data_a[0])))
        for excel_row in range(options.start_row_a, offset_a + len(data_a) + 1):
            record_a = data_a[excel_row - offset_a - 1]
            parts_a = [record_a[col - range_a.Column] for col in columns_a if range_a.Column <= col < range_a.Column + len(record_a)]
            key_a = normalized_building_key(parts_a)
            if not key_a:
                continue
            matches = records_b.get(key_a, [])
            if matches:
                matched_a += 1
                ambiguous_a += int(len(matches) > 1)
                for row_b, record_b in matches:
                    used_b_rows.add(row_b)
                    status = "сопоставлено" if len(matches) == 1 else f"сопоставлено: {len(matches)} строк B"
                    matched_rows.append((status, key_a, key_a, excel_row, row_b, *record_a, *record_b))
            else:
                unmatched_a += 1
                only_a_rows.append(("только A", key_a, None, excel_row, None, *record_a, *blank_b))

        unmatched_b = 0
        for key_b, row_b, record_b in order_b:
            if row_b in used_b_rows:
                continue
            unmatched_b += 1
            only_b_rows.append(("только B", None, key_b, None, row_b, *blank_a, *record_b))

        if options.sort_addresses:
            matched_rows.sort(key=lambda row: (str(row[1] or ""), int(row[3] or 0), int(row[4] or 0)))
            only_a_rows.sort(key=lambda row: (str(row[1] or ""), int(row[3] or 0)))
            only_b_rows.sort(key=lambda row: (str(row[2] or ""), int(row[4] or 0)))
        rows = [*matched_rows, *only_a_rows, *only_b_rows]

        output_book = excel.Workbooks.Add()
        output_sheet = output_book.Worksheets(1)
        output_sheet.Name = "Сравнение"
        headers = ["Статус", "Нормализованный адрес A", "Нормализованный адрес B", "Строка A", "Строка B"]
        headers.extend(_comparison_headers(data_a, options.start_row_a - offset_a, "A"))
        headers.extend(_comparison_headers(data_b, options.start_row_b - offset_b, "B"))
        header_row = 1
        data_start_row = header_row + 1
        first_a_col = 6
        last_a_col = first_a_col + len(data_a[0]) - 1
        first_b_col = last_a_col + 1
        last_b_col = first_b_col + len(data_b[0]) - 1
        dark_neutral = 0x4B3F35
        dark_a = 0x8B4A24
        dark_b = 0x2E75A8
        pale_a = 0xF7EBDD
        pale_b = 0xE8F3FA
        pale_green = 0xE2F0D9
        pale_yellow = 0xFFF2CC
        pale_gray = 0xF2F2F2

        summary_sheet = output_book.Worksheets.Add(After=output_sheet)
        summary_sheet.Name = "Сводка"
        summary_sheet.Range("A1:H1").Merge()
        summary_sheet.Cells(1, 1).Value = "СРАВНЕНИЕ ТАБЛИЦ A И B"
        summary_sheet.Cells(1, 1).Font.Bold = True
        summary_sheet.Cells(1, 1).Font.Size = 14
        summary_sheet.Cells(1, 1).Font.Color = 0xFFFFFF
        summary_sheet.Cells(1, 1).Interior.Color = dark_neutral
        summary_sheet.Cells(3, 1).Value = "Файл A"
        summary_sheet.Cells(3, 2).Value = options.file_a.name
        summary_sheet.Cells(4, 1).Value = "Лист A"
        summary_sheet.Cells(4, 2).Value = options.sheet_a
        summary_sheet.Cells(3, 4).Value = "Файл B"
        summary_sheet.Cells(3, 5).Value = options.file_b.name
        summary_sheet.Cells(4, 4).Value = "Лист B"
        summary_sheet.Cells(4, 5).Value = options.sheet_b
        stats = (("Сопоставлено A", matched_a), ("Несколько строк B", ambiguous_a), ("Только A", unmatched_a), ("Только B", unmatched_b), ("Строк сравнения", len(rows)))
        summary_sheet.Cells(6, 1).Value = "Статистика"
        summary_sheet.Cells(6, 1).Font.Bold = True
        for index, (label, value) in enumerate(stats, start=7):
            summary_sheet.Cells(index, 1).Value = label
            summary_sheet.Cells(index, 2).Value = value
        legend = (("сопоставлено", pale_green), ("несколько строк B", pale_yellow), ("только A / блок A", pale_a), ("только B / блок B", pale_b))
        summary_sheet.Cells(6, 4).Value = "Легенда"
        summary_sheet.Cells(6, 4).Font.Bold = True
        for index, (label, color) in enumerate(legend, start=7):
            summary_sheet.Cells(index, 4).Value = label
            summary_sheet.Cells(index, 4).Interior.Color = color
        summary_sheet.Columns("A:E").AutoFit()

        output_sheet.Range(output_sheet.Cells(header_row, 1), output_sheet.Cells(header_row, len(headers))).Value = (tuple(headers),)
        output_sheet.Range(output_sheet.Cells(header_row, 1), output_sheet.Cells(header_row, len(headers))).Font.Bold = True
        output_sheet.Range(output_sheet.Cells(header_row, 1), output_sheet.Cells(header_row, len(headers))).Font.Color = 0xFFFFFF
        output_sheet.Range(output_sheet.Cells(header_row, 1), output_sheet.Cells(header_row, 5)).Interior.Color = dark_neutral
        output_sheet.Range(output_sheet.Cells(header_row, first_a_col), output_sheet.Cells(header_row, last_a_col)).Interior.Color = dark_a
        output_sheet.Range(output_sheet.Cells(header_row, first_b_col), output_sheet.Cells(header_row, last_b_col)).Interior.Color = dark_b
        output_sheet.Range(output_sheet.Cells(header_row, 1), output_sheet.Cells(header_row, len(headers))).WrapText = True
        for start in range(0, len(rows), 500):
            chunk = tuple(rows[start:start + 500])
            first_row = data_start_row + start
            output_sheet.Range(output_sheet.Cells(first_row, 1), output_sheet.Cells(first_row + len(chunk) - 1, len(headers))).Value = chunk
        last_data_row = data_start_row + len(rows) - 1
        output_sheet.Range(output_sheet.Cells(data_start_row, 2), output_sheet.Cells(last_data_row, 2)).Interior.Color = pale_a
        output_sheet.Range(output_sheet.Cells(data_start_row, 3), output_sheet.Cells(last_data_row, 3)).Interior.Color = pale_b
        output_sheet.Range(output_sheet.Cells(data_start_row, 4), output_sheet.Cells(last_data_row, 4)).Interior.Color = pale_a
        output_sheet.Range(output_sheet.Cells(data_start_row, 5), output_sheet.Cells(last_data_row, 5)).Interior.Color = pale_b
        output_sheet.Range(output_sheet.Cells(data_start_row, first_a_col), output_sheet.Cells(last_data_row, last_a_col)).Interior.Color = pale_a
        output_sheet.Range(output_sheet.Cells(data_start_row, first_b_col), output_sheet.Cells(last_data_row, last_b_col)).Interior.Color = pale_b
        for row_index, row in enumerate(rows, start=data_start_row):
            status = str(row[0])
            color = pale_green if status == "сопоставлено" else pale_yellow if status.startswith("сопоставлено:") else pale_a if status == "только A" else pale_b if status == "только B" else pale_gray
            output_sheet.Cells(row_index, 1).Interior.Color = color
        output_sheet.Range(output_sheet.Cells(header_row, 1), output_sheet.Cells(last_data_row, len(headers))).AutoFilter()
        table_range = output_sheet.Range(output_sheet.Cells(header_row, 1), output_sheet.Cells(last_data_row, len(headers)))
        table_range.Borders.LineStyle = 1
        table_range.Borders.Weight = 2
        table_range.Borders.Color = 0xD9D9D9
        output_sheet.Activate()
        output_sheet.Cells(data_start_row, 1).Select()
        output_sheet.Application.ActiveWindow.FreezePanes = True
        output_sheet.Columns(1).ColumnWidth = 24
        output_sheet.Columns(2).ColumnWidth = 36
        output_sheet.Columns(3).ColumnWidth = 36
        output_sheet.Columns(4).ColumnWidth = 12
        output_sheet.Columns(5).ColumnWidth = 12
        output_sheet.Rows(header_row).RowHeight = 45
        output_book.SaveAs(str(options.output_file), 51)
        result = {
            "output": str(options.output_file), "matched_a": matched_a, "ambiguous_a": ambiguous_a,
            "unmatched_a": unmatched_a, "unmatched_b": unmatched_b, "comparison_rows": len(rows),
            "columns_a": len(data_a[0]), "columns_b": len(data_b[0]),
            "address_columns_a": list(columns_a), "address_columns_b": list(columns_b),
            "sort_addresses": options.sort_addresses,
        }
        if log:
            log(f"Comparison workbook: matched A={matched_a}, ambiguous A={ambiguous_a}, only A={unmatched_a}, only B={unmatched_b}, rows={len(rows)}")
        return result
    finally:
        if output_book is not None:
            output_book.Close(False)
        if book_b is not None:
            book_b.Close(False)
        if book_a is not None:
            book_a.Close(False)
        if excel is not None:
            excel.Quit()
        pythoncom.CoUninitialize()


def safe_join_workbooks(options: JoinOptions, log: Callable[[str], None] | None = None) -> dict[str, object]:
    if options.primary_file.suffix.lower() not in {".xlsx", ".xlsm"}:
        raise ValueError("The primary workbook must be XLSX or XLSM so it can be copied safely.")
    if not options.primary_file.exists() or not options.source_file.exists():
        raise FileNotFoundError("Primary or source workbook was not found.")
    options.output_file.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(options.primary_file, options.output_file)

    try:
        import pythoncom
        import win32com.client
    except ImportError as exc:
        raise RuntimeError("Microsoft Excel automation requires pywin32.") from exc

    pythoncom.CoInitialize()
    excel = None
    primary_book = None
    source_book = None
    try:
        excel = win32com.client.DispatchEx("Excel.Application")
        excel.Visible = False
        excel.DisplayAlerts = False
        excel.ScreenUpdating = False
        primary_book = excel.Workbooks.Open(str(options.output_file), 0, False)
        source_book = excel.Workbooks.Open(str(options.source_file), 0, True)
        target_sheet = primary_book.Worksheets(options.primary_sheet)

        source_rows: dict[str, list[tuple[str, tuple[object, ...], str, int]]] = defaultdict(list)
        payload_headers: list[str] = []
        for sheet_name in options.source_sheets:
            sheet = source_book.Worksheets(sheet_name)
            if not payload_headers:
                for column in options.source_payload_columns:
                    header = sheet.Cells(options.source_start_row - 2, column).Text or sheet.Cells(options.source_start_row - 3, column).Text
                    payload_headers.append(str(header or f"Source_{column}").strip())
            last_row = sheet.UsedRange.Row + sheet.UsedRange.Rows.Count - 1
            for row in range(options.source_start_row, last_row + 1):
                address_parts = tuple(sheet.Cells(row, col).Value for col in options.source_address_columns)
                key = normalized_building_key(address_parts)
                if not key:
                    continue
                payload = tuple(sheet.Cells(row, col).Value for col in options.source_payload_columns)
                raw_address = " ".join(str(v).strip() for v in address_parts if v not in (None, ""))
                source_rows[key].append((raw_address, payload, sheet_name, row))

        start_column = target_sheet.UsedRange.Column + target_sheet.UsedRange.Columns.Count
        existing_headers = {str(target_sheet.Cells(options.output_header_row, col).Text).strip() for col in range(1, start_column)}
        final_headers: list[str] = []
        for header in payload_headers:
            candidate = header or "Source_Data"
            if candidate in existing_headers or candidate in final_headers:
                candidate = f"МВК_{candidate}"
            final_headers.append(candidate)
        final_headers.extend(["Статус сопоставления", "Ключ адреса"])
        for offset, header in enumerate(final_headers):
            cell = target_sheet.Cells(options.output_header_row, start_column + offset)
            cell.Value = header
            cell.Font.Bold = True
            cell.WrapText = True

        last_primary_row = target_sheet.UsedRange.Row + target_sheet.UsedRange.Rows.Count - 1
        matched_keys: set[str] = set()
        matched = ambiguous = unmatched_primary = 0
        audit_rows: list[tuple[object, ...]] = []
        for row in range(options.primary_start_row, last_primary_row + 1):
            address_parts = tuple(target_sheet.Cells(row, col).Value for col in options.primary_address_columns)
            key = normalized_building_key(address_parts)
            if not key:
                continue
            candidates = source_rows.get(key, [])
            status = "не найдено"
            if candidates:
                matched_keys.add(key)
                status = "сопоставлено" if len(candidates) == 1 else f"сопоставлено: {len(candidates)} записи"
                matched += 1
                ambiguous += int(len(candidates) > 1)
                for payload_index in range(len(options.source_payload_columns)):
                    target_sheet.Cells(row, start_column + payload_index).Value = merge_distinct(c[1][payload_index] for c in candidates)
                if len(candidates) > 1:
                    audit_rows.append(("multiple_source_rows", key, row, " | ".join(c[0] for c in candidates)))
            else:
                unmatched_primary += 1
            target_sheet.Cells(row, start_column + len(payload_headers)).Value = status
            target_sheet.Cells(row, start_column + len(payload_headers) + 1).Value = key

        unmatched_source = 0
        for key, candidates in source_rows.items():
            if key in matched_keys:
                continue
            unmatched_source += len(candidates)
            for raw_address, _payload, sheet_name, row in candidates:
                audit_rows.append(("source_not_found_in_primary", key, f"{sheet_name}!{row}", raw_address))

        try:
            old_audit = primary_book.Worksheets(options.audit_sheet)
            old_audit.Delete()
        except Exception:
            pass
        audit = primary_book.Worksheets.Add(After=primary_book.Worksheets(primary_book.Worksheets.Count))
        audit.Name = options.audit_sheet
        audit_headers = ("Issue", "Normalized_Key", "Row", "Address")
        for col, value in enumerate(audit_headers, start=1):
            audit.Cells(1, col).Value = value
            audit.Cells(1, col).Font.Bold = True
        for out_row, record in enumerate(audit_rows, start=2):
            for col, value in enumerate(record, start=1):
                audit.Cells(out_row, col).Value = value
        audit.Columns.AutoFit()
        target_sheet.Range(target_sheet.Cells(options.output_header_row, start_column), target_sheet.Cells(last_primary_row, start_column + len(final_headers) - 1)).WrapText = True
        format_excel_worksheet(target_sheet)
        format_excel_worksheet(audit)
        primary_book.Save()
        if log:
            log(f"Safe table join: matched={matched}, ambiguous={ambiguous}, unmatched_primary={unmatched_primary}, unmatched_source={unmatched_source}")
        return {
            "output": str(options.output_file), "matched": matched, "ambiguous": ambiguous,
            "unmatched_primary": unmatched_primary, "unmatched_source": unmatched_source,
            "source_keys": len(source_rows), "added_columns": len(final_headers),
            "layout_applied_paths": [str(options.output_file)],
        }
    finally:
        if source_book is not None:
            source_book.Close(False)
        if primary_book is not None:
            primary_book.Close(False)
        if excel is not None:
            excel.Quit()
        pythoncom.CoUninitialize()
