from __future__ import annotations

from copy import copy
from dataclasses import dataclass
from datetime import date, datetime, time
from math import ceil
from pathlib import Path
from typing import Any, Callable, Iterable
import os
import unicodedata

from openpyxl import load_workbook
from openpyxl.cell.cell import MergedCell
from openpyxl.utils import get_column_letter


TARGET_CONTENT_COVERAGE = 0.90
MIN_COLUMN_WIDTH = 9.0
MAX_COLUMN_WIDTH = 48.0
MIN_ROW_HEIGHT = 18.0
MAX_ROW_HEIGHT = 180.0
LINE_HEIGHT = 15.0


@dataclass(frozen=True)
class SheetLayoutResult:
    title: str
    rows: int
    columns: int
    formatted_cells: int


@dataclass(frozen=True)
class WorkbookLayoutResult:
    path: Path
    sheets: tuple[SheetLayoutResult, ...]


def _display_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    if isinstance(value, (date, time)):
        return value.isoformat()
    return str(value)


def _visual_length(text: str) -> int:
    length = 0
    for char in text:
        if char == "\t":
            length += 4
        elif unicodedata.east_asian_width(char) in {"F", "W"}:
            length += 2
        else:
            length += 1
    return length


def _line_lengths(value: object) -> list[int]:
    text = _display_text(value)
    if not text:
        return []
    return [_visual_length(line) for line in text.splitlines() or [text]]


def percentile(values: Iterable[int], coverage: float = TARGET_CONTENT_COVERAGE) -> int:
    ordered = sorted(max(0, int(value)) for value in values)
    if not ordered:
        return 0
    rank = max(0, min(len(ordered) - 1, ceil(len(ordered) * coverage) - 1))
    return ordered[rank]


def _merged_title_cells(sheet: Any) -> set[tuple[int, int]]:
    return {
        (merged.min_row, merged.min_col)
        for merged in sheet.merged_cells.ranges
        if merged.max_col > merged.min_col
    }


def _column_widths(sheet: Any) -> dict[int, float]:
    lengths: dict[int, list[int]] = {}
    merged_titles = _merged_title_cells(sheet)
    for row in sheet.iter_rows(min_row=1, max_row=sheet.max_row, max_col=sheet.max_column):
        for cell in row:
            if isinstance(cell, MergedCell) or (cell.row, cell.column) in merged_titles:
                continue
            cell_lengths = _line_lengths(cell.value)
            if cell_lengths:
                lengths.setdefault(cell.column, []).extend(cell_lengths)

    widths: dict[int, float] = {}
    for column, samples in lengths.items():
        target = percentile(samples)
        widths[column] = min(MAX_COLUMN_WIDTH, max(MIN_COLUMN_WIDTH, float(target + 2)))
    return widths


def _wrapped_line_count(value: object, width: float) -> int:
    lines = _line_lengths(value)
    if not lines:
        return 1
    usable_width = max(1, int(width - 1))
    return max(1, sum(max(1, ceil(length / usable_width)) for length in lines))


def _matrix(value: object, rows: int, columns: int) -> tuple[tuple[object, ...], ...]:
    if rows == 1 and columns == 1:
        return ((value,),)
    if rows == 1:
        return (tuple(value),)
    if columns == 1:
        return tuple((item,) for item in value)
    return tuple(tuple(row) for row in value)


def format_excel_worksheet(sheet: Any) -> SheetLayoutResult:
    """Apply the same layout through live Excel, preserving native workbook features."""
    used = sheet.UsedRange
    row_count = int(used.Rows.Count)
    column_count = int(used.Columns.Count)
    if row_count < 1 or column_count < 1:
        return SheetLayoutResult(str(sheet.Name), 0, 0, 0)
    data = _matrix(used.Value2, row_count, column_count)

    for relative_column in range(column_count):
        samples: list[int] = []
        for row in data:
            if relative_column >= len(row):
                continue
            samples.extend(_line_lengths(row[relative_column]))
        if not samples:
            continue
        width = min(MAX_COLUMN_WIDTH, max(MIN_COLUMN_WIDTH, float(percentile(samples) + 2)))
        used.Columns(relative_column + 1).ColumnWidth = width

    used.WrapText = True
    used.VerticalAlignment = -4160  # xlTop
    used.Rows.AutoFit()
    for relative_row in range(1, row_count + 1):
        row = used.Rows(relative_row)
        if float(row.RowHeight or 0) > MAX_ROW_HEIGHT:
            row.RowHeight = MAX_ROW_HEIGHT
    return SheetLayoutResult(str(sheet.Name), row_count, column_count, row_count * column_count)


