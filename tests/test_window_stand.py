"""Стенд окна: поведение рабочей зоны, которое проверяли тесты прежнего окна, - на Debug-копии нового.

Прежнее окно проверялось из Python (классы `WorkbenchHistory` и функции `app.py`). Новое окно - программа
на C#, поэтому стенд запускает её отладочную копию со сценарием шагов (`AUDION_DEV_SCRIPT`, их читает
`Source\\MainWindow.Dev.cs`) и читает журнал, который она пишет. Окно стоит за краем экрана, мыши нет.

Три проверки взяты из прежних тестов:
- история путей помнит и закреплённые, и не закреплённые пути, а сброс оставляет только закрепления;
- при старте источник и назначение - `input` и `output` проекта, какие бы закрепления ни лежали в истории;
- окно не трогает закреплённые пути при очистке кэша истории.

Debug-копия есть только у того, кто собирал окно (`dotnet build Source -c Debug`); чистка проекта убирает
`Source\\bin`, и тогда проверки пропускаются.
"""
from __future__ import annotations

import datetime
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "Source"
BIN = SOURCE / "bin" / "Debug" / "net10.0"
EXE = BIN / "AudionAddressProcessor.exe"


def newest_source() -> float:
    return max(path.stat().st_mtime for pattern in ("*.cs", "*.axaml") for path in SOURCE.rglob(pattern)
               if "bin" not in path.relative_to(SOURCE).parts and "obj" not in path.relative_to(SOURCE).parts)


def run_stand(script: str, history: Path) -> list[str]:
    """Прогнать шаги в Debug-копии; вернуть строки журнала, которые она добавила."""
    log = BIN / "logs" / f"gui-{datetime.datetime.now():%Y%m%d}.log"
    before = len(log.read_text(encoding="utf-8").splitlines()) if log.is_file() else 0
    for stale in (BIN / "config").glob("window_settings.json*"):
        stale.unlink()
    env = dict(os.environ, AUDION_DEV_SCRIPT=script, AUDION_DEV_HISTORY=str(history))
    env.pop("AUDION_SHOT_ON_SCREEN", None)
    done = subprocess.run([str(EXE), "--root", str(ROOT)], env=env, timeout=120)
    assert done.returncode == 0, done.returncode
    lines = log.read_text(encoding="utf-8").splitlines() if log.is_file() else []
    return lines[before:]


@unittest.skipUnless(os.name == "nt" and EXE.is_file() and EXE.stat().st_mtime >= newest_source(),
                     "нет отладочной сборки окна новее его исходников: dotnet build Source -c Debug")
class TheWorkingAreaKeepsPathsAsTheEarlierWindowDid(unittest.TestCase):
    def setUp(self) -> None:
        self.box = Path(tempfile.mkdtemp(prefix="stand_"))
        self.addCleanup(shutil.rmtree, self.box, True)
        for name in ("source_pinned", "source_recent", "target_recent"):
            (self.box / name).mkdir()
        self.history = self.box / "path_history.json"

    def paths(self, lines: list[str], role: str) -> list[str]:
        return [line.split(f"history {role}: ", 1)[1] for line in lines if f"[dev] history {role}: " in line]

    def test_history_remembers_unpinned_and_the_reset_keeps_the_pins(self) -> None:
        pinned, recent, target = (self.box / name for name in ("source_pinned", "source_recent", "target_recent"))
        script = ";".join([
            "idle", f"choose=source:{pinned}", "pin=source", f"choose=source:{recent}", f"choose=target:{target}",
            "history=source", "history=target", "paths=reset", "history=source", "history=target", "close",
        ])
        lines = run_stand(script, self.history)
        # The journal holds both dumps one after another: the first before the reset, the second after it.
        dumps = [line for line in lines if "[dev] history source:" in line]
        self.assertTrue(any(f"pinned {pinned}" in line for line in dumps), dumps)
        self.assertTrue(any(str(recent) in line and "pinned" not in line for line in dumps), dumps)
        self.assertTrue(any("[dev] history target:" in line and str(target) in line for line in lines), lines[-12:])
        data = json.loads(self.history.read_text(encoding="utf-8"))
        # After the reset only what is pinned stays: the unpinned source and every target are gone.
        self.assertEqual([item["path"] for item in data["sources"]], [str(pinned)])
        self.assertTrue(data["sources"][0]["pinned"])
        self.assertEqual(data["targets"], [])

    def test_at_start_the_source_and_the_target_are_the_input_and_output_of_the_project(self) -> None:
        configured, pinned = self.box / "configured_source", self.box / "source_pinned"
        self.history.write_text(json.dumps({"sources": [
            {"path": str(configured), "count": 1, "last_used": "2026-01-01T00:00:00", "pinned": True},
            {"path": str(pinned), "count": 1, "last_used": "2026-01-02T00:00:00", "pinned": True},
        ], "targets": []}, ensure_ascii=False), encoding="utf-8")
        lines = run_stand("idle;say=validate_input;close", self.history)
        said = next(line for line in lines if "[dev] console:" in line)
        # The window names the paths of the project as the program counts them: from its folder.
        self.assertTrue(said.rstrip().endswith("--source input --target output"), said)
        self.assertNotIn(str(pinned), said)


if __name__ == "__main__":
    unittest.main()
