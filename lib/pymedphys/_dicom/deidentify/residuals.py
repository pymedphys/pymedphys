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

"""Search a written DICOM file for source values that should not be in it.

A source value that de-identification had to remove or replace can survive
outside the attribute that held it: in the preamble or File Meta Information
(PS3.15 Section E.1.1), a private or binary value, Data Set Trailing Padding,
or bytes after the data set. :func:`find_residuals` searches every byte of a
written file for each such value, and reports each one it finds by the
value's kind, its source attribute, the form and encoding found, and the
place in the file that :func:`~.file_layout.read_file_layout` gives. It lists
what it did not search, and why. Whether a file may be released is for its
caller to decide.

**Forms.** A value is normalised to NFC, split at backslashes unless its VR
is LT, ST, UR, or UT, and stripped of spaces, NULs, and whitespace at either
end. A person name (PN) is searched whole, by each component group, and by
its family, given, and middle names; where the family or given name is
shorter than :data:`MIN_CHARACTERS`, also as "GIVEN FAMILY", "FAMILY GIVEN",
and "FAMILY, GIVEN". A date (DA) is also searched as YYYY-MM-DD, and a
datetime (DT) by its date in both forms. A UID (UI) or text (AE, LO, LT, SH,
ST, UC, UR, or UT) is searched as it is, by up to its first
:data:`MAX_CHARACTERS` characters. Forms shorter than :data:`MIN_CHARACTERS`
are not searched, nor are binary values or the codes, numbers, ages, times,
and tags that occur throughout files (AS, AT, CS, DS, FD, FL, IS, SL, SS, SV,
TM, UL, US, and UV).

**Encodings.** Each form is searched in UTF-8, ISO 8859-1, UTF-16LE, and the
source's character set, except where the source's character set needs ISO
2022 escape sequences for it, since their bytes depend on the text around
them. ASCII letters match in either case, and text with other letters is
also searched in upper and lower case.

**Matching.** Letters and digits are those of ASCII; in UTF-16LE each
neighbouring character is two bytes. A match is rejected where a digit
precedes a form that starts with a digit, as in a 39-digit component of a
``2.25.`` UID; where a digit follows a form that ends with one, unless the
form is a date or datetime, which a time may follow, or the first characters
of a longer value; where a letter adjoins a person name form at an edge that
is a letter, as "MARY" in "PRIMARY"; and, for a form of digits alone, inside
a DS or IS value, such as contour data. Values that hold numbers (native
Pixel Data, Float Pixel Data, and Double Float Pixel Data of the top-level
data set, and values of VR OD, OF, OL, OV, and OW) are searched only for
forms of at least :data:`MIN_BYTES_IN_NUMBERS` bytes that are not UTF-16LE,
since shorter forms and UTF-16LE text match sample values by chance. Every
other byte, including encapsulated fragments and bytes that could not be read
as elements, is searched for every form.

**Reporting.** Each source attribute is reported once for each place it is
found, by the widest form there, in the order of :class:`Form`, with the
encoding and offset of that form's first match there. Places are named as
:class:`~.file_layout.Location` names them, with items numbered from 0, as
pydicom indexes them: ``(300A,00B0)[1]`` is the second item of Beam Sequence.
Results hold attribute paths, kinds, forms, VRs, codec names, and offsets,
never a value or its bytes, and nothing is logged or warned.
"""

from __future__ import annotations

import bisect
import dataclasses
import datetime
import enum
import functools
import mmap
import string
import unicodedata
from collections.abc import Iterable, Iterator

from .file_layout import ElementPath, Location, Region, Span, read_file_layout
from .values import CHECKED_VRS

MIN_CHARACTERS = 4  # the shortest form searched
MIN_BYTES_IN_NUMBERS = 8  # the shortest form searched in values that hold numbers
MAX_CHARACTERS = 256  # longer values are searched by their first 256 characters
CODECS = ("utf-8", "latin-1", "utf-16-le")
CHUNK_BYTES = 64 * 2**20  # the bytes lower-cased at a time
_PREFIX_BYTES = 6  # forms that start with the same bytes are searched together

