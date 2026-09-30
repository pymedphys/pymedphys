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

"""Map every byte of a written DICOM file to where it belongs.

Verification must say where in a written file it finds something: in the
preamble, a File Meta Information element, a data set element, Data Set
Trailing Padding, or the bytes after the last element that could be read.
:func:`read_file_layout` reads a DICOM PS3.10 file's structure from its bytes
alone, independently of the library that wrote it.
"""

from __future__ import annotations

import bisect
import dataclasses
import enum
import functools
import mmap
import re
import struct

from .standard import VRS, load_data_dictionary
from .uids import normalise_uid

# The VRs whose explicit VR header is 8 bytes, with a 16-bit length (PS3.5
# Table 7.1-2). Every other VR's is 12 bytes, with a 32-bit length (Table 7.1-1).
VRS_WITH_16_BIT_LENGTH = frozenset(
    {"AE", "AS", "AT", "CS", "DA", "DS", "DT", "FL", "FD", "IS", "LO", "LT",
     "PN", "SH", "SL", "SS", "ST", "TM", "UI", "UL", "US"}
)  # fmt: skip
# Implicit VR Little Endian (PS3.5 Section A.1), and the retired Papyrus 3
# syntax that PS3.6 also names implicit VR little endian.
IMPLICIT_VR_TRANSFER_SYNTAXES = frozenset({"1.2.840.10008.1.2", "1.2.840.10008.1.20"})
# Explicit VR Big Endian, retired in 2006 (PS3.5 Section A.3).
BIG_ENDIAN_TRANSFER_SYNTAXES = frozenset({"1.2.840.10008.1.2.2"})
# Those that deflate the whole data set (PS3.5 Sections A.5, A.7, and A.12),
# unlike Deflated Image Frame Compression (Section A.4.13).
DEFLATED_TRANSFER_SYNTAXES = frozenset(
    {"1.2.840.10008.1.2.1.99", "1.2.840.10008.1.2.4.95", "1.2.840.10008.1.2.4.205"}
)
# The most items an element can be nested in and still be read, so that a
# file cannot make reading exhaust the stack.
MAX_NESTING = 32
TAG_PATTERN = re.compile(r"\([0-9A-F]{4},[0-9A-F]{4}\)")

_ITEM, _ITEM_END, _SEQUENCE_END = (0xFFFE, 0xE000), (0xFFFE, 0xE00D), (0xFFFE, 0xE0DD)
_PIXEL_DATA, _PADDING, _UNDEFINED = (0x7FE0, 0x0010), (0xFFFC, 0xFFFC), 0xFFFFFFFF
_Items = tuple[tuple[str, int], ...]


class Region(enum.Enum):
    """The parts of a file (PS3.10 Sections 7.1 and 7.2)."""

    PREAMBLE = "preamble"  # bytes 0 to 127
    FILE_META = "file-meta"  # the "DICM" prefix and the group 0002 elements
    DATA_SET = "data-set"
    TRAILING_PADDING = "trailing-padding"  # (FFFC,FFFC) outside any item
    TRAILING = "trailing-bytes"  # from where reading stopped to the end


@dataclasses.dataclass(frozen=True)
class ElementPath:
    """An element, and the sequence items that hold it.

    Attributes
    ----------
    items : tuple of (str, int)
        Each sequence's tag and item, counting from 0, outermost first.
    tag : str
        The element's tag, such as ``"(300A,00C3)"``.

    Raises
    ------
    ValueError
        Unless each tag is ``(gggg,eeee)`` in upper-case hexadecimal and each
        item an integer from 0.
    """

    items: _Items
    tag: str

    def __post_init__(self) -> None:
        try:
            valid = isinstance(self.items, tuple) and all(
                TAG_PATTERN.fullmatch(tag)
                and isinstance(item, int)
                and str(item).isdigit()
                for tag, item in (*self.items, (self.tag, 0))
            )
        except (TypeError, ValueError):  # an item that is not a tag and a number
            valid = False
        if not valid:
            raise ValueError("a path needs tags such as (300A,00C3) and items from 0")

    def __str__(self) -> str:
        """Return the path as, for example, ``(300A,00B0)[1] > (300A,00C3)``."""
        return " > ".join([*(f"{tag}[{item}]" for tag, item in self.items), self.tag])


