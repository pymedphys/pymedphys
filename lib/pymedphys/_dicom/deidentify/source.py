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

"""Hold a source file's bytes, once its whole structure is shown to be sound.

:func:`read_source` admits a DICOM PS3.10 file only if
:func:`.file_layout.read_file_layout` reads every byte of it, from the
preamble and File Meta Information to the end of its data set, in Implicit
or Explicit VR Little Endian, the transfer syntaxes of the first supported
release (D-010). Reading checks each element's header and length, that its
value fits what holds it, that tags rise through each data set and item, so
that none repeats, each item's tag, length, and delimiter, each sequence's
delimiter, and a bound on nesting; Data Set Trailing Padding is accounted
for, and nothing may follow the last element. Every Value Length and Item
Length but the undefined length must then be even (PS3.5 Sections 7.1.1 and
7.5), in the File Meta Information and in the data set, at every depth.
Anything else is refused with a :class:`SourceReason` and the offset where
reading stopped or the odd length starts, never a value.

The layout reader itself reads an odd length, so that a written file can be
searched for residual values whatever its lengths; only admitting a source
requires them to be even.

The :class:`SourceEvidence` it returns keeps an immutable copy of the bytes
and, for each element of the data set, where its header and Value Field
are, its VR as written, and whether its length is undefined. Those bytes are
the authority on what the source holds: a data set from
:meth:`SourceEvidence.dataset` is a fresh, mutable view, and decoding an
element through it, as pydicom does on access, never changes the evidence.
:func:`.elements.read_element` given the evidence decodes from the source's
Value Field and refuses an element that does not match it.
"""

from __future__ import annotations

import enum
import io
import struct
from collections.abc import Iterator, Mapping

from pymedphys._imports import pydicom

from .diagnostics import redacted_diagnostics
from .file_layout import (
    ElementPath,
    Extent,
    FileLayout,
    Region,
    read_file_layout,
)

# Implicit VR Little Endian and Explicit VR Little Endian (PS3.5 Sections
# A.1 and A.2), the transfer syntaxes of the first supported release.
SUPPORTED_TRANSFER_SYNTAXES = frozenset({"1.2.840.10008.1.2", "1.2.840.10008.1.2.1"})
_DATA_SET_REGIONS = (Region.DATA_SET, Region.TRAILING_PADDING)
_ITEM_TAG = b"\xfe\xff\x00\xe0"  # (FFFE,E000), little endian
_UNDEFINED_LENGTH = 0xFFFFFFFF


class SourceReason(enum.Enum):
    """Why a source file is refused, as a stable code."""

    NOT_PS3_10 = "not-ps3-10"  # no "DICM" prefix after a 128-byte preamble
    TRANSFER_SYNTAX = "transfer-syntax"  # absent, or not supported
    STRUCTURE = "structure"  # unreadable, an odd length, or bytes after it
    PYDICOM = "pydicom"  # pydicom cannot read what the layout reads


class SourceRefused(Exception):
    """A source file whose structure cannot be shown to be sound.

    Not a :class:`ValueError`, which code that rejects invalid input could
    catch by accident.

    Attributes
    ----------
    reason : SourceReason
    offset : int, optional
        Where reading stopped, or where the element or item whose length is
        odd starts, for :attr:`SourceReason.STRUCTURE`.
    """

    def __init__(self, reason: SourceReason, offset: int | None = None) -> None:
        super().__init__(reason, offset)
        self.reason = reason
        self.offset = offset

    def __str__(self) -> str:
        where = "" if self.offset is None else f" at byte {self.offset}"
        return f"the source file is refused ({self.reason.value}){where}"