_BINARY = frozenset({"OB", "OD", "OF", "OL", "OV", "OW", "UN"})
_SINGLE_VALUED = frozenset({"LT", "ST", "UR", "UT"})
_NUMBERS = frozenset({"OD", "OF", "OL", "OV", "OW"})
_PIXEL_DATA = frozenset({"(7FE0,0008)", "(7FE0,0009)", "(7FE0,0010)"})
_DIGITS = frozenset(string.digits.encode())
_LETTERS = frozenset(string.ascii_letters.encode())
_PADDING = "\x00" + string.whitespace
_ASCII = bytes(range(0x20, 0x7F)).decode("ascii")


class ValueKind(enum.Enum):
    """What a source value is, from its VR."""

    PERSON_NAME = "person-name"  # PN
    UID = "uid"  # UI
    DATE = "date"  # DA
    DATETIME = "datetime"  # DT
    TEXT = "text"  # AE, LO, LT, SH, ST, UC, UR, and UT


_KINDS = dict.fromkeys(("AE", "LO", "LT", "SH", "ST", "UC", "UR", "UT"), ValueKind.TEXT)
_KINDS.update(PN=ValueKind.PERSON_NAME, UI=ValueKind.UID, DA=ValueKind.DATE)
_KINDS.update(DT=ValueKind.DATETIME)
_DATES = (ValueKind.DATE, ValueKind.DATETIME)


class Form(enum.Enum):
    """How a source value was written where it is found, widest first."""

    VALUE = "value"  # the whole value
    NAME_GROUP = "name-group"  # a component group of a person name
    NAME_JOINED = "name-joined"  # family and given names, where one is short
    NAME_COMPONENT = "name-component"  # a family, given, or middle name
    DATE_DICOM = "date-yyyymmdd"  # the date of a datetime
    DATE_ISO = "date-iso"  # a date as YYYY-MM-DD


_ORDER = {form: index for index, form in enumerate(Form)}


class Omission(enum.Enum):
    """Why a form was not searched."""

    TOO_SHORT = "too-short"  # shorter than MIN_CHARACTERS characters
    NOT_DISTINCTIVE = "not-distinctive"  # a code, number, age, time, or tag
    BINARY = "binary"  # a value of VR OB, OD, OF, OL, OV, OW, or UN
    CODE_EXTENSIONS = "code-extensions"  # needs ISO 2022 escape sequences


def _words(member: enum.Enum) -> str:
    return "UID" if member is ValueKind.UID else member.value.replace("-", " ")


@dataclasses.dataclass(frozen=True, repr=False)
class SourceValue:
    """A value that de-identification removed or replaced, to search for.

    Its ``repr`` leaves out the value, and its errors name only the source.

    Attributes
    ----------
    source : ElementPath
        Where the value was in the source data set or File Meta Information.
    vr : str
        Its VR, which can be any but SQ.
    value : str or bytes
        The decoded value, with multiple values separated by backslashes;
        for a person name, ``str(PersonName)``. Bytes only for a VR that is
        not searched, such as OB.
    codecs : tuple of str
        The Python codecs of the source's Specific Character Set (0008,0005),
        as pydicom names them; each must encode ASCII as ASCII.

    Raises
    ------
    ValueError
        If an attribute is not one of these.

    Examples
    --------
    >>> SourceValue(ElementPath((), "(0010,0010)"), "PN", "ZEBEDEE^QUILLON")
    SourceValue(source='(0010,0010)', vr='PN')
    """

    source: ElementPath
    vr: str
    value: str | bytes
    codecs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.source, ElementPath):
            raise ValueError("a source value needs the ElementPath of its source")
        problem = self._problem()
        if problem:
            raise ValueError(f"the source value from {self.source} {problem}")

    def _problem(self) -> str | None:
        if not isinstance(self.vr, str) or self.vr not in CHECKED_VRS:
            return "needs a VR other than SQ"
        if not isinstance(self.value, str if self.vr in _KINDS else (str, bytes)):
            return "needs text for a VR that is searched, or else text or bytes"
        if isinstance(self.value, str) and not _encodes(self.value, "utf-8"):
            return "is not valid Unicode text"
        if not isinstance(self.codecs, tuple) or not all(
            isinstance(codec, str) and _encodes(_ASCII, codec, _ASCII.encode())
            for codec in self.codecs
        ):
            return "needs a tuple of text codecs that encode ASCII as ASCII"
        return None

    def __repr__(self) -> str:
        return f"SourceValue(source={str(self.source)!r}, vr={self.vr!r})"