_PLACES = {
    Region.PREAMBLE: "the preamble",
    Region.FILE_META: "the DICM prefix",
    Region.TRAILING: "bytes after the last readable element",
}


@dataclasses.dataclass(frozen=True)
class Location:
    """Where a byte belongs.

    Attributes
    ----------
    region : Region
    element : ElementPath, optional
        The element whose header or value holds the byte, including the
        headers and delimiters of the items in its value.
    vr : str, optional
        The VR as written in explicit VR, or, in implicit VR and in place of
        UN, the VR that PS3.6 gives the attribute. Where PS3.6 gives none or
        several, as for a private attribute, it is UN as written, or ``None``
        in implicit VR.
    item : int, optional
        The item of an encapsulated value, from 0, the Basic Offset Table.
    """

    region: Region
    element: ElementPath | None = None
    vr: str | None = None
    item: int | None = None

    def __str__(self) -> str:
        """Name the place, such as ``data set element (0010,0010) (PN)``."""
        if self.element is None:
            return _PLACES.get(self.region, self.region.value)
        if self.region is Region.TRAILING_PADDING:
            return f"Data Set Trailing Padding {self.element.tag}"
        part = (
            "File Meta Information" if self.region is Region.FILE_META else "data set"
        )
        place = f"{part} element {self.element}" + (f" ({self.vr})" if self.vr else "")
        return place if self.item is None else f"item {self.item} of {place}"


@dataclasses.dataclass(frozen=True)
class Span:
    """The bytes from ``start`` up to ``end``, which share a location.

    Attributes
    ----------
    start, end : int
    value_start : int, optional
        Where the value starts, after the header, in the span of an element
        or an encapsulated item; ``None`` in a span that holds only a header
        or delimiter, and outside elements.
    location : Location
    """

    start: int
    end: int
    value_start: int | None
    location: Location


@dataclasses.dataclass(frozen=True)
class FileLayout:
    """Where each byte of a file belongs.

    Attributes
    ----------
    size : int
        The file's length in bytes.
    transfer_syntax : str, optional
        Transfer Syntax UID (0002,0010) without padding, or ``None``. Like
        other values, it is left out of the repr.
    readable : bool
        Whether the whole file was read: ``False`` if any byte is trailing or
        the file ends inside a sequence or item.
    spans : tuple of Span
        Each starting where the one before ends, from 0 to ``size``.
    """

    size: int
    transfer_syntax: str | None = dataclasses.field(repr=False)
    readable: bool
    spans: tuple[Span, ...] = dataclasses.field(repr=False)

    def locate(self, offset: int) -> Location:
        """Return the location of the byte at ``offset``.

        Raises
        ------
        ValueError
            If ``offset`` is outside the file.
        """
        if not 0 <= offset < self.size:
            raise ValueError("the offset is outside the file")
        index = bisect.bisect_right(self.spans, offset, key=lambda span: span.start)
        return self.spans[index - 1].location


