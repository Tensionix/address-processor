"""How the output of a program that is not Python is read: in the encoding it was written in.

A Python script of the project writes UTF-8 (the runner tells it to); a program of Windows writes what it likes - UTF-8,
UTF-16, the OEM page of the console (cp866), the ANSI page of the system (cp1251). The rules go from the sure to the guessed:

1. a known program is read in its own encoding, given by whoever runs it (`StreamDecoder(encoding=...)`);
2. a mark of the order of bytes, or the bytes below the space every other byte (the high bytes of UTF-16), is UTF-16 - with
   the order that gives a text;
3. bytes that are valid UTF-8 and give Cyrillic, or only the usual signs (quotes, dashes, №, the degree, the drawing of
   tables), are UTF-8. A line of another page is seldom valid UTF-8, and when it is, it gives signs of other scripts -
   cp866 «том» is the bytes of an arrow, «уже» of a Chinese sign, cp1251 «Её» of a Latin «Ÿ» - and the pages compete;
4. ASCII alone tells nothing and is read as it is;
5. between the single-byte pages the one where the text looks like Russian wins: frequent letters, small letters inside
   words, a vowel in a word, no letter three times in a row, few signs that are neither. A line of Russian in cp866 read as cp1251 turns into
   signs and rare letters, and back; the frame of a table of cp866 read as cp1251 turns into «ЙНННННН».

One program speaks one encoding: `StreamDecoder` decides once, by the first line that tells, and keeps to it - a short line
after it («Да», «ОК») is not guessed again, so the lines of one program are not read in two encodings.
"""
from __future__ import annotations

import locale

# The letters of Russian from the most frequent to the rarest: a letter weighs by its place.
FREQUENT = set("оеаинтсрвлкмдпу")
MIDDLE = set("яыьгзбчйхжш")
# Signs a Russian text of a program has besides letters: they neither help nor hurt.
NEUTRAL = set("«»—–№…‘’“”°·• ")
# The drawing of a console's tables and the blocks of a progress bar.
BOX = {chr(code) for code in range(0x2500, 0x25A0)}
VOWELS = set("аеёиоуыэюя")
# The blocks of Unicode a text of UTF-16 decodes into when its order of bytes is right.
PLAUSIBLE = ((0x00A0, 0x024F), (0x0400, 0x052F), (0x2000, 0x2BFF), (0x2E80, 0x9FFF), (0xAC00, 0xD7AF), (0xF900, 0xFAFF),
             (0xFE30, 0xFFEF), (0x1F300, 0x1FAFF))
# The signs past ASCII a line of UTF-8 may hold alone and still be taken for UTF-8 for sure.
USUAL = NEUTRAL | BOX | set("✓✔✗✘→←↑↓€©®™‹›−×÷±≤≥≈∙√")
# The words of one letter Russian has; «ь» alone is cp866 «№» read as cp1251.
ONE_LETTER = set("авикосуяж")
# The bytes below the space that a text of one byte a sign has not: no tab, no line ends, no ESC of the colour codes.
CONTROL = set(range(0x00, 0x09)) | {0x0B, 0x0C} | set(range(0x0E, 0x1B)) | set(range(0x1C, 0x20))
BOMS = ((b"\xef\xbb\xbf", "utf-8"), (b"\xff\xfe", "utf-16-le"), (b"\xfe\xff", "utf-16-be"))


def _single_byte_candidates() -> list[str]:
    """cp866 and cp1251, and the pages of this system when they are others."""
    pages = ["cp866", "cp1251"]
    for page in (locale.getpreferredencoding(False), _oem_page()):
        name = str(page or "").lower().replace("_", "-")
        if name and name not in pages and name not in {"utf-8", "utf8", "ascii"}:
            pages.append(name)
    return pages


def _oem_page() -> str:
    try:
        import ctypes

        return f"cp{ctypes.windll.kernel32.GetOEMCP()}"
    except Exception:  # noqa: BLE001 - not Windows: there is no OEM page to add
        return ""


def _plausible(text: str) -> bool:
    return all(ord(char) < 0x80 or any(low <= ord(char) <= high for low, high in PLAUSIBLE) for char in text)


def _sure_utf8(text: str) -> bool:
    """A valid line of UTF-8 that is UTF-8 for sure: it holds Cyrillic, or no sign past ASCII but the usual ones."""
    if any("\u0400" <= char <= "\u04ff" for char in text):
        return True
    return all(char.isascii() or char in USUAL for char in text)


def _russian_score(text: str) -> int:
    """How much a text looks like Russian written by a program: letters by their frequency; a capital in the middle of a
    word, a letter three times in a row and a sign that is neither a letter nor usual punctuation against it."""
    score = 0
    previous, run = "", 0
    word = ""
    for char in text + " ":
        low = char.lower()
        if "а" <= low <= "я" or low == "ё":
            word += low
        elif word:
            # A Russian word has a vowel: «схч» of cp1251 «без» read as cp866 has none; a word of one letter is one of a few.
            if len(word) >= 2 and not VOWELS & set(word):
                score -= 6 if len(word) >= 3 else 3
            elif len(word) == 1 and word not in ONE_LETTER:
                score -= 4
            word = ""
        run = run + 1 if char == previous else 1
        if "а" <= low <= "я" or low == "ё":
            score += 4 if low in FREQUENT else 2 if low in MIDDLE else 0
            if char.isupper() and previous.isalpha() and previous.islower():
                score -= 6
            if run >= 3:
                score -= 10
        elif ord(char) > 127 and char not in NEUTRAL and char not in BOX:
            score -= 2 if char.isalpha() else 6
        previous = char
    # The frame of a table stands by spaces and other strokes of the frame; one glued to a letter or a sign is a capital or a
    # quote of cp1251 read as cp866 («(JSON)╗», «╘ыру»).
    for index, char in enumerate(text):
        if char in BOX:
            for near in (text[index - 1] if index else " ", text[index + 1] if index + 1 < len(text) else " "):
                if not near.isspace() and near not in BOX:
                    score -= 3
    return score