def _encodes(text: str, codec: str, expected: bytes | None = None) -> bool:
    """Return whether ``codec`` encodes ``text``, as ``expected`` if given."""
    try:
        encoded = text.encode(codec)
    except (LookupError, ValueError):  # ValueError includes UnicodeError
        return False
    return expected is None or encoded == expected


@dataclasses.dataclass(frozen=True)
class Finding:
    """A source value found in a written file.

    Attributes
    ----------
    source : ElementPath
        Where the value was in the source.
    kind : ValueKind
    form : Form
        The widest form found at this location.
    encoding : str
        The codec of that form's first match here.
    location : Location
        Where it was found in the written file.
    offset : int
        The byte at which that match starts.
    """

    source: ElementPath
    kind: ValueKind
    form: Form
    encoding: str
    location: Location
    offset: int

    def __str__(self) -> str:
        """Describe the finding by its source, form, encoding, and place."""
        return (
            f"{_words(self.kind)} from {self.source} found as {_words(self.form)}, "
            f"{self.encoding}, in {self.location} at byte {self.offset}"
        )


@dataclasses.dataclass(frozen=True)
class NotSearched:
    """A form of a source value that was not searched, and why.

    Attributes
    ----------
    source : ElementPath
    vr : str
    form : Form
    reason : Omission
    encoding : str, optional
        For code extensions, the codec it was not searched in.
    """

    source: ElementPath
    vr: str
    form: Form
    reason: Omission
    encoding: str | None = None

    def __str__(self) -> str:
        """Describe the omission by its source, VR, form, and reason."""
        codec = f" in {self.encoding}" if self.encoding else ""
        return (
            f"{self.vr} from {self.source}: {_words(self.form)} not searched: "
            f"{_words(self.reason)}{codec}"
        )


@dataclasses.dataclass(frozen=True)
class ResidualSearch:
    """What a search of a written file found.

    Attributes
    ----------
    findings : tuple of Finding
        In the order of their offsets.
    not_searched : tuple of NotSearched
        Each once, in the order of the values.
    readable : bool
        Whether the file's structure was read to its end. Bytes that could
        not be read were searched as bytes after the last readable element.
    """

    findings: tuple[Finding, ...]
    not_searched: tuple[NotSearched, ...]
    readable: bool


def find_residuals(
    data: bytes | bytearray | memoryview | mmap.mmap, values: Iterable[SourceValue]
) -> ResidualSearch:
    """Search a written file for source values, as the module describes.

    Parameters
    ----------
    data : bytes, bytearray, memoryview, or mmap.mmap
        The whole written file. A memory map is read a chunk at a time.
    values : iterable of SourceValue
        The values that had to be removed or replaced, such as the
        instance's own and its subject's from the run's other instances.
        Repeated values are searched once.

    Returns
    -------
    ResidualSearch

    Raises
    ------
    ValueError
        If the transfer syntax deflates the data set.
    TypeError
        If a value is not a :class:`SourceValue`.

    Examples
    --------
    >>> name = SourceValue(ElementPath((), "(0010,0010)"), "PN", "ZEBEDEE^QUILLON")
    >>> result = find_residuals(b"Dr Zebedee", [name])
    >>> print(result.findings[0])  # doctest: +NORMALIZE_WHITESPACE
    person name from (0010,0010) found as name component, utf-8, in bytes
    after the last readable element at byte 3
    """
    layout = read_file_layout(data)
    derived = [item for value in dict.fromkeys(values) for item in _derive(value)]
    needles = [item for item in derived if isinstance(item, _Needle)]
    omitted = [item for item in derived if isinstance(item, NotSearched)]
    with memoryview(data) as view, view.cast("B") as octets:
        found = _search(octets, layout.spans, layout.size, needles)
    order = sorted(
        found.values(), key=lambda f: (f.offset, str(f.source), f.kind.value)
    )
    return ResidualSearch(tuple(order), tuple(dict.fromkeys(omitted)), layout.readable)


