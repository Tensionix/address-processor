from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable


OFFICE_TEMP_SUFFIXES = {".tmp", ".temp", ".wbk", ".asd", ".xlk"}


@dataclass(frozen=True)
class CleanupRecord:
    path: Path
    reason: str


LogCallback = Callable[[str], None]


def is_office_temp_file(path: Path) -> bool:
    name = path.name
    lowered = name.lower()
    return (
        name.startswith("~$")
        or (name.startswith(".~lock.") and name.endswith("#"))
        or path.suffix.lower() in OFFICE_TEMP_SUFFIXES
        or lowered.endswith(".tmp")
    )


def delete_office_temp_files(folder: Path, *, log: LogCallback | None = None) -> tuple[CleanupRecord, ...]:
    if not folder.exists():
        return ()

    records: list[CleanupRecord] = []
    for path in sorted(folder.rglob("*")):
        if not path.is_file() or not is_office_temp_file(path):
            continue
        try:
            path.unlink()
        except OSError as exc:
            if log:
                log(f"[SKIP TEMP] {path}: {exc}")
            continue
        record = CleanupRecord(path=path, reason="office_temp_file")
        records.append(record)
        if log:
            log(f"[DELETE TEMP] {path}")
    return tuple(records)
