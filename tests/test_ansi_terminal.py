from __future__ import annotations

from pathlib import Path
import os
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from system_core.core.ansi_terminal import (  # noqa: E402
    AnsiHtmlRenderer,
    ansi_to_html,
    strip_ansi,
    terminal_html,
    terminal_lines_html,
)
from system_core.core.jobs import JobContext, decode_process_line, run_process  # noqa: E402
from system_core.core.logging_utils import append_log  # noqa: E402
from system_core.core.manifest import Operation  # noqa: E402
from system_core.core.paths import get_project_paths  # noqa: E402


class AnsiTerminalTests(unittest.TestCase):
    def test_ansi_to_html_escapes_text_and_renders_sgr(self) -> None:
        html = ansi_to_html("Привет <tag> \x1b[36m[OK]\x1b[0m")

        self.assertIn("Привет &lt;tag&gt;", html)
        self.assertIn('<span style="color:#06b6d4">[OK]</span>', html)
        self.assertNotIn("\x1b", html)
        self.assertNotIn("[36m", html)
        self.assertNotIn("[0m", html)

    def test_strip_ansi_returns_plain_utf8_text(self) -> None:
        plain = strip_ansi("\x1b[1;32m[INFO]\x1b[0m Кириллица <tag>")

        self.assertEqual(plain, "[INFO] Кириллица <tag>")
        self.assertNotIn("\x1b", plain)
        self.assertNotIn("[0m", plain)

    def test_disk_log_is_plain_utf8_without_ansi(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_file = Path(tmp) / "run.log"
            append_log(log_file, "\x1b[36m[OK]\x1b[0m Кириллица")
            text = log_file.read_text(encoding="utf-8")

        self.assertIn("[OK] Кириллица", text)
        self.assertNotIn("\x1b", text)
        self.assertNotIn("[36m", text)
        self.assertNotIn("[0m", text)

    def test_stateful_renderer_carries_style_between_chunks(self) -> None:
        renderer = AnsiHtmlRenderer()

        first = renderer.render_line("\x1b[93mпервая")
        second = renderer.render_line("вторая\x1b[0m")
        third = renderer.render_line("обычная")

        self.assertIn('<span style="color:#facc15">первая</span>', first)
        self.assertIn('<span style="color:#facc15">вторая</span>', second)
        self.assertEqual(third, "обычная")

    def test_unsupported_control_sequences_are_dropped(self) -> None:
        html = ansi_to_html("a\x1b]0;title\x07b\x1b[2Jc")

        self.assertEqual(html, "abc")
        self.assertNotIn("title", html)
        self.assertNotIn("\x1b", html)

    def test_terminal_lines_html_can_append_without_rerendering_prefix(self) -> None:
        first = terminal_lines_html(["\x1b[36m[OK]\x1b[0m Кириллица"])
        second = terminal_lines_html(["<tag>"], leading_newline=True)

        self.assertIn('<span style="color:#06b6d4">[OK]</span>', first)
        self.assertEqual(second, "\n&lt;tag&gt;")
        self.assertNotIn("\x1b", first + second)
        self.assertNotIn("[36m", first + second)

    def test_cp866_windows_tool_output_decodes_without_mojibake(self) -> None:
        text = "Ошибка: не удаётся найти файл."
        decoded = decode_process_line(text.encode("cp866"))

        self.assertEqual(decoded, text)
        self.assertNotIn("�", decoded)
        self.assertNotIn("����", decoded)
        self.assertNotIn("㤠", decoded)
        self.assertNotIn("䠩", decoded)

    def test_run_process_decodes_non_python_cp866_byte_stream(self) -> None:
        if os.name != "nt":
            self.skipTest("Windows codepage fallback is only relevant on Windows.")

        raw_lines: list[str] = []
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            log_file = tmp_path / "run.log"
            payload_path = tmp_path / "cp866_output.txt"
            payload_path.write_bytes("Ошибка: не удаётся найти файл.\r\n".encode("cp866"))
            context = JobContext(
                paths=get_project_paths(ROOT),
                operation=Operation(
                    id="cp866_subprocess_test",
                    title="CP866 subprocess test",
                    description="",
                    service="tests:test",
                ),
                log_file=log_file,
                report_dir=tmp_path,
                log_callback=raw_lines.append,
            )

            result = run_process(
                context,
                ["cmd.exe", "/d", "/c", "type", str(payload_path)],
                cwd=ROOT,
                check=True,
            )

        self.assertEqual(result.exit_code, 0)
        self.assertIn("Ошибка: не удаётся найти файл.", result.lines)
        joined = "\n".join(raw_lines)
        self.assertNotIn("�", joined)
        self.assertNotIn("����", joined)
        self.assertNotIn("㤠", joined)
        self.assertNotIn("䠩", joined)

    def test_run_process_keeps_gui_raw_ansi_but_disk_log_plain(self) -> None:
        raw_lines: list[str] = []
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            log_file = tmp_path / "run.log"
            context = JobContext(
                paths=get_project_paths(ROOT),
                operation=Operation(
                    id="ansi_subprocess_test",
                    title="ANSI subprocess test",
                    description="",
                    service="tests:test",
                ),
                log_file=log_file,
                report_dir=tmp_path,
                log_callback=raw_lines.append,
            )
            script = (
                "import os, sys; "
                "print(os.environ.get('PYTHONUNBUFFERED', '')); "
                "sys.stdout.write('\\x1b[36m[OK]\\x1b[0m Кириллица <tag>\\n'); "
                "sys.stdout.flush()"
            )
            script_path = tmp_path / "ansi_subprocess.py"
            script_path.write_text(script, encoding="utf-8")

            result = run_process(context, [sys.executable, str(script_path)], cwd=ROOT, check=True)
            log_text = log_file.read_text(encoding="utf-8")

        self.assertEqual(result.exit_code, 0)
        self.assertIn("1", result.lines)
        self.assertTrue(any("\x1b[36m" in line for line in raw_lines))
        self.assertTrue(any(line.startswith("[CMD]") and " -u " in line for line in raw_lines))

        html = terminal_html(raw_lines)
        self.assertIn('<span style="color:#06b6d4">[OK]</span>', html)
        self.assertIn("Кириллица &lt;tag&gt;", html)
        self.assertNotIn("\x1b", html)
        self.assertNotIn("[36m", html)
        self.assertNotIn("[0m", html)

        self.assertIn("[OK] Кириллица <tag>", log_text)
        self.assertNotIn("\x1b", log_text)
        self.assertNotIn("[36m", log_text)
        self.assertNotIn("[0m", log_text)


if __name__ == "__main__":
    unittest.main()