@dataclasses.dataclass(frozen=True, repr=False)
class _Needle:
    """An encoded form to search for, which never leaves this module."""

    folded: bytes  # with ASCII letters in lower case
    origin: tuple[ElementPath, ValueKind, Form, str]  # a Finding's first fields
    wide: bool  # whether it is UTF-16LE, with two bytes to a character
    before: frozenset[int]  # the characters that reject a match before it
    after: frozenset[int]  # and after it
    digits: bool  # whether the form is digits alone


def _derive(value: SourceValue) -> Iterator[_Needle | NotSearched]:
    """Yield the needles of a value, and the forms of it not searched."""
    if not isinstance(value, SourceValue):
        raise TypeError("each value to search for must be a SourceValue")
    omission = functools.partial(NotSearched, value.source, value.vr)
    kind = _KINDS.get(value.vr)
    if kind is None:
        reason = Omission.BINARY if value.vr in _BINARY else Omission.NOT_DISTINCTIVE
        yield omission(Form.VALUE, reason)
        return
    seen: set[bytes] = set()
    for form, text in _forms(str(value.value), value.vr, kind):
        if len(text) < MIN_CHARACTERS:
            if text:
                yield omission(form, Omission.TOO_SHORT)
            continue
        # A time can follow a date, and anything the first characters of a
        # longer value.
        open_end = kind in _DATES or len(text) > MAX_CHARACTERS
        text, word = text[:MAX_CHARACTERS], kind is ValueKind.PERSON_NAME
        before = _edge(text[0], word)
        after = frozenset() if open_end else _edge(text[-1], word)
        digits = text.isascii() and text.isdigit()
        for codec, encoded in _encodings(text, value.codecs):
            if b"\x1b" in encoded and codec not in CODECS:
                yield omission(form, Omission.CODE_EXTENSIONS, codec)
            elif encoded.lower() not in seen:
                seen.add(encoded.lower())
                origin, wide = (value.source, kind, form, codec), codec == "utf-16-le"
                yield _Needle(encoded.lower(), origin, wide, before, after, digits)


def _forms(text: str, vr: str, kind: ValueKind) -> Iterator[tuple[Form, str]]:
    """Yield each form of a value, widest first, some of them empty."""
    text = unicodedata.normalize("NFC", text)
    for one in [text] if vr in _SINGLE_VALUED else text.split("\\"):
        one = one.strip(_PADDING)
        if kind is not ValueKind.PERSON_NAME:
            yield Form.VALUE, one
            iso = _iso_date(one[:8]) if kind in _DATES else None
            if iso and kind is ValueKind.DATETIME:
                yield Form.DATE_DICOM, one[:8]
            if iso:
                yield Form.DATE_ISO, iso
            continue
        yield Form.VALUE, one.rstrip("=^ ")
        for group in one.split("="):
            group = group.strip(_PADDING).rstrip("^ ")
            parts = [part.strip(_PADDING) for part in group.split("^")]
            family, given, middle = (parts + ["", ""])[:3]
            yield Form.NAME_GROUP, group
            if family and given and min(len(family), len(given)) < MIN_CHARACTERS:
                yield Form.NAME_JOINED, f"{given} {family}"
                yield Form.NAME_JOINED, f"{family} {given}"
                yield Form.NAME_JOINED, f"{family}, {given}"
            for part in (family, given, middle):
                yield Form.NAME_COMPONENT, part


def _iso_date(date: str) -> str | None:
    """Return a valid YYYYMMDD date as YYYY-MM-DD, or ``None``."""
    if not (len(date) == 8 and date.isascii() and date.isdigit()):
        return None
    try:
        return datetime.date.fromisoformat(date).isoformat()
    except ValueError:
        return None


def _edge(char: str, word: bool) -> frozenset[int]:
    """Return the neighbouring characters that reject a match at ``char``."""
    if char in string.digits:
        return _DIGITS
    if word and char in string.ascii_letters:
        return _LETTERS
    return frozenset()


