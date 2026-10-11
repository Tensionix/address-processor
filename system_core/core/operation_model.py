"""An operation of the manifest as data: its fields, their defaults, the parameters of a run.

What a window knows about an operation without it being a matter of looks: the default of a field,
whether a field is in sight, where a list of options comes from, and which parameters go to the
service. While the window on NiceGUI held these rules itself (`ui_nicegui/app.py` of 1.9.0), an
operation could be run "as in the window" only from the window. Here is one copy of them - for the
console command (`system_core/cli.py`) and for the window that calls it.

The rules are carried over from that window unchanged; that they give the same parameters for every
operation of the manifest is checked by tests/test_cli_door.py against the record made of that
window (tests/former_window_parameters.json, made by tests/capture_former_window_parameters.py).
"""
from __future__ import annotations

import importlib
import inspect
import json
from pathlib import Path
from typing import Any

from .manifest import CommandNode, Operation, ToolManifest

CHECKBOX_GROUP_KINDS = {"checkboxes", "multi_checkbox", "multicheckbox", "multi-select", "multiselect"}
CHECKBOX_KINDS = {"checkbox", "bool", "boolean", "toggle"}
NUMBER_KINDS = {"number", "int", "integer", "float"}
SLOT_ORDER_KINDS = {"slot_order", "slot-order", "slotorder"}
CHOICE_KINDS = {"radio", "select", "tabs"}
# A widget the window draws for itself: it has no value to send.
UI_ONLY_KINDS = {"oktmo_key_toolbar", "oktmo-key-toolbar"}

# The alignment has two modes. In the fast one the fields of normalization are not in sight and go
# to the service at their defaults.
ALIGNMENT_OPERATION = "run_address_aligner"
ALIGNMENT_MODE_FIELD = "alignment_mode"
ALIGNMENT_NORMALIZATION_GROUP = "alignment_normalization"
ALIGNMENT_NORMALIZATION_FIELDS = {
    "normalize_before_match",
    "normalize_after_match",
    "collect_before_match",
    "collect_whole_document",
    "use_oktmo",
    "oktmo_scope_enabled",
    "oktmo_scope_region",
    "oktmo_scope_municipality",
    "oktmo_key_toolbar",
    "city",
    "subject_ter_hint",
    "municipality_hint",
    "oktmo_data_dir",
}

# One address as the line of the slots: the sample that stands for every slot in the preview.
SLOT_PREVIEW_SAMPLES = {
    "postal_index": "625000",
    "federal_district": "Уральский федеральный округ",
    "parent_subject": "Российская Федерация",
    "subject": "Тюменская область",
    "autonomous_okrug": "Ханты-Мансийский автономный округ — Югра",
    "municipality": "Тюменский муниципальный округ",
    "locality": "г. Тюмень",
    "territory": "территория СНТ Берёзка",
    "microdistrict": "мкр. Центральный",
    "street": "ул. Ленина",
    "house": "д. 10",
    "building": "корп. 2",
    "structure": "стр. 1",
    "apartment": "кв. 15",
    "room": "комн. 3",
}
SLOT_SHORT_LABELS = {
    "ru": {
        "postal_index": "Индекс", "federal_district": "ФО", "parent_subject": "Рег.-род.", "subject": "Субъект",
        "autonomous_okrug": "АО", "municipality": "МО", "locality": "НП", "territory": "Терр.",
        "microdistrict": "Мкр/кв.", "street": "Улица", "house": "Дом", "premise": "Пом.",
        "oktmo_code": "ОКТМО", "oktmo_name": "Имя ОКТМО", "house_base": "№ дома", "house_mods": "Мод. дома",
        "house_modifiers": "Корп./стр.", "street_numbers": "№ улицы", "territory_key": "Ключ терр.", "match_key": "Ключ",
    },
    "en": {
        "postal_index": "Index", "federal_district": "Fed.", "parent_subject": "Parent", "subject": "Subject",
        "autonomous_okrug": "AO", "municipality": "Mun.", "locality": "Locality", "territory": "Terr.",
        "microdistrict": "Mkr/Qtr", "street": "Street", "house": "House", "premise": "Prem.",
        "oktmo_code": "OKTMO", "oktmo_name": "OKTMO name", "house_base": "House no.", "house_mods": "Mods",
        "house_modifiers": "Bldg cols", "street_numbers": "St. nums", "territory_key": "Terr. key", "match_key": "Key",
    },
}


