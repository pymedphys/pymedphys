# Copyright (C) 2026 Matthew Jennings

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Read a page's UserUnit from a one-page PDF as PDFium writes it (D-061).

PDFium ignores a page's UserUnit (ISO 32000-1 Table 30) and gives no way to
read it, so :mod:`.encapsulated_documents` has PDFium write the page alone
into a new document, which PDFium saves whole: every object written as an
indirect object, none in an object stream, with a cross-reference table.
:func:`page_user_unit` reads that file as its structure gives it, from the
trailer's Root, through the catalogue's Pages and their one kid, to that
page's own dictionary, and reads UserUnit from that dictionary alone, never
from a string, a stream, a nested dictionary, or another object, so that an
annotation's text that quotes PDF syntax cannot be taken for the page's
setting.

The objects are read by the syntax of ISO 32000-1 Sections 7.2 and 7.3:
white space and comments, booleans, numbers, literal and hexadecimal
strings, names with their ``#`` escapes, arrays, dictionaries, the null
object, and indirect references. Whatever the file holds that this does
not read as that structure, such as a cross-reference stream, a page tree
of more than one page, or a value nested too deeply, raises ValueError, so
that the document is refused rather than read otherwise.

This module is pure Python, and runs in the decoding child with PDFium.
"""

from __future__ import annotations

import dataclasses
import math
import re

# ISO 32000-1 Table 1 and Table 2.
_WHITE_SPACE = b"\x00\t\n\x0c\r "
_DELIMITERS = b"()<>[]{}/%"
# How deeply arrays and dictionaries may nest, and how many references a
# UserUnit may pass through, before the file is refused.
_MAX_DEPTH = 64
_MAX_REFERENCES = 8
_NUMBER = re.compile(rb"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)")
_INTEGER = re.compile(rb"[0-9]+")
_STARTXREF = re.compile(rb"startxref[\x00\t\n\x0c\r ]+([0-9]+)[\x00\t\n\x0c\r ]")


class Name(str):
    """A PDF name, without its solidus and with its escapes decoded."""


class String(bytes):
    """A PDF string, literal or hexadecimal, as written; never decoded."""


@dataclasses.dataclass(frozen=True)
class Reference:
    """An indirect reference, ``number generation R``."""

    number: int
    generation: int


def page_user_unit(saved: bytes) -> float:
    """Return the UserUnit of the one page of ``saved``, 1 where it has none.

    Parameters
    ----------
    saved : bytes
        A one-page PDF as PDFium saves it whole.

    Raises
    ------
    ValueError
        If the file is not read as the module describes, or the page's
        UserUnit is not a positive, finite number.
    """
    file = _File(saved)
    catalogue = file.dictionary(file.trailer().get("Root"))
    pages = file.dictionary(catalogue.get("Pages"))
    kids = file.resolved(pages.get("Kids"))
    if not isinstance(kids, list) or len(kids) != 1:
        raise ValueError("page tree")
    page = file.dictionary(kids[0])
    if page.get("Type") != Name("Page"):
        raise ValueError("page")
    unit = file.resolved(page.get("UserUnit"))
    if unit is None:
        return 1.0
    if isinstance(unit, bool) or not isinstance(unit, (int, float)):
        raise ValueError("user unit")
    unit = float(unit)
    if not (math.isfinite(unit) and unit > 0):
        raise ValueError("user unit")
    return unit


class _File:
    """A PDF with a cross-reference table, whose objects are read on demand."""

    def __init__(self, data: bytes) -> None:
        self.data = data
        found = list(_STARTXREF.finditer(data))
        if not found:
            raise ValueError("startxref")
        position = int(found[-1].group(1))
        position = self._keyword(position, b"xref")
        self.offsets: dict[int, int] = {}
        while True:
            position = self._skip(position)
            if data.startswith(b"trailer", position):
                self.trailer_at = position + len(b"trailer")
                break
            first, position = self._integer(position)
            count, position = self._integer(position)
            for number in range(first, first + count):
                offset, position = self._integer(position)
                _, position = self._integer(position)
                position = self._skip(position)
                kind = data[position : position + 1]
                if kind not in (b"n", b"f"):
                    raise ValueError("xref")
                position += 1
                if kind == b"n":
                    self.offsets[number] = offset

    def trailer(self) -> dict:
        trailer, _ = _Reader(self.data).value(self.trailer_at)
        if not isinstance(trailer, dict):
            raise ValueError("trailer")
        return trailer

    def resolved(self, value):
        """``value``, or the object it refers to, through each reference."""
        for _ in range(_MAX_REFERENCES):
            if not isinstance(value, Reference):
                return value
            value = self._object(value)
        raise ValueError("references")

    def dictionary(self, value) -> dict:
        value = self.resolved(value)
        if not isinstance(value, dict):
            raise ValueError("dictionary")
        return value

    def _object(self, reference: Reference):
        """The object that ``reference`` names, or None where the file has
        no such object, which a reference to no object is (ISO 32000-1
        Section 7.3.10)."""
        offset = self.offsets.get(reference.number)
        if offset is None:
            return None
        number, position = self._integer(offset)
        generation, position = self._integer(position)
        if (number, generation) != (reference.number, reference.generation):
            raise ValueError("object")
        position = self._keyword(position, b"obj")
        value, _ = _Reader(self.data).value(position)
        return value

    def _skip(self, position: int) -> int:
        return _Reader(self.data).skip(position)

    def _keyword(self, position: int, keyword: bytes) -> int:
        position = self._skip(position)
        if not self.data.startswith(keyword, position):
            raise ValueError(keyword.decode("ascii"))
        return position + len(keyword)

    def _integer(self, position: int) -> tuple[int, int]:
        position = self._skip(position)
        match = _INTEGER.match(self.data, position)
        if match is None:
            raise ValueError("integer")
        return int(match.group()), match.end()


class _Reader:
    """Reads one PDF object from bytes, by ISO 32000-1 Sections 7.2 and 7.3."""

    def __init__(self, data: bytes) -> None:
        self.data = data

    def skip(self, position: int) -> int:
        """The position after any white space and comments."""
        data = self.data
        while position < len(data):
            byte = data[position]
            if byte in _WHITE_SPACE:
                position += 1
            elif byte == ord("%"):
                while position < len(data) and data[position] not in b"\r\n":
                    position += 1
            else:
                break
        return position

    def value(self, position: int, depth: int = 0):
        """Return the object at ``position``, and the position after it."""
        if depth > _MAX_DEPTH:
            raise ValueError("depth")
        data = self.data
        position = self.skip(position)
        if data.startswith(b"<<", position):
            return self._dictionary(position + 2, depth)
        opened = {
            b"[": self._array,
            b"(": self._literal,
            b"<": self._hexadecimal,
            b"/": self._name,
        }.get(data[position : position + 1])
        if opened is not None:
            return opened(position + 1, depth)
        match = _NUMBER.match(data, position)
        if match is not None:
            return self._number_or_reference(match)
        return self._keyword(position)

    def _keyword(self, position: int):
        word = self._regular(position)
        keywords = {b"true": True, b"false": False, b"null": None}
        if word not in keywords:
            raise ValueError("object")
        return keywords[word], position + len(word)

    def _hexadecimal(self, position: int, depth: int):
        del depth
        end = self.data.find(b">", position)
        if end < 0:
            raise ValueError("hexadecimal string")
        return String(self.data[position:end]), end + 1

    def _dictionary(self, position: int, depth: int):
        found: dict[str, object] = {}
        while True:
            position = self.skip(position)
            if self.data.startswith(b">>", position):
                return found, position + 2
            key, position = self.value(position, depth + 1)
            if not isinstance(key, Name):
                raise ValueError("key")
            found[str(key)], position = self.value(position, depth + 1)

    def _array(self, position: int, depth: int):
        found = []
        while True:
            position = self.skip(position)
            if self.data[position : position + 1] == b"]":
                return found, position + 1
            if position >= len(self.data):
                raise ValueError("array")
            item, position = self.value(position, depth + 1)
            found.append(item)

    def _literal(self, position: int, depth: int):
        del depth
        data = self.data
        start = position
        nesting = 1
        while position < len(data):
            byte = data[position]
            if byte == ord("\\"):
                position += 2
                continue
            if byte == ord("("):
                nesting += 1
            elif byte == ord(")"):
                nesting -= 1
                if nesting == 0:
                    return String(data[start:position]), position + 1
            position += 1
        raise ValueError("literal string")

    def _name(self, position: int, depth: int = 0):
        del depth
        raw = self._regular(position)
        try:
            name = re.sub(
                rb"#([0-9A-Fa-f]{2})",
                lambda match: bytes.fromhex(match[1].decode()),
                raw,
            )
            return Name(name.decode("latin-1")), position + len(raw)
        except ValueError:
            raise ValueError("name") from None

    def _number_or_reference(self, match: re.Match):
        text = match.group()
        position = match.end()
        if _INTEGER.fullmatch(text):
            # number generation R
            after = self.skip(position)
            generation = _INTEGER.match(self.data, after)
            if generation is not None:
                keyword = self.skip(generation.end())
                if self.data[keyword : keyword + 1] == b"R" and not self._regular(
                    keyword + 1
                ):
                    return (
                        Reference(int(text), int(generation.group())),
                        keyword + 1,
                    )
            if self._regular(position):
                raise ValueError("number")
            return int(text), position
        if self._regular(position):
            raise ValueError("number")
        return float(text), position

    def _regular(self, position: int) -> bytes:
        """The run of regular characters from ``position``."""
        data = self.data
        end = position
        while (
            end < len(data)
            and data[end] not in _WHITE_SPACE
            and data[end] not in _DELIMITERS
        ):
            end += 1
        return data[position:end]