class SourceEvidence:
    """A source file's immutable bytes, and where each element of its data set is.

    Build one with :func:`read_source`. Its ``repr`` shows only the file's
    size, transfer syntax, and number of elements.
    """

    def __init__(self, data: bytes, transfer_syntax: str, elements: tuple) -> None:
        self._data = data
        self.transfer_syntax = transfer_syntax
        self._elements: Mapping[ElementPath, Extent] = {
            extent.location.element: extent for extent in elements
        }

    @property
    def size(self) -> int:
        """The file's length in bytes."""
        return len(self._data)

    def __repr__(self) -> str:
        return (
            f"SourceEvidence(size={self.size}, transfer_syntax="
            f"{self.transfer_syntax!r}, elements={len(self._elements)})"
        )

    def paths(self) -> Iterator[ElementPath]:
        """Yield the path of each element of the data set, in file order."""
        return iter(self._elements)

    def __contains__(self, path: object) -> bool:
        return path in self._elements

    def element(self, path: ElementPath) -> Extent:
        """Return where the element at ``path`` is; :class:`KeyError` if absent."""
        return self._elements[path]

    def encoded(self, path: ElementPath) -> bytes:
        """Return the element at ``path`` as in the file, header and value.

        Raises
        ------
        KeyError
            If the data set has no element at ``path``.
        """
        extent = self._elements[path]
        return self._data[extent.start : extent.end]

    def header(self, path: ElementPath) -> bytes:
        """Return the header of the element at ``path``, as in the file.

        Raises
        ------
        KeyError
            If the data set has no element at ``path``.
        """
        extent = self._elements[path]
        return self._data[extent.start : extent.value_start]

    def value_field(self, path: ElementPath) -> bytes:
        """Return the Value Field of the element at ``path``, as in the file.

        Raises
        ------
        KeyError
            If the data set has no element at ``path``.
        ValueError
            If the element's length is undefined, so that its value is its
            items rather than one field.
        """
        extent = self._elements[path]
        if extent.undefined_length:
            raise ValueError(f"{path} has an undefined length")
        return self._data[extent.value_start : extent.end]

    def dataset(self) -> pydicom.Dataset:
        """Return a fresh data set read from the evidence, as ``dcmread`` reads it.

        Each call reads the bytes again, in full and without deferring any
        value, so changing one data set changes neither the evidence nor
        another. pydicom's warnings and log records while it reads are
        redacted. pydicom converts each value when it is first accessed,
        later, so a caller that accesses values redacts them itself, as
        :func:`~pymedphys._dicom.deidentify.elements.read_element` does.

        Raises
        ------
        SourceRefused
            If pydicom cannot read the file.
        """
        try:
            with redacted_diagnostics():
                return pydicom.dcmread(io.BytesIO(self._data), defer_size=None)
        # pydicom raises many types for a file it cannot read, and its
        # message can quote a value.
        except Exception:  # pylint: disable = broad-exception-caught
            raise SourceRefused(SourceReason.PYDICOM) from None


def read_source(data: bytes | bytearray | memoryview) -> SourceEvidence:
    """Return the evidence of a source file whose every byte is accounted for.

    Parameters
    ----------
    data : bytes, bytearray, or memoryview
        The whole file. It is copied, so later changes to it do not reach
        the evidence.

    Returns
    -------
    SourceEvidence

    Raises
    ------
    SourceRefused
        If the file is not a DICOM PS3.10 file, its transfer syntax is not
        Implicit or Explicit VR Little Endian, its structure cannot be read
        to its end, or an element or item has an odd length.
    """
    data = bytes(data)
    if data[128:132] != b"DICM":
        raise SourceRefused(SourceReason.NOT_PS3_10)
    try:
        layout = read_file_layout(data)
    except ValueError:  # a deflated data set
        raise SourceRefused(SourceReason.TRANSFER_SYNTAX) from None
    syntax = layout.transfer_syntax
    if syntax not in SUPPORTED_TRANSFER_SYNTAXES:
        raise SourceRefused(SourceReason.TRANSFER_SYNTAX)
    if not layout.readable:
        # Reading stopped where the trailing bytes start, or, inside a
        # sequence or item, at the end of the file.
        last = layout.spans[-1]
        stop = last.start if last.location.region is Region.TRAILING else layout.size
        raise SourceRefused(SourceReason.STRUCTURE, stop)
    odd = _first_odd_length(data, layout)
    if odd is not None:
        raise SourceRefused(SourceReason.STRUCTURE, odd)
    elements = tuple(
        extent
        for extent in layout.elements
        if extent.location.region in _DATA_SET_REGIONS
    )
    return SourceEvidence(data, syntax, elements)


def _first_odd_length(data: bytes, layout: FileLayout) -> int | None:
    """Return where the first element or item whose length is odd starts.

    Every Value Length but the undefined length, FFFFFFFFH, is even (PS3.5
    Section 7.1.1), and so is every Item Length (Section 7.5), including
    those of fragments (Section A.4). The layout gives each element's extent,
    and each item header is a span of its own.

    Parameters
    ----------
    data : bytes
        The whole file.
    layout : FileLayout
        The file's layout, which has been read to its end.

    Returns
    -------
    int or None
        The offset of the first such element or item, in file order, or
        ``None`` if every length is even or undefined.
    """
    starts = [
        extent.start
        for extent in layout.elements
        if not extent.undefined_length and (extent.end - extent.value_start) % 2
    ]
    for span in layout.spans:
        if (
            span.location.region is not Region.PREAMBLE
            and data[span.start : span.start + 4] == _ITEM_TAG
        ):
            (length,) = struct.unpack_from("<I", data, span.start + 4)
            if length != _UNDEFINED_LENGTH and length % 2:
                starts.append(span.start)
    return min(starts, default=None)