def field_id(field: dict[str, Any]) -> str:
    return str(field.get("id") or field.get("name") or "").strip()


def raw_kind(field: dict[str, Any]) -> str:
    return str(field.get("type", field.get("kind", "text"))).lower()


def is_checkbox_group(field: dict[str, Any]) -> bool:
    return raw_kind(field) in CHECKBOX_GROUP_KINDS


def option_value(option: Any) -> Any:
    if isinstance(option, dict):
        return option.get("value", option.get("id", option.get("label", "")))
    return option


# ---------------------------------------------------------------------------------------------
# The line of the slots: which slots an address is made of and in what order they stand.

def slot_order_options(field: dict[str, Any]) -> list[tuple[str, int]]:
    """The slots a `slot_order` field orders, each with the place the manifest gives it by default."""
    result: list[tuple[str, int]] = []
    options = field.get("options")
    for index, option in enumerate(options if isinstance(options, list) else [], start=1):
        value = str(option_value(option)).strip()
        if not value:
            continue
        try:
            default_order = int(option.get("default_order", index)) if isinstance(option, dict) else index
        except (TypeError, ValueError):
            default_order = index
        result.append((value, max(1, default_order)))
    return result


def slot_order_default(field: dict[str, Any]) -> dict[str, int]:
    configured = field.get("default", {})
    if isinstance(configured, dict):
        result: dict[str, int] = {}
        for key, value in configured.items():
            try:
                result[str(key)] = max(1, int(value))
            except (TypeError, ValueError):
                continue
        if result:
            return result
    return dict(slot_order_options(field))


def normalize_slot_order(field: dict[str, Any], payload: Any) -> dict[str, int]:
    """Every slot gets its own place from 1 to the number of slots: a taken place goes to the next free one."""
    options = slot_order_options(field)
    if not options:
        return {}
    max_order = len(options)
    defaults = dict(options)
    given = payload if isinstance(payload, dict) else {}
    result: dict[str, int] = {}
    used: set[int] = set()

    def coerce_position(raw: Any, fallback: int) -> int:
        try:
            position = int(raw)
        except (TypeError, ValueError):
            position = fallback
        return min(max(1, position), max_order)

    def nearest_free(preferred: int) -> int:
        if preferred not in used:
            return preferred
        for position in range(preferred + 1, max_order + 1):
            if position not in used:
                return position
        for position in range(preferred - 1, 0, -1):
            if position not in used:
                return position
        return preferred

    for slot, default_order in options:
        position = nearest_free(coerce_position(given.get(slot, defaults.get(slot, default_order)), default_order))
        result[slot] = position
        used.add(position)
    return result


def slot_preview(values: dict[str, Any], fallback: str = "") -> str:
    """The address as the slots would write it: the enabled ones, in the order chosen."""
    enabled = values.get("enabled_slots")
    if not isinstance(enabled, list):
        return fallback
    order = values.get("slot_order")
    keys = [key for key in SLOT_PREVIEW_SAMPLES if key in enabled]
    if isinstance(order, dict):
        keys.sort(key=lambda key: (int(order.get(key) or 999), list(SLOT_PREVIEW_SAMPLES).index(key)))
    return " · ".join(SLOT_PREVIEW_SAMPLES[key] for key in keys)


# ---------------------------------------------------------------------------------------------
# Fields: defaults, what is in sight, what goes to the service.

