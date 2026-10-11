"""Сборщик: что читает из него Оркестратор и из чего он собирает окружение.

`builder_main.cmd` запускают не только из меню. Оркестратор находит шаг по строке
`if /I "%RAW%"=="<код>" goto <МЕТКА>` и вырезает команды от метки до `goto MAIN` в свой командный
файл; шаг без метки или без команд для него отсутствует, и сборка проекта кончается отказом. Здесь
тот же разбор повторён, чтобы потерянный шаг находился в проекте, а не в выпуске.

Сборка обновляет компоненты - Python и его пакеты; `App\\` она не собирает. Окружение после чистки
ставится заново из `install\\requirements_full.in`, поэтому пакет, который движок импортирует, обязан
быть в этом списке: поставленный в `runtime\\` руками живёт до первой чистки.

Проверки ничего не запускают и не скачивают (кроме шага 70 на подставном проекте во временной папке).
"""
from __future__ import annotations

import ast
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "builder_main.cmd"
REQUIREMENTS = ROOT / "install" / "requirements_full.in"

MENU = re.compile(r"echo\s+\[(?P<code>\d{2})\]\s*(?P<rest>.*)$")
DISPATCH = re.compile(r'if\s+/I\s+"%RAW%"\s*==\s*"(?P<raw>[^"]+)"\s+goto\s+(?P<label>[A-Za-z0-9_]+)')
LABEL = re.compile(r"^\s*:(?P<label>[A-Za-z0-9_]+)\s*$")
CALLED = re.compile(r'call\s+"%BASE_DIR%\\(?P<path>[^"]+)"', re.IGNORECASE)

# Имя, под которым пакет импортируют, - имя, под которым его ставят.
PACKAGE_OF = {"yaml": "pyyaml", "fitz": "pymupdf", "win32com": "pywin32", "pythoncom": "pywin32",
              "win32process": "pywin32"}


def builder_lines() -> list[str]:
    return BUILDER.read_text(encoding="ascii").splitlines()


def menu_steps(lines: list[str]) -> dict[str, str]:
    """Шаги меню: код - действие. Как у Оркестратора: первая строка с действием побеждает."""
    steps: dict[str, str] = {}
    for line in lines:
        found = MENU.search(line)
        if not found or found["code"] == "00":
            continue
        parts = re.split(r"\s*\^\|\s*", found["rest"].strip(), maxsplit=2)
        steps.setdefault(found["code"], parts[1].strip() if len(parts) > 1 else "")
    return steps


def dispatch(lines: list[str]) -> dict[str, str]:
    table: dict[str, str] = {}
    for line in lines:
        found = DISPATCH.search(line)
        if found:
            table.setdefault(found["raw"].strip().lower(), found["label"].upper())
    return table


def body(lines: list[str], label: str) -> list[str]:
    """Команды шага: от метки до `goto MAIN` вне скобок, без пауз и комментариев."""
    commands: list[str] = []
    inside = False
    depth = 0
    for line in lines:
        named = LABEL.match(line)
        if named:
            if inside:
                break
            inside = named["label"].upper() == label
            continue
        if not inside:
            continue
        text = line.strip()
        if not text or re.match(r"(?i)^(pause(\s|$)|rem\b|::)", text):
            continue
        if re.match(r"(?i)^goto\s+MAIN\b", text) and depth <= 0:
            break
        if re.match(r"(?i)^exit\s+/b\b", text) and depth <= 0:
            break
        commands.append(text)
        depth = max(0, depth + line.count("(") - line.count(")"))
    return commands


def listed_packages() -> tuple[set[str], set[str]]:
    """Пакеты списка: те, что ставятся, и те, что названы запасными (закомментированы)."""
    active: set[str] = set()
    optional: set[str] = set()
    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        target = active
        if text.startswith("#"):
            text, target = text.lstrip("# ").strip(), optional
            if " " in text:
                continue  # фраза, а не имя пакета
        if text:
            target.add(re.split(r"[\[<>=!~ ]", text, maxsplit=1)[0].lower())
    return active, optional


def engine_imports() -> dict[str, bool]:
    """Сторонние модули движка: имя - все ли его импорты стоят под `try`."""
    files = [path for path in (ROOT / "system_core").rglob("*.py") if "__pycache__" not in path.parts]
    own = {path.stem for path in files} | {part for path in files for part in path.relative_to(ROOT).parts[:-1]}
    guarded: dict[str, bool] = {}
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        in_try = {id(child) for node in ast.walk(tree) if isinstance(node, ast.Try) for child in ast.walk(node)}
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module.split(".")[0]]
            for name in names:
                if name in sys.stdlib_module_names or name in own:
                    continue
                guarded[name] = guarded.get(name, True) and id(node) in in_try
    return guarded