def _encodings(text: str, codecs: tuple[str, ...]) -> Iterator[tuple[str, bytes]]:
    """Yield each codec, and each case of ``text`` that it can encode."""
    for codec in dict.fromkeys((*CODECS, *codecs)):
        for variant in dict.fromkeys((text, text.upper(), text.lower())):
            try:
                encoded = variant.encode(codec)
            except UnicodeEncodeError:
                continue
            yield codec, encoded


def _holds_numbers(span: Span) -> bool:
    where, path = span.location, span.location.element
    if where.region is not Region.DATA_SET or path is None or where.item is not None:
        return False
    return where.vr in _NUMBERS or (not path.items and path.tag in _PIXEL_DATA)


_Found = dict[tuple[ElementPath, ValueKind, Location], Finding]


def _search(
    octets: memoryview, spans: tuple[Span, ...], size: int, needles: list[_Needle]
) -> _Found:
    """Return the first finding of the widest form of each source in each place.

    Needles that start with the same bytes are found together, and each
    match of those bytes is checked against each of them.
    """
    starts = [span.start for span in spans]
    text: list[tuple[int, int]] = []  # the ranges outside values that hold numbers
    position = 0
    for span in spans:
        if span.value_start is not None and _holds_numbers(span):
            text.append((position, span.value_start))
            position = span.end
    text.append((position, size))
    groups: dict[tuple[bytes, bool], list[int]] = {}
    for index, needle in enumerate(needles):
        everywhere = not needle.wide and len(needle.folded) >= MIN_BYTES_IN_NUMBERS
        groups.setdefault((needle.folded[:_PREFIX_BYTES], everywhere), []).append(index)
    resume = [0] * len(needles)  # where each needle's next match can start
    found: _Found = {}
    longest = max((len(needle.folded) for needle in needles), default=1)
    for chunk in range(0, size if needles else 0, CHUNK_BYTES):
        stop = min(chunk + CHUNK_BYTES, size)
        block = bytes(octets[chunk : stop + longest - 1]).lower()
        clipped = [(max(low, chunk), min(high, stop)) for low, high in text]
        ranges = {True: [(chunk, stop)], False: [(a, b) for a, b in clipped if a < b]}
        searches = (
            (prefix, members, low, high)
            for (prefix, everywhere), members in groups.items()
            for low, high in ranges[everywhere]
        )
        for prefix, members, low, high in searches:
            end = high - chunk + len(prefix) - 1  # matches start before high
            position = block.find(prefix, low - chunk, end)
            while position != -1:
                offset = chunk + position
                for index in members:
                    needle = needles[index]
                    if resume[index] <= offset and block.startswith(
                        needle.folded, position
                    ):
                        span = spans[bisect.bisect_right(starts, offset) - 1]
                        resume[index] = _judge(octets, needle, offset, span, found)
                following = min(resume[index] for index in members) - chunk
                position = block.find(prefix, max(position + 1, following), end)
    return found


def _judge(
    octets: memoryview, needle: _Needle, offset: int, span: Span, found: _Found
) -> int:
    """Record a match at ``offset`` if it counts; return where to search next.

    After a match that counts, or one of digits alone in a DS or IS value,
    the needle's search moves on to the end of the element.
    """
    if needle.digits and span.location.vr in ("DS", "IS"):
        return span.end
    width = 2 if needle.wide else 1
    if (
        _character(octets, offset - width, width) in needle.before
        or _character(octets, offset + len(needle.folded), width) in needle.after
    ):
        return offset + 1
    source, kind, form, _ = needle.origin
    key = (source, kind, span.location)
    best = found.get(key)
    if best is None or (_ORDER[form], offset) < (_ORDER[best.form], best.offset):
        found[key] = Finding(*needle.origin, span.location, offset)
    return span.end


def _character(octets: memoryview, at: int, width: int) -> int:
    """Return the byte of the ASCII character at ``at``, or -1 if none."""
    if at < 0 or at + width > len(octets) or (width == 2 and octets[at + 1]):
        return -1
    return octets[at]