def _text_score(text: str) -> int:
    """How much a decoded text is text: ASCII words and Cyrillic letters for, signs below the space against."""
    score = 0
    for char in text:
        if char.isascii():
            score += 1 if char.isprintable() else -4 if char not in "\r\n\t\x1b" else 0
        elif "Ѐ" <= char <= "ӿ":
            score += 2
        elif char in BOX:
            score += 1
    return score


# The high bytes of the signs programs write in UTF-16: Latin, Cyrillic, punctuation, the drawing of tables.
HIGH_BYTES = {0x00, 0x04, 0x20, 0x25}


def _utf16(data: bytes) -> str | None:
    """utf-16-le / utf-16-be when the bytes are UTF-16: many bytes below the space (the high bytes of the signs - 0 of the
    Latin ones, 4 of the Cyrillic), or one side of the pairs made of the high bytes alone (a frame of a table, 0x25), and an
    order that decodes into a text of the signs programs write."""
    if len(data) < 2:
        return None
    controls = sum(1 for byte in data if byte in CONTROL) >= max(1, len(data) // 5)
    highs = len(data) >= 6 and any(sum(1 for byte in side if byte in HIGH_BYTES) >= len(side) * 0.9
                                   for side in (data[0::2], data[1::2]))
    if not controls and not highs:
        return None
    best = None
    for name in ("utf-16-le", "utf-16-be"):
        piece = _aligned(data, name)
        try:
            text = piece.decode(name)
        except UnicodeDecodeError:
            continue
        if not _plausible(text):
            continue
        score = _text_score(text)
        if best is None or score > best[0]:
            best = (score, name)
    return best[1] if best and best[0] > 0 else None


def _aligned(data: bytes, name: str) -> bytes:
    """A piece of UTF-16-LE as a pipe gives it line by line: the zero of the line feed before opens it, its own line feed
    lacks its zero."""
    if name == "utf-16-le":
        if len(data) % 2 and data.startswith(b"\x00"):
            data = data[1:]
        if len(data) % 2 and data.endswith(b"\n"):
            data += b"\x00"
    return data


def guess(data: bytes) -> tuple[str, bool]:
    """The encoding of a piece of output and whether the piece told it for sure (a stream keeps to a sure one)."""
    if not data:
        return "utf-8", False
    for mark, name in BOMS:
        if data.startswith(mark):
            return name, True
    wide = _utf16(data)
    if wide:
        return wide, True
    if max(data) < 0x80:
        return "ascii", False
    scored = []
    try:
        text = data.decode("utf-8")
        if _sure_utf8(text):
            return "utf-8", True
        scored.append((_russian_score(text), "utf-8"))
    except UnicodeDecodeError:
        pass
    for page in _single_byte_candidates():
        try:
            scored.append((_russian_score(data.decode(page)), page))
        except (LookupError, UnicodeDecodeError):
            continue
    if not scored:
        return "utf-8", False
    scored.sort(key=lambda item: item[0], reverse=True)
    best, page = scored[0]
    runner_up = scored[1][0] if len(scored) > 1 else best - 100
    # Sure only when the text is clearly Russian in one page and not in the other; a line of two letters stays a guess.
    return page, best - runner_up >= 8


def _decode(data: bytes, encoding: str) -> str:
    for mark, name in BOMS:
        if name == encoding and data.startswith(mark):
            data = data[len(mark):]
    data = _aligned(data, encoding)
    try:
        return data.decode(encoding)
    except LookupError:
        return data.decode("utf-8", errors="replace")
    except UnicodeDecodeError:
        return data.decode(encoding, errors="replace")


class StreamDecoder:
    """The lines of one program: the encoding is decided by the first line that tells it and kept to. `encoding` - the
    encoding of a known program, given by whoever runs it: nothing is guessed then."""

    def __init__(self, encoding: str | None = None) -> None:
        self.encoding = (encoding or "").lower()
        self.fixed = bool(encoding)
        # UTF-16-LE read line by line: the zero of the last line feed comes at the start of the next piece.
        self._zero_due = False

    def decode(self, data: bytes) -> str:
        data = bytes(data)
        if not data:
            return ""
        if self.encoding == "utf-16-le":
            data = self._carried(data)
        if self.fixed:
            return _decode(data, self.encoding)
        if self.encoding:
            try:
                return _decode_strict(data, self.encoding)
            except UnicodeDecodeError:
                # A piece that is not in the kept encoding is read by its own look and does not change what is kept.
                return _decode(data, guess(data)[0])
        encoding, sure = guess(data)
        if sure:
            self.encoding = encoding
            if encoding == "utf-16-le":
                data = self._carried(data)
        return _decode(data, encoding)

    def _carried(self, data: bytes) -> bytes:
        if self._zero_due and data.startswith(b"\x00"):
            data = data[1:]
        self._zero_due = data.endswith(b"\n") and len(data) % 2 == 1
        return data + b"\x00" if self._zero_due else data


def _decode_strict(data: bytes, encoding: str) -> str:
    for mark, name in BOMS:
        if name == encoding and data.startswith(mark):
            data = data[len(mark):]
    return _aligned(data, encoding).decode(encoding)


def decode_process_bytes(data: bytes, encoding: str | None = None) -> str:
    """One piece of output on its own, by the same rules."""
    return StreamDecoder(encoding).decode(data)


def decode_process_output(data: bytes) -> str:
    return decode_process_bytes(data)