def read_file_layout(data: bytes | bytearray | memoryview | mmap.mmap) -> FileLayout:
    """Read where each byte of a DICOM PS3.10 file belongs.

    Every byte is trailing unless bytes 128 to 131 are "DICM" (PS3.10 Section
    7.1). The File Meta Information is read as Explicit VR Little Endian while
    the group is 0002, whatever its group length says. The data set is read
    as Implicit VR Little Endian (PS3.5 Section A.1) if Transfer Syntax UID
    (0002,0010) says so, left trailing if it is missing or big endian, and
    otherwise read as Explicit VR Little Endian (Sections A.2 and A.4).
    Headers follow PS3.5 Section 7.1, and items and their delimiters Section
    7.5. Pixel Data (7FE0,0010) of undefined length holds a Basic Offset Table
    and fragments (Section A.4). A value holds items if its VR is SQ, or, in
    implicit VR or VR UN, if PS3.6 gives its attribute VR SQ, or does not list
    the attribute and the value's length is undefined or the value reads as
    items to its end. Items in a value of VR UN are in implicit VR (Section
    6.2.2). Data Set Trailing Padding (FFFC,FFFC) in an item is a data set
    element (PS3.10 Section 7.2).

    Reading stops at the first structure that cannot be read, such as an
    unknown VR, an item where an element belongs, a length past the end of
    what holds it, or nesting deeper than :data:`MAX_NESTING`; the rest of the
    file is trailing. Only headers, the transfer syntax, and the first four
    bytes of some values are read, so the time taken grows with the number of
    elements and items, not with the size of their values.

    Parameters
    ----------
    data : bytes, bytearray, memoryview, or mmap.mmap
        The whole file. A memory map is read without loading the file.

    Returns
    -------
    FileLayout

    Raises
    ------
    ValueError
        If the transfer syntax deflates the data set.
    """
    with memoryview(data) as view, view.cast("B") as octets:
        return _Reader(octets).read()


class _Unreadable(Exception):
    """A structure that cannot be read, where reading stops."""


@functools.cache
def _dictionary() -> dict[str, tuple[str, ...]]:
    return {entry.tag: entry.vrs for entry in load_data_dictionary().attributes}


@functools.lru_cache(maxsize=4096)
def _dictionary_vrs(tag: str) -> tuple[str, ...]:
    """Return the VRs PS3.6 gives a standard attribute, or ``()``."""
    dictionary = _dictionary()
    if tag in dictionary or int(tag[4], 16) % 2:  # an odd group is private
        return dictionary.get(tag, ())
    # "x" stands for any digit of a repeating group or masked element.
    for listed, vrs in dictionary.items():
        if "x" in listed and all(a in ("x", b) for a, b in zip(listed, tag)):
            return vrs
    return ()


