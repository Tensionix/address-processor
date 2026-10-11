"""The layout of the window as data: `config/window_layout.yaml` checked against the manifest.

The window draws sections and the operations in them from this file and from the manifest, and
knows no operation by name. A file that names an operation the manifest does not have, or leaves
one of its operations nowhere, is refused here - not found as a missing button on the screen.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import load_yaml_or_json
from .manifest import ToolManifest
from .operation_model import all_nodes, find_node


def placed_operations(layout: dict[str, Any]) -> list[str]:
    """Every operation id the layout names, in the order of the file, repeats kept."""
    placed: list[str] = []
    for section in layout.get("sections") or []:
        placed.extend(str(item.get("id", "")).strip() for item in section.get("operations") or [])
    placed.extend(str(value).strip() for value in (layout.get("workspace") or {}).values())
    placed.extend(str(value).strip() for value in layout.get("result_actions") or [])
    return placed


def runnable_ids(manifest: ToolManifest) -> list[str]:
    """The ids of the operations of the manifest that run something, each once."""
    seen: list[str] = []
    for node in all_nodes(manifest):
        if node.service and node.id not in seen:
            seen.append(node.id)
    return seen


def load_layout(path: Path, manifest: ToolManifest) -> dict[str, Any]:
    """The layout, or {} when the project has none; ValueError when it disagrees with the manifest."""
    layout = load_yaml_or_json(path)
    if not layout:
        return {}
    sections = layout.get("sections")
    if not isinstance(sections, list) or not sections:
        raise ValueError(f"{path.name}: no sections")
    ids: set[str] = set()
    for section in sections:
        section_id = str(section.get("id", "")).strip()
        if not section_id or section_id in ids:
            raise ValueError(f"{path.name}: a section has no id or repeats one: {section_id!r}")
        ids.add(section_id)
        for key in ("title", "title_ru", "hint", "hint_ru"):
            if not str(section.get(key, "")).strip():
                raise ValueError(f"{path.name}: section {section_id} has no {key}")
        operations = section.get("operations")
        if not isinstance(operations, list) or not operations:
            raise ValueError(f"{path.name}: section {section_id} has no operations")
        if len(operations) > 1:
            for item in operations:
                if not str(item.get("tab", "")).strip() or not str(item.get("tab_ru", "")).strip():
                    raise ValueError(f"{path.name}: {item.get('id')} in section {section_id} has no tab names")
    placed = placed_operations(layout)
    unknown = sorted({item for item in placed if find_node(manifest, item) is None})
    if unknown:
        raise ValueError(f"{path.name}: the manifest has no operation {', '.join(unknown)}")
    missing = [item for item in runnable_ids(manifest) if item not in placed]
    if missing:
        raise ValueError(f"{path.name}: nowhere in the window: {', '.join(missing)}")
    return layout
