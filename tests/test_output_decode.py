"""The output of a program that is not Python is read in the encoding it was written in (system_core/core/output_decode.py):
the same Russian text in UTF-8, UTF-16, cp866 and cp1251 reads the same; the short and the treacherous lines too; the lines of
one program are read in one encoding; a known encoding is not guessed."""
from __future__ import annotations

import io
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from system_core.core.jobs import JobContext, run_process  # noqa: E402
from system_core.core.output_decode import StreamDecoder, decode_process_bytes, guess  # noqa: E402
from system_core.core.paths import get_project_paths  # noqa: E402

TEXTS = [
    "Ошибка: не удаётся найти файл.",
    "Файл C:\\Temp\\отчёт.txt скопирован",
    "Сертификат добавлен в хранилище «Корневые».",
    "Обработано файлов: 12; пропущено: 0",
    "Отказано в доступе.",
    "Готово", "Ошибка", "Да", "Нет", "ПРИВЕТ",
    "╔══════╗", "║ Имя  ║",
]
# cp866 words that are valid UTF-8 by chance (an arrow, a Chinese sign), a cp1251 word that gives a Latin «Ÿ».
TRAPS = [("том", "cp866"), ("уже", "cp866"), ("так", "cp866"), ("только", "cp866"), ("сам", "cp866"), ("Её", "cp1251"),
         ("без", "cp1251"), ("Флаг", "cp1251"), ("(JSON)»", "cp1251")]


@pytest.mark.parametrize("encoding", ["utf-8", "cp866", "cp1251", "utf-16-le", "utf-16", "utf-16-be"])
@pytest.mark.parametrize("text", TEXTS)
def test_the_same_text_reads_the_same_in_every_encoding(text: str, encoding: str) -> None:
    try:
        data = text.encode(encoding)
    except UnicodeEncodeError:
        pytest.skip(f"{encoding} has no sign of {text!r}")
    assert decode_process_bytes(data) == text


@pytest.mark.parametrize(("text", "encoding"), TRAPS)
def test_a_short_line_that_looks_like_another_encoding_is_read_right(text: str, encoding: str) -> None:
    assert decode_process_bytes(text.encode(encoding)) == text


def test_ascii_alone_tells_nothing_and_utf8_with_cyrillic_is_sure() -> None:
    assert guess(b"Copying files...") == ("ascii", False)
    assert guess("Копирование".encode("utf-8")) == ("utf-8", True)
    assert guess("Скачано 45% ████▌".encode("utf-8")) == ("utf-8", True)


@pytest.mark.parametrize("encoding", ["cp866", "cp1251"])
def test_the_lines_of_one_program_are_read_in_one_encoding(encoding: str) -> None:
    lines = ["Копирование файлов началось.", "Да", "ОК", "сам", "трёх", "Готово"]
    decoder = StreamDecoder()
    assert [decoder.decode((line + "\r\n").encode(encoding)).rstrip("\r\n") for line in lines] == lines
    assert decoder.encoding == encoding


def test_utf16_le_read_line_by_line_from_a_pipe() -> None:
    text = "Первая строка\r\nвторая\r\nтретья\r\n"
    decoder = StreamDecoder()
    pieces = [decoder.decode(raw).rstrip("\r\n") for raw in io.BytesIO(text.encode("utf-16-le"))]
    assert [piece for piece in pieces if piece] == ["Первая строка", "вторая", "третья"]


def test_a_known_encoding_is_not_guessed() -> None:
    # «Да» in cp1251 read as cp866 is «ДР»: told the encoding, the decoder does not guess.
    assert StreamDecoder("cp866").decode("Да".encode("cp866")) == "Да"
    assert StreamDecoder("cp1251").decode("сам".encode("cp1251")) == "сам"


@pytest.mark.skipif(os.name != "nt", reason="the console pages are a matter of Windows")
@pytest.mark.parametrize("encoding", ["cp866", "cp1251"])
def test_run_process_reads_a_program_of_windows_in_its_page(tmp_path: Path, encoding: str) -> None:
    lines = ["Копирование файлов началось.", "Да", "Готово: 3 файла"]
    payload = tmp_path / "out.txt"
    payload.write_bytes(("\r\n".join(lines) + "\r\n").encode(encoding))
    said: list[str] = []
    context = JobContext(paths=get_project_paths(ROOT), operation=None, log_file=tmp_path / "op.log", report_dir=tmp_path,
                         log_callback=said.append)
    result = run_process(context, ["cmd", "/d", "/c", "type", str(payload)], cwd=tmp_path)
    assert list(result.lines) == lines
