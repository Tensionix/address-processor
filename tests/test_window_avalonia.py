"""Окно на Avalonia (Source\\) и консольная команда: то, что одно читает, другое отдаёт.

Окно - лицо команды: манифест оно получает командой `describe`, операцию запускает командой `run`,
ход читает из служебных строк. Это контракт двух программ на двух языках, и расходится он молча:
ключ, переименованный в команде, в окне просто окажется пустым. Здесь он сверяется по исходникам, а
собранное окно проверяет себя само (`--self-check`): у каждой операции манифеста есть кнопка, у
каждого поля - элемент формы.

Проверки не открывают окно (кроме самопроверки собранной копии, которая окно не показывает) и не
запускают операций.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from system_core import cli  # noqa: E402

SOURCE = ROOT / "Source"
CYRILLIC = re.compile("[А-Яа-яЁё]")
# Ключи, которые окно честно читает, если манифест их даст: команда пересылает поле, как его записал манифест.
OPTIONAL_KEYS = {"min", "max", "step", "min_selected", "placeholder_ru", "tooltip", "tooltip_ru", "short_label", "short_label_ru"}
# Ключи вариантов, которые приходят не от describe, а от поставщика списка (команда `options`).
PROVIDER_KEYS = {"header", "pinned"}
MANIFEST_TEXT = (ROOT / "config" / "tool_manifest.yaml").read_text(encoding="utf-8")


def sources(pattern: str) -> list[Path]:
    return [path for path in sorted(SOURCE.rglob(pattern))
            if "bin" not in path.relative_to(SOURCE).parts and "obj" not in path.relative_to(SOURCE).parts]


def snake(name: str) -> str:
    return re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", name).lower()


def properties(class_name: str) -> set[str]:
    """Свойства класса модели окна, которые читаются из ответа команды, - именами ключей JSON."""
    text = (SOURCE / "Core" / "Manifest.cs").read_text(encoding="utf-8")
    body = re.search(r"public sealed class %s\b.*?\n\{(.*?)\n\}" % class_name, text, re.S)
    assert body, class_name
    found = set()
    for line in body.group(1).splitlines():
        if "[JsonIgnore]" in line:
            continue
        match = re.match(r"\s*public [\w<>?\[\], ()]+ (\w+) \{ get; set; \}", line)
        if match:
            found.add(snake(match.group(1)))
    return found


def all_nodes(nodes):
    for node in nodes:
        yield node
        yield from all_nodes(node["children"])


def window_texts() -> dict[str, str]:
    """Русские тексты окна: литералы кода и разметки, которые видит человек."""
    found: dict[str, str] = {}
    for path in sources("*.cs"):
        if path.name in ("MainWindow.Dev.cs", "Icons.cs"):       # шаги проверки без мыши: в выпуск не идут
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip().startswith("//"):
                continue
            for literal in re.findall(r'"((?:[^"\\]|\\.)*)"', line.split(" // ")[0]):
                if not CYRILLIC.search(literal):
                    continue
                # Образцы, по которым журнал красит строки, и метка строк окна - не тексты для перевода.
                if path.name == "Journal.cs" and ("|" in literal or literal == "[окно]"):
                    continue
                text = literal.replace('\\"', '"').replace("\\n", "\n").replace("\\\\", "\\")
                found.setdefault(text, f"{path.relative_to(SOURCE)}:{number}")
    for path in sources("*.axaml"):
        text = re.sub(r"<!--.*?-->", "", path.read_text(encoding="utf-8"), flags=re.S)
        for _attribute, value in re.findall(r'(Text|ToolTip\.Tip|PlaceholderText|Header|Content|Title)="([^"]*)"', text):
            if CYRILLIC.search(value):
                found.setdefault(value.replace("&quot;", '"'), path.name)
    return found


@unittest.skipUnless(SOURCE.is_dir(), "исходников окна нет")
class WindowAndCommandTests(unittest.TestCase):
    def describe(self) -> dict:
        done = subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "system_core" / "cli.py"), "describe"],
                              capture_output=True, text=True, encoding="utf-8", timeout=120)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)

    def test_every_text_of_the_window_has_an_english_pair(self) -> None:
        dictionary = json.loads((SOURCE / "config" / "i18n.json").read_text(encoding="utf-8-sig"))
        texts = window_texts()
        missing = {text: where for text, where in texts.items() if text not in dictionary}
        self.assertEqual(missing, {}, "русские тексты окна без английской пары в Source\\config\\i18n.json")
        empty = [text for text, pair in dictionary.items() if not str(pair.get("en") or "").strip()]
        self.assertEqual(empty, [], "записи словаря без английского текста")
        # Записи, которых в окне нет, допустимы только для текстов манифеста, которые он даёт лишь по-русски.
        stale = sorted(text for text in dictionary if text not in texts and text not in MANIFEST_TEXT)
        self.assertEqual(stale, [], "записи словаря, которых нет ни в окне, ни в манифесте")
        for text, pair in dictionary.items():
            self.assertEqual(sorted(re.findall(r"\{\d+\}", text)), sorted(re.findall(r"\{\d+\}", pair["en"])),
                             f"места подстановки в русском и английском тексте разные: {text!r}")

    def test_the_window_calls_python_as_the_wrapper_does(self) -> None:
        """Окно зовёт Python проекта само, без cmd: то, что делает обёртка, повторено слово в слово."""
        wrapper = (ROOT / "address_cli.cmd").read_text(encoding="ascii")
        door = (SOURCE / "Core" / "Door.cs").read_text(encoding="utf-8")
        paths = (SOURCE / "Core" / "Paths.cs").read_text(encoding="utf-8")
        self.assertIn(r'"%PYTHON_CMD%" -u "%BASE_DIR%\system_core\cli.py" %*', wrapper)
        self.assertIn('new[] { "-u", Script }', door)
        self.assertIn('Path.Combine(Paths.Root, "system_core", "cli.py")', door)
        for name, value in (("PYTHONUTF8", "1"), ("PYTHONIOENCODING", "utf-8")):
            self.assertIn(f'set "{name}={value}"', wrapper)
            self.assertIn(f'["{name}"] = "{value}"', door)
        # Python ищется там же и в том же порядке.
        for place in (r"runtime\python.exe", r"runtime\python\python.exe"):
            self.assertIn(place, wrapper)
            self.assertIn(place.replace("\\", "\\\\") if '@"' not in paths else place, paths)
        self.assertLess(paths.index(r"runtime\python.exe"), paths.index(r"runtime\python\python.exe"))
        self.assertIn('DoorName = "address_cli.cmd"', paths)

    def test_the_command_gives_every_key_the_window_reads(self) -> None:
        described = self.describe()
        nodes = list(all_nodes(described["nodes"] + described.get("maintenance", [])))
        fields = [field for node in nodes for field in node["fields"]]
        options = [option for field in fields for option in field.get("options", [])]
        # Ключ, которого в ответе нет ни у одного поля, окно ещё может ждать: его даёт манифест не каждому полю.
        manifest_keys = set(re.findall(r"^\s*-?\s*([a-z_]+):", MANIFEST_TEXT, re.M))
        for class_name, given in (
                ("Node", set().union(*(set(node) for node in nodes))),
                ("Field", set().union(*(set(field) for field in fields))),
                ("Option", set().union(*(set(option) for option in options))),
                ("SectionInfo", set().union(*(set(part) for part in described["layout"]["sections"]))),
                ("PlacedOperation", set().union(*(set(operation) for part in described["layout"]["sections"] for operation in part["operations"]))),
                ("Layout", set(described["layout"])),
                ("WorkspaceInfo", set(described["layout"]["workspace"])),
                ("SlotInfo", set(described["slots"])),
                ("ProjectPaths", set(described["paths"])),
        ):
            unread_by_command = properties(class_name) - given - manifest_keys - OPTIONAL_KEYS - PROVIDER_KEYS
            self.assertEqual(unread_by_command, set(), f"окно ждёт от {class_name} ключи, которых команда не отдаёт")
        self.assertEqual(properties("Manifest") - set(described), set(), "окно ждёт от describe ключи, которых нет")

    def test_the_window_knows_every_kind_of_field(self) -> None:
        text = (SOURCE / "Core" / "Manifest.cs").read_text(encoding="utf-8")
        known = set(re.findall(r'"(\w+)"', re.search(r"Known =\s*\{([^}]*)\}", text, re.S).group(1)))
        described = self.describe()
        used = {field["kind"] for node in all_nodes(described["nodes"] + described.get("maintenance", [])) for field in node["fields"]
                if field.get("drawn", True)}
        self.assertEqual(used - known, set(), "в манифесте есть поля вида, которого форма окна не рисует")
        self.assertEqual(known - {field["kind"] for node in all_nodes(described["nodes"] + described.get("maintenance", []))
                                  for field in node["fields"]}, set(), "форма знает вид поля, которого в манифесте нет")

    def test_service_lines_and_exit_codes(self) -> None:
        door = (SOURCE / "Core" / "Door.cs").read_text(encoding="utf-8")
        self.assertIn(f'Control = "{cli.CONTROL}"', door)
        self.assertIn(f"ExitDone = {cli.EXIT_OK}, ExitFailed = {cli.EXIT_FAILED}, ExitUsage = {cli.EXIT_USAGE}, "
                      f"ExitStopped = {cli.EXIT_STOPPED}", door)
        source = (ROOT / "system_core" / "cli.py").read_text(encoding="utf-8")
        said = set(re.findall(r'control\(\{"(\w+)"', source))
        self.assertEqual(said, {"started", "progress", "live", "finished"})
        for kind in said:
            self.assertIn(f'TryGetProperty("{kind}"', door, f"окно не читает служебную строку «{kind}»")
        # Ключи команды `run`, которыми окно её зовёт.
        for key in ("--operation", "--params", "--result", "--cancel-file", "--session-dir"):
            self.assertIn(f'"{key}"', source)
            self.assertIn(f'"{key}"', door)

    def test_every_operation_stands_in_the_layout_and_the_window_draws_its_hidden_fields_by_key(self) -> None:
        """Окно не знает операций по имени: что нарисовать, говорят ключи манифеста, а не `if` по идентификатору."""
        code = "\n".join(path.read_text(encoding="utf-8") for path in sources("*.cs")
                         if path.name not in ("MainWindow.Dev.cs", "Icons.cs"))
        described = self.describe()
        for operation in (node for node in all_nodes(described["nodes"] + described.get("maintenance", [])) if node["runs"]):
            self.assertNotIn(f'"{operation["id"]}"', code, f"окно знает операцию {operation['id']} по имени")

    def test_start_exe_opens_the_window(self) -> None:
        """Start.exe в корне запускает окно из App\\ - то самое, что собирает проект окна."""
        launcher = (ROOT / "system_core" / "start_launcher" / "StartLauncher.cs").read_text(encoding="utf-8")
        project = (SOURCE / "AudionAddressProcessor.csproj").read_text(encoding="utf-8")
        assembly = re.search(r"<AssemblyName>(\w+)</AssemblyName>", project).group(1)
        self.assertIn(f'ProgramName = "{assembly}.exe"', launcher)
        self.assertIn('Path.Combine(root, "App")', launcher)
        code = "\n".join(line for line in launcher.splitlines() if not line.strip().startswith("//"))
        self.assertNotIn("launcher_gui", code, "лаунчер снова зовёт прежнее окно")
        self.assertNotIn("cmd.exe", code)
        # Исходник несёт русский текст: сборка обязана читать его как UTF-8.
        build = (ROOT / "install" / "Build-StartLauncher.ps1").read_text(encoding="utf-8")
        self.assertIn('"/codepage:65001"', build)
        start, window = ROOT / "Start.exe", ROOT / "App" / f"{assembly}.exe"
        if not start.is_file() or not window.is_file():
            self.skipTest("Start.exe или App\\ не собраны")
        if start.stat().st_mtime < (ROOT / "system_core" / "start_launcher" / "StartLauncher.cs").stat().st_mtime:
            self.skipTest("Start.exe старше своего исходника: install\\Build-StartLauncher.cmd")
        done = subprocess.run([str(start), "--self-test"], timeout=60)
        self.assertEqual(done.returncode, 0, "Start.exe не находит окно в App\\")

    def test_the_built_window_holds_the_whole_manifest(self) -> None:
        """Собранное окно строит все разделы без показа и считает построенное против манифеста."""
        newest = max(path.stat().st_mtime for pattern in ("*.cs", "*.axaml") for path in sources(pattern))
        built = [path for path in (ROOT / "App" / "AudionAddressProcessor.exe",
                                   SOURCE / "bin" / "Release" / "net10.0" / "AudionAddressProcessor.exe",
                                   SOURCE / "bin" / "Debug" / "net10.0" / "AudionAddressProcessor.exe")
                 if path.is_file() and path.stat().st_mtime >= newest]
        if not built:
            self.skipTest("нет сборки окна новее его исходников: install\\Build-App.cmd")
        with tempfile.TemporaryDirectory() as temp:
            report = Path(temp) / "self_check.json"
            done = subprocess.run([str(built[0]), "--root", str(ROOT), f"--self-check={report}"], timeout=180)
            self.assertTrue(report.is_file(), "окно не записало результат самопроверки")
            result = json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual(done.returncode, 0, result)
        self.assertTrue(result["ok"], result)


if __name__ == "__main__":
    unittest.main()