class TheBuilderOffersWhatItsMenuNames(unittest.TestCase):
    def setUp(self) -> None:
        self.lines = builder_lines()
        self.steps = menu_steps(self.lines)
        self.table = dispatch(self.lines)

    def test_every_step_of_the_menu_has_a_body(self) -> None:
        self.assertTrue(self.steps)
        lost = []
        for code, action in self.steps.items():
            by_code, by_action = self.table.get(code), self.table.get(action.lower())
            if not action or by_code is None or by_code != by_action or not body(self.lines, by_code):
                lost.append("%s:%s" % (code, action))
        self.assertEqual(lost, [])

    def test_every_script_a_step_calls_is_in_the_project(self) -> None:
        missing = []
        for code in self.steps:
            for command in body(self.lines, self.table[code]):
                for found in CALLED.finditer(command):
                    if not (ROOT / found["path"]).is_file():
                        missing.append("%s: %s" % (code, found["path"]))
        self.assertEqual(missing, [])

    def test_a_release_build_has_its_steps(self) -> None:
        # Сборка выпуска: вернуть Python, проверить, убрать кэш установки. Окно она не собирает.
        offered = {"%s:%s" % pair for pair in self.steps.items()}
        self.assertLessEqual({"02:build_ps", "71:verify", "70:clean_cache"}, offered)

    def test_the_verify_step_checks_the_window_a_build_does_not_make(self) -> None:
        """`App\\` едет в выпуск готовой: проверка смотрит, на месте ли она и рисует ли манифест этой версии."""
        commands = body(self.lines, self.table["71"])
        self.assertEqual(len(commands), 1)
        script = ROOT / CALLED.search(commands[0])["path"]
        text = script.read_text(encoding="ascii")
        for needed in ("runtime\\python.exe", "address_cli.cmd", "describe", "Start.exe", "App\\AudionAddressProcessor.exe",
                       "App\\AudionPs.exe", "config\\version.json", "--self-check="):
            self.assertIn(needed, text)
        self.assertNotIn("dotnet", text.lower().replace(".net 10 sdk", ""))      # SDK проверке не нужен

    def test_no_step_fetches_what_the_program_no_longer_has(self) -> None:
        """Меню с fzf и прежние окна убраны, PowerShell у программы свой: шагов и сценариев для них нет."""
        named = []
        scripts = [BUILDER, ROOT / "cleanup_project.cmd", *sorted((ROOT / "install").glob("*.cmd")),
                   *sorted((ROOT / "install").glob("*.ps1"))]
        for path in scripts:
            text = path.read_text(encoding="utf-8-sig", errors="replace").lower()
            for word in ("fzf", "system_core\\powershell", "_pwsh_tmp", "launcher_gui", "launcher_project", "ui_nicegui"):
                if word in text:
                    named.append("%s: %s" % (path.name, word))
        self.assertEqual(named, [])


@unittest.skipUnless(os.name == "nt", "шаг 70 - сценарий Windows")
class TheCleanCacheStepLeavesTheProgramWhole(unittest.TestCase):
    """Шаг 70 на подставном проекте.

    За день работы над окном в `Source\\bin` и `Source\\obj` набирается около гигабайта.
    `cleanup_project.cmd` в рабочей папке не запускают - он опустошает `output\\`, - поэтому остатки
    сборок убирает шаг 70: собранное окно, исходники, окружение и файлы владельца он не трогает.
    """

    STAYS = ("App/AudionAddressProcessor.exe", "App/AudionPs.exe", "Source/Program.cs", "Source/Views/Form.cs",
             "Source/Ps/Program.cs", "Source/Ps/AudionPs.csproj", "install/download/get-pip.py", "runtime/python.exe",
             "wheelhouse/lxml.whl", "output/book.xlsx", "report/run/report.md", "config/window_settings.json", "Start.exe")
    GOES = ("Source/bin/Debug/net10.0/AudionAddressProcessor.dll", "Source/bin/Release/net10.0/win-x64/AudionAddressProcessor.exe",
            "Source/obj/project.assets.json", "Source/Ps/bin/Release/net10.0/win-x64/AudionPs.dll",
            "Source/Ps/obj/project.assets.json", "install/download/python-3.12.10-embed-amd64.zip",
            "system_core/__pycache__/cli.cpython-312.pyc")

    def test_build_leftovers_go_and_the_window_stays(self) -> None:
        shell = next((path for path in (str(ROOT / "App" / "AudionPs.exe"), shutil.which("pwsh"), shutil.which("powershell"))
                      if path and Path(path).is_file()), None)
        if shell is None:
            self.skipTest("PowerShell не найден")
        box = Path(tempfile.mkdtemp(prefix="clean70_"))
        self.addCleanup(shutil.rmtree, box, True)
        for name in (*self.STAYS, *self.GOES):
            path = box / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("x", encoding="utf-8")
        done = subprocess.run([shell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
                               str(ROOT / "install" / "Clean-Install-Cache.ps1"), "-ProjectRoot", str(box)],
                              stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                              encoding="utf-8", errors="replace", timeout=120)
        self.assertEqual(done.returncode, 0, done.stdout)
        self.assertEqual([name for name in self.STAYS if not (box / name).is_file()], [])
        self.assertEqual([name for name in self.GOES if (box / name).exists()], [])
        for folder in ("Source/bin", "Source/obj", "Source/Ps/bin", "Source/Ps/obj"):
            self.assertFalse((box / folder).exists(), folder)
        self.assertIn("Source\\bin", done.stdout)           # что убрано, названо путём, а не словом «bin»


class TheBuildInstallsWhatTheEngineImports(unittest.TestCase):
    def test_every_package_the_engine_imports_is_listed(self) -> None:
        active, optional = listed_packages()
        unlisted = []
        for name, only_under_try in sorted(engine_imports().items()):
            package = PACKAGE_OF.get(name, name).lower()
            if package in active or (only_under_try and package in optional):
                continue
            unlisted.append("%s (%s)" % (name, package))
        self.assertEqual(unlisted, [])

    def test_the_doctor_asks_only_for_what_the_build_installs(self) -> None:
        """Без пакета из списка доктор должен отказывать, а пакет, которого в списке нет, он требовать не вправе."""
        from system_core import doctor
        active, _ = listed_packages()
        asked = {package.lower() for _module, package in doctor.REQUIRED_MODULES}
        self.assertEqual(sorted(asked - active), [])
        self.assertIn(("pandas", "pandas"), doctor.REQUIRED_MODULES)


if __name__ == "__main__":
    unittest.main()
