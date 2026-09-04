from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any
import re


def ordered_slot_ids(
    *,
    enabled_slots: Iterable[str],
    slot_order: Iterable[str],
    slot_columns: Mapping[str, str],
    default_slot_order: Iterable[str] = (),
) -> tuple[str, ...]:
    enabled = set(enabled_slots)
    ordered: list[str] = []
    for slot in slot_order:
        if slot in enabled and slot in slot_columns and slot not in ordered:
            ordered.append(slot)
    for slot in default_slot_order:
        if slot in enabled and slot in slot_columns and slot not in ordered:
            ordered.append(slot)
    for slot in enabled_slots:
        if slot in slot_columns and slot not in ordered:
            ordered.append(slot)
    return tuple(ordered)


def build_slot_fill_summary(
    rows: Iterable[Any],
    *,
    enabled_slots: tuple[str, ...],
    slot_order: tuple[str, ...],
    slot_columns: Mapping[str, str],
    default_slot_order: Iterable[str] = (),
    slot_labels: Mapping[str, str] | None = None,
    get_slot_value: Callable[[Any, str], Any],
    get_normalized: Callable[[Any], Any] | None = None,
    is_empty_row: Callable[[Any], bool] | None = None,
) -> dict[str, Any]:
    row_items = list(rows)
    slot_ids = ordered_slot_ids(
        enabled_slots=enabled_slots,
        slot_order=slot_order,
        slot_columns=slot_columns,
        default_slot_order=default_slot_order,
    )
    labels = slot_labels or {}
    slot_stats: dict[str, dict[str, Any]] = {
        slot: {
            "column": slot_columns[slot],
            "header": labels.get(slot, slot_columns[slot]),
            "filled": 0,
            "fill_rate": 0.0,
            "samples": [],
        }
        for slot in slot_ids
    }
    empty_rows = 0
    complete_rows = 0
    incomplete_rows = 0
    rows_with_any_selected_slot = 0
    incomplete_examples: list[dict[str, Any]] = []

    for row in row_items:
        if is_empty_row and is_empty_row(row):
            empty_rows += 1
            continue
        missing_slots: list[str] = []
        filled_in_row = 0
        for slot in slot_ids:
            value = _clean(get_slot_value(row, slot))
            if value:
                filled_in_row += 1
                stat = slot_stats[slot]
                stat["filled"] += 1
                samples = stat["samples"]
                if len(samples) < 5 and value not in samples:
                    samples.append(value)
            else:
                missing_slots.append(slot)

        if filled_in_row:
            rows_with_any_selected_slot += 1
        if slot_ids and not missing_slots:
            complete_rows += 1
        elif slot_ids:
            incomplete_rows += 1
            if len(incomplete_examples) < 5:
                incomplete_examples.append(
                    {
                        "normalized": _clean(get_normalized(row)) if get_normalized else None,
                        "missing_slots": missing_slots,
                    }
                )

    records_total = len(row_items) - empty_rows
    denominator = records_total or 1
    for stat in slot_stats.values():
        stat["fill_rate"] = round(float(stat["filled"]) / denominator, 4)

    return {
        "rows_total": len(row_items),
        "records_total": records_total,
        "empty_rows": empty_rows,
        "selected_slots": list(slot_ids),
        "complete_rows": complete_rows,
        "incomplete_rows": incomplete_rows,
        "rows_with_any_selected_slot": rows_with_any_selected_slot,
        "incomplete_examples": incomplete_examples,
        "slots": slot_stats,
    }


def _clean(value: Any) -> str | None:
    if isinstance(value, (list, tuple, set, frozenset)):
        value = ", ".join(str(item) for item in value if str(item).strip())
    text = re.sub(r"\s+", " ", str(value or "").replace("\xa0", " ")).strip(" ,;")
    if not text or text.lower() == "nan":
        return None
    return text