def field_default(field: dict[str, Any]) -> Any:
    """The value a field has before anyone touched it."""
    if "default" in field:
        return field["default"]
    options = field.get("options", [])
    kind = raw_kind(field)
    if kind in SLOT_ORDER_KINDS:
        return slot_order_default(field)
    if kind in CHECKBOX_GROUP_KINDS:
        if not isinstance(options, list):
            return []
        return [option.get("value", option.get("id", option.get("label")))
                for option in options if isinstance(option, dict) and option.get("default", False)]
    if isinstance(options, list) and options:
        first = options[0]
        if isinstance(first, dict):
            return first.get("value", first.get("id", ""))
        return first
    return ""


def form_values(node: CommandNode | Operation, values: dict[str, Any]) -> dict[str, Any]:
    """Every field of the operation with its default, overlaid by what was changed."""
    result = {field_id(field): field_default(field) for field in node.fields if field_id(field)}
    result.update(values)
    return result


def is_ui_only(field: dict[str, Any]) -> bool:
    """A widget with no value of its own (the toolbar of the OKTMO keys): drawn, never sent."""
    return raw_kind(field) in UI_ONLY_KINDS or bool(field.get("ui_only", False))


def is_gui_hidden(field: dict[str, Any]) -> bool:
    """The manifest keeps the field for the service and keeps it out of the form."""
    return bool(field.get("gui_hidden", field.get("hide_in_gui", False)))


def route_of(field: dict[str, Any]) -> str:
    """`source` or `target` when the field names a path the workbench already holds, else ''.

    The window on NiceGUI found such fields by words in their id, label and hint
    (`is_workbench_route_field`): any field that spoke of a folder and of a source or a result was
    left out of the form. The manifest says it now (`route`), and the list of such fields can be read.
    """
    return str(field.get("route") or "").strip().lower()


def depends_on(field: dict[str, Any]) -> list[str]:
    value = field.get("depends_on") or []
    return [value] if isinstance(value, str) else [str(item).strip() for item in value if str(item).strip()]


def dependencies_met(field: dict[str, Any], values: dict[str, Any]) -> bool:
    """`depends_on`: in sight while every field named holds something; `show_when`: while each has its value."""
    for dependency in depends_on(field):
        if str(values.get(dependency) or "").strip().lower() in {"", "0", "false", "none", "null"}:
            return False
    show_when = field.get("show_when")
    if isinstance(show_when, dict):
        for dependency, expected in show_when.items():
            actual = values.get(str(dependency))
            if isinstance(expected, (list, tuple, set)):
                if actual not in expected:
                    return False
            elif actual != expected:
                return False
    return True


def section_of(field: dict[str, Any]) -> str:
    """The block of the form a field stands in: the manifest names it `group`."""
    explicit = str(field.get("group") or field.get("ui_group") or field.get("section_group") or "").strip().lower()
    section = str(field.get("section") or "").strip().lower()
    if not explicit and section and section not in {"advanced", "expert", "rare"}:
        explicit = section
    return explicit or "parameters"


def visible_fields(node: CommandNode | Operation, values: dict[str, Any]) -> list[dict[str, Any]]:
    """The fields of the form in sight for these values: not routed, not hidden, their conditions met."""
    everything = form_values(node, values)
    return [field for field in node.fields
            if field_id(field) and not route_of(field) and not is_gui_hidden(field) and dependencies_met(field, everything)]


# ---------------------------------------------------------------------------------------------
# The alignment: a fast mode and one with normalization.

def alignment_mode(value: Any) -> str:
    mode = str(value or "fast").strip().lower()
    mode = {
        "normalization": "normalized", "normalize": "normalized", "post_normalize": "normalized",
        "post-normalize": "normalized", "alignment_normalization": "normalized", "alignment+normalization": "normalized",
    }.get(mode, mode)
    return "normalized" if mode in {"normalized", "normalised"} else "fast"


def is_alignment_normalization_field(field: dict[str, Any]) -> bool:
    return section_of(field) == ALIGNMENT_NORMALIZATION_GROUP or field_id(field) in ALIGNMENT_NORMALIZATION_FIELDS