def format_worksheet(sheet: Any) -> SheetLayoutResult:
    if sheet.max_row < 1 or sheet.max_column < 1:
        return SheetLayoutResult(sheet.title, 0, 0, 0)

    widths = _column_widths(sheet)
    for column, width in widths.items():
        dimension = sheet.column_dimensions[get_column_letter(column)]
        if not dimension.hidden:
            dimension.width = width

    formatted_cells = 0
    for row in sheet.iter_rows(min_row=1, max_row=sheet.max_row, max_col=sheet.max_column):
        max_lines = 1
        has_content = False
        for cell in row:
            if isinstance(cell, MergedCell) or cell.value is None:
                continue
            has_content = True
            formatted_cells += 1
            alignment = copy(cell.alignment)
            alignment.wrap_text = True
            alignment.shrink_to_fit = False
            if not alignment.vertical:
                alignment.vertical = "top"
            cell.alignment = alignment
            width = widths.get(cell.column, MIN_COLUMN_WIDTH)
            max_lines = max(max_lines, _wrapped_line_count(cell.value, width))
        if has_content and not sheet.row_dimensions[row[0].row].hidden:
            sheet.row_dimensions[row[0].row].height = min(
                MAX_ROW_HEIGHT,
                max(MIN_ROW_HEIGHT, LINE_HEIGHT * max_lines + 3),
            )

    return SheetLayoutResult(
        title=sheet.title,
        rows=sheet.max_row,
        columns=sheet.max_column,
        formatted_cells=formatted_cells,
    )


def format_workbook(path: Path | str) -> WorkbookLayoutResult:
    workbook_path = Path(path).resolve()
    if workbook_path.suffix.lower() not in {".xlsx", ".xlsm"}:
        raise ValueError(f"Unsupported workbook format: {workbook_path.suffix}")
    if not workbook_path.exists():
        raise FileNotFoundError(workbook_path)

    keep_vba = workbook_path.suffix.lower() == ".xlsm"
    workbook = load_workbook(workbook_path, keep_vba=keep_vba)
    temporary_path = workbook_path.with_name(f".{workbook_path.stem}.layout{workbook_path.suffix}")
    try:
        sheets = tuple(format_worksheet(sheet) for sheet in workbook.worksheets)
        workbook.save(temporary_path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
    finally:
        workbook.close()
    os.replace(temporary_path, workbook_path)
    return WorkbookLayoutResult(workbook_path, sheets)


def _artifact_paths(value: object) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, (str, Path)):
        return [str(value)]
    if isinstance(value, dict):
        return _artifact_paths(list(value.values()))
    if isinstance(value, (list, tuple, set, frozenset)):
        paths: list[str] = []
        for item in value:
            paths.extend(_artifact_paths(item))
        return list(dict.fromkeys(paths))
    return [str(value)]


def format_result_workbooks(
    result: dict[str, Any],
    *,
    project_root: Path,
    log: Callable[[str], None] | None = None,
) -> list[WorkbookLayoutResult]:
    artifacts = result.get("artifacts") if isinstance(result.get("artifacts"), dict) else {}
    already_formatted = {
        str(Path(item).resolve())
        for item in _artifact_paths(result.get("layout_applied_paths"))
    }
    candidates = [
        *_artifact_paths(artifacts.get("outputs")),
        *_artifact_paths(artifacts.get("staging")),
    ]
    formatted: list[WorkbookLayoutResult] = []
    for raw_path in dict.fromkeys(candidates):
        path = Path(raw_path)
        if not path.is_absolute():
            path = project_root / path
        if str(path.resolve()) in already_formatted:
            continue
        if path.suffix.lower() not in {".xlsx", ".xlsm"} or not path.exists():
            continue
        try:
            layout = format_workbook(path)
        except Exception as exc:
            if log:
                log(f"Workbook auto-layout skipped for {path}: {exc.__class__.__name__}: {exc}")
            continue
        formatted.append(layout)
        if log:
            cell_count = sum(sheet.formatted_cells for sheet in layout.sheets)
            log(
                f"Workbook auto-layout: {path.name}; "
                f"sheets={len(layout.sheets)}, cells={cell_count}, "
                f"column coverage={TARGET_CONTENT_COVERAGE:.0%}"
            )
    return formatted