class _Reader:
    """Read the spans of a file in order, and stop where it cannot be read."""

    def __init__(self, data: memoryview) -> None:
        self.data = data
        self.spans: list[Span] = []
        self.region = Region.FILE_META

    def read(self) -> FileLayout:
        size = len(self.data)
        if self.data[128:132] != b"DICM":
            spans = (Span(0, size, None, Location(Region.TRAILING)),) if size else ()
            return FileLayout(size, None, False, spans)
        self._add(0, 128, None, Location(Region.PREAMBLE))
        position = self._add(128, 132, None, Location(Region.FILE_META))
        readable, syntax = True, None
        try:
            while self.data[position : position + 2] == b"\x02\x00":
                position = self._element(position, size, True, ())
        except _Unreadable:
            readable = False
        for span in self.spans:
            if str(span.location.element) == "(0002,0010)" and span.value_start:
                value = bytes(self.data[span.value_start : span.end])
                syntax = normalise_uid(value.decode("latin-1")) or None
        if syntax in DEFLATED_TRANSFER_SYNTAXES:
            raise ValueError("the data set is deflated, so its elements cannot be read")
        if readable and syntax and syntax not in BIG_ENDIAN_TRANSFER_SYNTAXES:
            self.region = Region.DATA_SET
            explicit = syntax not in IMPLICIT_VR_TRANSFER_SYNTAXES
            try:
                while position < size:
                    position = self._element(position, size, explicit, ())
            except _Unreadable:
                readable = False
        end = self.spans[-1].end
        if end < size:
            self._add(end, size, None, Location(Region.TRAILING))
        return FileLayout(size, syntax, readable and end == size, tuple(self.spans))

    def _unpack(self, form: str, position: int, end: int) -> tuple[int, ...]:
        if position + struct.calcsize(form) > end:
            raise _Unreadable
        return struct.unpack_from(form, self.data, position)

    def _add(self, start: int, end: int, value: int | None, where: Location) -> int:
        self.spans.append(Span(start, end, value, where))
        return end

    def _element(self, position: int, end: int, explicit: bool, items: _Items) -> int:
        """Read the element at ``position``, and return where it ends."""
        tag = self._unpack("<HH", position, end)
        if tag[0] == 0xFFFE:  # an item or delimiter where an element belongs
            raise _Unreadable
        vr = bytes(self.data[position + 4 : position + 6]).decode("latin-1")
        if not explicit:
            vr, header, (length,) = None, 8, self._unpack("<I", position + 4, end)
        elif vr in VRS_WITH_16_BIT_LENGTH:
            header, (length,) = 8, self._unpack("<H", position + 6, end)
        elif vr in VRS:
            header, (length,) = 12, self._unpack("<I", position + 8, end)
        else:
            raise _Unreadable
        path = ElementPath(items, "({:04X},{:04X})".format(*tag))
        known = _dictionary_vrs(path.tag) if vr in (None, "UN") else ()
        padding = tag == _PADDING and not items and self.region is Region.DATA_SET
        region = Region.TRAILING_PADDING if padding else self.region
        where = Location(region, path, known[0] if len(known) == 1 else vr)
        # Whether the value holds items: True, False, or None if it does only
        # when it reads as items to its end.
        holds_items = None if vr in (None, "UN") and not known else "SQ" in (vr, *known)
        start = position + header
        if length == _UNDEFINED:
            if tag != _PIXEL_DATA and holds_items is False:
                raise _Unreadable
            self._add(position, start, None, where)
            if tag == _PIXEL_DATA:
                return self._fragments(start, end, where)
            return self._items(start, end, True, vr == "SQ", path, where)
        stop = start + length
        if stop > end:
            raise _Unreadable
        peek = self.data[start : min(start + 4, stop)] == b"\xfe\xff\x00\xe0"
        if holds_items or (holds_items is None and peek):
            mark = len(self.spans)
            self._add(position, start, None, where)
            try:
                return self._items(start, stop, False, vr == "SQ", path, where)
            except _Unreadable:
                if holds_items:
                    raise
                del self.spans[mark:]
        return self._add(position, stop, start, where)

    def _items(
        self,
        position: int,
        end: int,
        delimited: bool,
        explicit: bool,
        path: ElementPath,
        where: Location,
    ) -> int:
        """Read a sequence's items, up to ``end`` or its delimiter."""
        if len(path.items) >= MAX_NESTING:
            raise _Unreadable
        index = 0
        while delimited or position < end:
            group, number, length = self._unpack("<HHI", position, end)
            if delimited and (group, number) == _SEQUENCE_END:
                return self._add(position, position + 8, None, where)
            undefined = length == _UNDEFINED
            stop = end if undefined else position + 8 + length
            if (group, number) != _ITEM or stop > end:
                raise _Unreadable
            position = self._add(position, position + 8, None, where)
            items = (*path.items, (path.tag, index))
            while undefined or position < stop:
                if undefined and self._unpack("<HHI", position, stop)[:2] == _ITEM_END:
                    position = self._add(position, position + 8, None, where)
                    break
                position = self._element(position, stop, explicit, items)
            index += 1
        return position

    def _fragments(self, position: int, end: int, where: Location) -> int:
        """Read an encapsulated value's items, up to its delimiter."""
        index = 0
        while True:
            group, number, length = self._unpack("<HHI", position, end)
            if (group, number) == _SEQUENCE_END:
                return self._add(position, position + 8, None, where)
            stop = position + 8 + length
            if (group, number) != _ITEM or length == _UNDEFINED or stop > end:
                raise _Unreadable
            fragment = dataclasses.replace(where, item=index)
            self._add(position, stop, position + 8, fragment)
            position, index = stop, index + 1