def apply_parameter_guards(node: CommandNode | Operation, parameters: dict[str, Any], values: dict[str, Any]) -> dict[str, Any]:
    """The rules of an operation that decide a parameter after the form was read."""
    if node.id != ALIGNMENT_OPERATION:
        return parameters
    mode = alignment_mode(parameters.get(ALIGNMENT_MODE_FIELD))
    parameters[ALIGNMENT_MODE_FIELD] = mode
    if mode == "fast":
        for field in visible_fields(node, values):
            if is_alignment_normalization_field(field):
                parameters[field_id(field)] = field_default(field)
    return parameters


def build_parameters(node: CommandNode | Operation, values: dict[str, Any]) -> dict[str, Any]:
    """The parameters of a run: what the manifest sets, and the fields in sight - the value given or the default.

    The two paths of the workbench are not among them: they go to the service as the folders of the
    project (`input`, `output`), as the window has always sent them.
    """
    parameters = dict(node.parameters)
    for field in visible_fields(node, values):
        if is_ui_only(field):
            continue
        key = field_id(field)
        value = values.get(key, field_default(field))
        if raw_kind(field) in SLOT_ORDER_KINDS:
            # A window orders the slots itself, so each has a place of its own; a command line may not.
            value = normalize_slot_order(field, value)
        parameters[key] = value
    return apply_parameter_guards(node, parameters, values)


def unknown_values(node: CommandNode | Operation, values: dict[str, Any]) -> list[str]:
    """The names of values the operation has no field for: a mistyped name must not vanish quietly."""
    known = {field_id(field) for field in node.fields if field_id(field)}
    return sorted(key for key in values if key not in known)


def short_selections(node: CommandNode | Operation, values: dict[str, Any]) -> list[str]:
    """The groups of checkboxes in sight with fewer ticks than the field asks for (`min_selected`)."""
    everything = form_values(node, values)
    short = []
    for field in visible_fields(node, values):
        if not is_checkbox_group(field):
            continue
        wanted = int(field.get("min_selected", 0) or 0)
        chosen = everything.get(field_id(field))
        if wanted > 0 and (not isinstance(chosen, list) or len(chosen) < wanted):
            short.append(field_id(field))
    return short


def wrong_choices(node: CommandNode | Operation, values: dict[str, Any]) -> list[str]:
    """Values that are none of the options the manifest lists for their field, as "field=value".

    A window cannot give such a value; a command line can. Only a field with its options written in
    the manifest is judged: a list that comes from a provider is not known without asking it.
    """
    wrong = []
    for field in node.fields:
        key = field_id(field)
        options = field.get("options")
        if key not in values or option_source(field) or not isinstance(options, list) or not options:
            continue
        if raw_kind(field) not in CHOICE_KINDS | CHECKBOX_GROUP_KINDS:
            continue
        known = {str(option_value(option)) for option in options}
        given = values[key] if isinstance(values[key], (list, tuple)) else [values[key]]
        wrong.extend(f"{key}={item}" for item in given if str(item) not in known)
    return wrong


def coerce(field: dict[str, Any], text: str) -> Any:
    """A value of the command line (`--set name=value`) in the shape the field expects."""
    kind = raw_kind(field)
    if kind in CHECKBOX_KINDS:
        lowered = text.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off", ""}:
            return False
        raise ValueError("true or false is expected")
    if kind in NUMBER_KINDS:
        number = float(text.replace(",", "."))
        return int(number) if number.is_integer() else number
    if kind in CHECKBOX_GROUP_KINDS:
        return [item.strip() for item in text.split(",") if item.strip()]
    if kind in SLOT_ORDER_KINDS:
        loaded = json.loads(text)
        if not isinstance(loaded, dict):
            raise ValueError('an object like {"street": 1, "house": 2} is expected')
        return loaded
    return text


