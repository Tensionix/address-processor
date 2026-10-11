"""Очистка рабочих папок движком: куда бы окно ни показало источник и назначение, проект и папки программы целы.

Операция «Очистить input и output программы» получает от окна источник и назначение; окно не даёт
выбрать корень проекта, но командная строка - даёт. Охрана стоит в самом движке.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from system_core.services.address_aligner_service import _clean_managed_folder  # noqa: E402


def context(root: Path) -> SimpleNamespace:
    return SimpleNamespace(paths=SimpleNamespace(root=root), log=lambda line: None)


@pytest.mark.parametrize("name", ["", "config", "system_core", "runtime", "App", "Source", "data", "docs"])
def test_the_project_and_the_folders_of_the_program_are_never_cleaned(tmp_path: Path, name: str) -> None:
    folder = tmp_path / name if name else tmp_path
    folder.mkdir(exist_ok=True)
    keep = folder / "keep.txt"
    keep.write_text("x", encoding="utf-8")
    with pytest.raises(RuntimeError):
        _clean_managed_folder(context(tmp_path), folder, "SOURCE")
    assert keep.is_file()


def test_a_working_folder_is_cleaned_and_stays(tmp_path: Path) -> None:
    for name in ("input", "output", "output/sub"):
        folder = tmp_path / name
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "a.txt").write_text("x", encoding="utf-8")
        result = _clean_managed_folder(context(tmp_path), folder, name)
        assert folder.is_dir()
        assert not (folder / "a.txt").exists()
        assert result["removed_items"] >= 1


def test_a_folder_outside_the_project_is_refused(tmp_path: Path) -> None:
    project, elsewhere = tmp_path / "project", tmp_path / "elsewhere"
    project.mkdir()
    elsewhere.mkdir()
    (elsewhere / "a.txt").write_text("x", encoding="utf-8")
    with pytest.raises(RuntimeError):
        _clean_managed_folder(context(project), elsewhere, "TARGET")
    assert (elsewhere / "a.txt").is_file()