# ---------------------------------------------------------------------------------------------
# The manifest as a tree of nodes, and the lists of options its fields ask for.

def all_nodes(manifest: ToolManifest):
    """Every node of the manifest: the operations of its groups, then the maintenance ones."""
    def walk(nodes):
        for node in nodes:
            yield node
            yield from walk(node.children)

    yield from walk(manifest.operation_groups)
    yield from manifest.maintenance_operations


def find_node(manifest: ToolManifest, node_id: str) -> CommandNode | Operation | None:
    """An operation of the manifest by its id: a node that has a service to run."""
    for node in all_nodes(manifest):
        if node.id == node_id and node.service:
            return node
    return None


def option_source(field: dict[str, Any]) -> str:
    """Where the options of a field come from when the manifest does not list them: `module:function`."""
    return str(field.get("options_source") or field.get("source") or "").strip()


def resolve_options(source: str, root: Path, values: dict[str, Any], field: dict[str, Any] | None = None) -> list[Any]:
    """Ask a provider for its list: with as many of (root, values, field) as it takes.

    How many arguments it takes is read from its signature before it is called, and it is called
    once: what it raises goes out as it is.
    """
    if ":" not in source:
        raise RuntimeError(f"Dynamic option source must use module:function syntax: {source}")
    module_name, function_name = source.split(":", 1)
    provider = getattr(importlib.import_module(module_name), function_name)
    try:
        count = len(inspect.signature(provider).parameters)
    except (TypeError, ValueError):
        count = 3  # a callable that shows no signature takes the whole of it
    arguments = (root, dict(values), field or {})
    options = provider(*arguments[:count])
    if not isinstance(options, list):
        raise RuntimeError(f"Dynamic option source returned {type(options).__name__}, expected list.")
    return options


def describe_option(option: Any) -> dict[str, Any]:
    """An option of a choice as an object: the manifest and the providers write it either way."""
    if not isinstance(option, dict):
        return {"value": option, "label": str(option)}
    row = dict(option)
    row["value"] = option_value(option)
    row["label"] = str(option.get("label") or option.get("title") or row["value"])
    return row


def describe_field(field: dict[str, Any]) -> dict[str, Any]:
    """A field as the manifest wrote it, plus what the window needs to know about it and may not guess.

    `drawn` - the form shows it (when its conditions are met); `sent` - its value goes to the service.
    """
    row = dict(field)
    row["id"] = field_id(field)
    row["kind"] = raw_kind(field)
    row["group"] = section_of(field)
    row["default"] = field_default(field)
    row["drawn"] = not route_of(field) and not is_gui_hidden(field)
    row["sent"] = row["drawn"] and not is_ui_only(field)
    row["depends_on"] = depends_on(field)
    if isinstance(field.get("options"), list):
        row["options"] = [describe_option(option) for option in field["options"]]
    source = option_source(field)
    if source:
        row["options_source"] = source
    return row


def describe_node(node: CommandNode | Operation) -> dict[str, Any]:
    children = tuple(getattr(node, "children", ()))
    return {
        "id": node.id, "title": node.title, "title_ru": node.title_ru,
        "description": node.description, "description_ru": node.description_ru,
        "kind": node.kind, "runs": bool(node.service), "parameters": dict(node.parameters),
        "fields": [describe_field(field) for field in node.fields if field_id(field)],
        "children": [describe_node(child) for child in children],
    }


def describe(manifest: ToolManifest, layout: dict[str, Any] | None = None) -> dict[str, Any]:
    """The manifest taken apart: what a window draws its sections, operations and fields by."""
    return {
        "tool": dict(manifest.raw.get("tool", {})),
        "nodes": [describe_node(node) for node in manifest.operation_groups],
        "maintenance": [describe_node(node) for node in manifest.maintenance_operations],
        "layout": layout or {},
        "slots": {"samples": dict(SLOT_PREVIEW_SAMPLES), "short_labels": SLOT_SHORT_LABELS},
    }
