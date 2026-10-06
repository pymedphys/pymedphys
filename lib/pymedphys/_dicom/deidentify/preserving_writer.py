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

"""Write a de-identified data set from its source's bytes.

:func:`write_data_set` writes an instance's data set from the
:class:`.source.SourceEvidence` of its source file and the plan for it, by
element path, in the source's transfer syntax:

- a kept element is copied from the source byte for byte, header and value,
  including a sequence or other element holding items when nothing in it
  changes, so that an opaque value that happens to read as items stays as it
  is;
- a kept element holding items with a change in it keeps its tag and VR as
  written, and is written with an undefined length, as is each of its items,
  ended by the Item and Sequence Delimitation Items (PS3.5 Sections 7.5.1
  and 7.5.2; for UN, Section 6.2.2), so that no length needs to be worked
  out again. Every item is written, even one whose elements are all
  removed, so the number of items is kept;
- a removed element is left out, with everything in it;
- a replacement, or an element introduced into a data set or item that is
  written, is encoded by pydicom's writer for one element, with the VR that
  it gives and the Specific Character Set in force at its place in the
  output: that of its own data set, or else of the nearest item or data set
  that holds it (PS3.5 Section 7.5.3). A sequence among them is written as
  an edited kept one is, its items' elements taken as they are held, so
  that pydicom never resolves an ambiguous VR; an element that pydicom
  still holds encoded, or whose VR is ambiguous, is refused.

A replacement is refused unless it belongs in a data set, which leaves out
File Meta Information, group lengths, and delimiters; it is written with
the VR it gives; and each text value can be written in the character set in
force, as :func:`.elements.character_set_problem` finds, or, for a VR of the
Default Character Repertoire alone, in ISO 646. In implicit VR, including
the items of a sequence kept as UN, which stay in implicit VR, no VR is
written and a reader takes it from its dictionary, so a replacement is
refused unless the pinned dictionary gives its VR alone. A plan is refused
where it keeps an element inside one removed or replaced, keeps a group
length, which could go stale, or changes the character set of kept text.

The elements of each data set are written in ascending order of tag (PS3.5
Section 7.1). :func:`.preservation.verify_preservation` then checks the
file written from the result against its source and the same plan.

A kept element of undefined length that holds no items, which can only be
fragments of OB, is refused rather than copied: verification could not show
it preserved. Only Implicit and Explicit VR Little Endian, which
:func:`.source.read_source` admits, are written. :func:`write_file_bytes`
puts the preamble and the File Meta Information that :mod:`.file_meta`
builds before the data set. Each refusal is raised outside any handler, so
it carries no exception from pydicom, whose message can quote a value, and
pydicom's warnings and log records while either function writes are
redacted by :func:`.diagnostics.redacted_diagnostics`.
"""

from __future__ import annotations

import enum
import struct
from collections.abc import Mapping, Sequence

from pymedphys._imports import pydicom

from . import file_meta
from .diagnostics import redacted_diagnostics
from .elements import (
    CHARACTER_SET_VRS,
    DEFAULT_CODECS,
    UndecodableElement,
    character_set_problem,
    dataset_codecs,
)
from .file_layout import ElementPath
from .preservation import TEXT_VRS, Expectations
from .source import SUPPORTED_TRANSFER_SYNTAXES, SourceEvidence
from .standard import VRS, dictionary_attribute

_IMPLICIT = "1.2.840.10008.1.2"
_CHARACTER_SET = "(0008,0005)"
# The VRs of text in the Default Character Repertoire alone (PS3.5 Table 6.2-1).
_DEFAULT_TEXT_VRS = frozenset(
    {"AE", "AS", "CS", "DA", "DS", "DT", "IS", "TM", "UI", "UR"}
)
# File Meta Information, command elements, and items and delimiters.
_NOT_IN_A_DATA_SET = (0x0000, 0x0002, 0xFFFE)
_UNDEFINED = b"\xff\xff\xff\xff"
_ITEM = b"\xfe\xff\x00\xe0" + _UNDEFINED
_ITEM_END = b"\xfe\xff\x0d\xe0" + bytes(4)
_SEQUENCE_END = b"\xfe\xff\xdd\xe0" + bytes(4)
_Terms = tuple[str, ...]


class WriteReason(enum.Enum):
    """Why a data set is not written, as a stable code."""

    TRANSFER_SYNTAX = "transfer-syntax"  # not Implicit or Explicit VR Little Endian
    UNPLANNED = "unplanned"  # a source element neither kept, replaced, nor removed
    UNPLACED = "unplaced"  # kept or replaced in a data set that is not written
    FRAGMENTS = "fragments"  # a kept value of undefined length without items
    ELEMENT = "element"  # an element that cannot be written as it is given
    IMPLICIT_VR = "implicit-vr"  # in implicit VR, a VR the dictionary does not settle
    ENCODING = "encoding"  # text or a character set that cannot be encoded
    CHARACTER_SET = "character-set"  # kept text in another character set


class WriteRefused(Exception):
    """A data set that cannot be written as planned.

    Not a :class:`ValueError`, which code that rejects invalid input could
    catch by accident. Its message names the reason and the element's path,
    never a value.

    Attributes
    ----------
    reason : WriteReason
    path : ElementPath, optional
        The element refused; ``None`` for the transfer syntax.

    Examples
    --------
    >>> str(WriteRefused(WriteReason.UNPLANNED, ElementPath((), "(0010,0010)")))
    'the data set is not written (unplanned) at (0010,0010)'
    """

    def __init__(self, reason: WriteReason, path: ElementPath | None = None) -> None:
        super().__init__(reason, path)
        self.reason = reason
        self.path = path

    def __str__(self) -> str:
        where = "" if self.path is None else f" at {self.path}"
        return f"the data set is not written ({self.reason.value}){where}"


def write_data_set(
    source: SourceEvidence,
    *,
    kept: frozenset[ElementPath],
    removed: frozenset[ElementPath],
    replacements: Mapping[ElementPath, pydicom.DataElement],
) -> bytes:
    """Return the encoded data set that the plan makes of ``source``.

    Parameters
    ----------
    source : SourceEvidence
    kept : frozenset of ElementPath
        Elements to copy, and elements holding items to keep as containers.
    removed : frozenset of ElementPath
        Elements to leave out, including every element inside a removed one.
    replacements : mapping of ElementPath to pydicom.DataElement
        The elements to write in place of source elements, or to introduce,
        each with the tag of its path and a single VR. The elements in the
        items of a sequence among them are written from the sequence.

    Returns
    -------
    bytes
        The data set, without a preamble or File Meta Information.

    Raises
    ------
    ValueError
        If a path is in more than one of ``kept``, ``removed``, and
        ``replacements``.
    WriteRefused
        If the data set cannot be written as planned.
    """
    if source.transfer_syntax not in SUPPORTED_TRANSFER_SYNTAXES:
        raise WriteRefused(WriteReason.TRANSFER_SYNTAX)
    plan = Expectations(kept=kept, changed=frozenset(replacements), removed=removed)
    with redacted_diagnostics():
        writer = _Writer(source, plan, replacements)
        data = writer.data_set((), source.transfer_syntax != _IMPLICIT)
    writer.check_placed()
    return data


def write_file_bytes(
    data_set: bytes,
    *,
    sop_class_uid: str,
    sop_instance_uid: str,
    transfer_syntax_uid: str,
) -> bytes:
    """Return a DICOM file of a written data set, with new File Meta Information.

    The preamble is :data:`.file_meta.PREAMBLE`, and the File Meta
    Information is what :func:`.file_meta.file_meta_information` builds from
    the arguments, which it checks as it describes.
    """
    meta = file_meta.file_meta_information(
        sop_class_uid=sop_class_uid,
        sop_instance_uid=sop_instance_uid,
        transfer_syntax_uid=transfer_syntax_uid,
    )
    buffer = _buffer(explicit=True)
    with redacted_diagnostics():
        pydicom.filewriter.write_file_meta_info(buffer, meta, enforce_standard=False)
    return file_meta.PREAMBLE + b"DICM" + buffer.getvalue() + data_set


class _Writer:
    """Write the data sets of one plan, and record what is written."""

    def __init__(
        self,
        source: SourceEvidence,
        plan: Expectations,
        replacements: Mapping[ElementPath, pydicom.DataElement],
    ) -> None:
        self.source, self.plan, self.replacements = source, plan, replacements
        self.written: set[ElementPath] = set()
        self.copied: set[ElementPath] = set()  # containers copied whole
        self.children: dict[tuple, list[ElementPath]] = {}
        self.edited = {  # the containers that hold a change
            _container(path, depth)
            for path in plan.changed | plan.removed
            for depth in range(len(path.items))
        }
        planned = plan.kept | plan.changed | plan.removed
        governing = {_CHARACTER_SET} & {path.tag for path in planned - plan.kept}
        for path in source.paths():
            if path not in planned:
                raise WriteRefused(WriteReason.UNPLANNED, path)
            self.children.setdefault(path.items, []).append(path)
            if path in plan.kept and path.tag.endswith(",0000)"):
                raise WriteRefused(WriteReason.ELEMENT, path)  # a group length
            extent = source.element(path)
            if (
                governing
                and path in plan.kept
                and extent.items is None
                and extent.location.vr in TEXT_VRS
                and self.terms(path.items, False) != self.terms(path.items, True)
            ):
                raise WriteRefused(WriteReason.CHARACTER_SET, path)
        for path in replacements:
            if path not in source:
                self.children.setdefault(path.items, []).append(path)

    def data_set(self, items: tuple, explicit: bool) -> bytes:
        """Return the data set or item that ``items`` names, encoded."""
        encoded = []
        for path in self.children.get(items, ()):
            if path in self.replacements:
                codecs = _codecs(self.terms(items, True), path)
                element = self.replacements[path]
                encoded.append((path.tag, _encode(path, element, explicit, codecs)))
            elif path in self.plan.kept:
                encoded.append((path.tag, self.kept(path)))
            else:
                continue
            self.written.add(path)
        return b"".join(each for _, each in sorted(encoded))

    def kept(self, path: ElementPath) -> bytes:
        extent = self.source.element(path)
        if extent.items is None and extent.undefined_length:
            raise WriteRefused(WriteReason.FRAGMENTS, path)
        if path not in self.edited:
            self.copied.add(path)
            return self.source.encoded(path)
        # Only SQ, UN, and implicit VR hold items (file_layout), and each can
        # be of undefined length (PS3.5 Sections 6.2.2 and 7.5).
        tag = self.source.header(path)[:4]
        items = [
            self.data_set((*path.items, (path.tag, index)), extent.vr == "SQ")
            for index in range(extent.items or 0)
        ]
        return _sequence(tag, extent.vr, items)

    def check_placed(self) -> None:
        """Refuse a kept or replaced element that no written data set holds."""
        unplaced = [
            path
            for path in (self.plan.kept | self.plan.changed) - self.written
            if not any(
                _container(path, depth) in self.copied
                for depth in range(len(path.items))
            )
        ]
        if unplaced:
            raise WriteRefused(WriteReason.UNPLACED, min(unplaced, key=str))

    def terms(self, items: tuple, output: bool) -> _Terms:
        """Return the Specific Character Set in force in a data set.

        That is the one in the source, or, with ``output``, the one that the
        plan writes, by replacing or keeping it.
        """
        for depth in range(len(items), -1, -1):
            holder = ElementPath(items[:depth], _CHARACTER_SET)
            if output and holder in self.replacements:
                return _terms(self.replacements[holder].value)
            if holder in self.source and (not output or holder in self.plan.kept):
                extent = self.source.element(holder)
                if extent.undefined_length or extent.items is not None:
                    raise WriteRefused(WriteReason.FRAGMENTS, holder)
                text = self.source.value_field(holder).decode("latin-1")
                return _terms(text.split("\\"))
        return ()


def _container(path: ElementPath, depth: int) -> ElementPath:
    """Return the element at ``depth`` that holds ``path`` in its items."""
    return ElementPath(path.items[:depth], path.items[depth][0])


def _values(value: object) -> list:
    if value is None:
        return []
    if isinstance(value, (list, tuple, pydicom.multival.MultiValue)):
        return list(value)
    return [value]


def _terms(value: object) -> _Terms:
    """Return a Specific Character Set's terms; none for the default."""
    terms = tuple(str(term).strip(" ") for term in _values(value))
    return terms if any(terms) else ()


def _codecs(terms: _Terms, path: ElementPath) -> tuple[str, ...]:
    """Return the codecs of a Specific Character Set, as elements does."""
    if not terms:
        return DEFAULT_CODECS
    holder = pydicom.Dataset()
    holder.add_new(0x00080005, "CS", list(terms))
    try:
        return dataset_codecs(holder)
    except UndecodableElement:
        pass
    raise WriteRefused(WriteReason.ENCODING, path)


def _tag(tag: pydicom.tag.BaseTag) -> str:
    return f"({tag.group:04X},{tag.elem:04X})"


def _belongs(path: ElementPath, element: pydicom.DataElement) -> bool:
    """Return whether an element, as it is held, can be written at ``path``.

    It needs the path's tag, outside File Meta Information, command elements,
    group lengths, and items and delimiters, one VR, and, unless it is a
    sequence, a defined length.
    """
    return (
        _tag(element.tag) == path.tag
        and element.VR in VRS
        and element.tag.group not in _NOT_IN_A_DATA_SET
        and element.tag.elem != 0
        and not (element.is_undefined_length and element.VR != "SQ")
    )


def _encode(
    path: ElementPath,
    element: object,
    explicit: bool,
    codecs: Sequence[str],
) -> bytes:
    """Return a replacement encoded, with the elements of any items it holds."""
    if not isinstance(element, pydicom.DataElement) or not _belongs(path, element):
        raise WriteRefused(WriteReason.ELEMENT, path)
    attribute = dictionary_attribute(path.tag)
    if not explicit and (attribute is None or attribute.vrs != (element.VR,)):
        # A reader takes the VR from its dictionary, so one that the pinned
        # dictionary does not give alone could be read otherwise.
        raise WriteRefused(WriteReason.IMPLICIT_VR, path)
    if element.VR == "SQ":
        return _encode_sequence(path, element, explicit, codecs)
    values = _values(element.value)
    if (
        element.VR in CHARACTER_SET_VRS
        and character_set_problem(element.VR, values, codecs)
    ) or (
        element.VR in _DEFAULT_TEXT_VRS
        and not all(str(each).isascii() for each in values)
    ):
        raise WriteRefused(WriteReason.ENCODING, path)
    buffer = _buffer(explicit)
    try:
        with redacted_diagnostics():
            pydicom.filewriter.write_data_element(buffer, element, list(codecs))
    # pydicom raises many types for a value it cannot encode, and its
    # message can quote the value.
    except Exception:  # pylint: disable = broad-exception-caught
        buffer = None
    if buffer is None:
        raise WriteRefused(WriteReason.ENCODING, path)
    encoded = buffer.getvalue()
    # pydicom writes as UN a value too long for the length of its VR.
    if explicit and encoded[4:6] != element.VR.encode():
        raise WriteRefused(WriteReason.ELEMENT, path)
    return encoded


def _encode_sequence(
    path: ElementPath,
    element: pydicom.DataElement,
    explicit: bool,
    codecs: Sequence[str],
) -> bytes:
    """Return a sequence encoded from its items' elements as they are held."""
    items = []
    for index, item in enumerate(element.value):
        inner = (*path.items, (path.tag, index))
        held = item.get(0x00080005)
        in_force = codecs if held is None else _codecs(_terms(held.value), path)
        # Dataset.elements() yields each element without converting it,
        # where indexing would resolve an ambiguous VR.
        items.append(
            b"".join(
                _encode(ElementPath(inner, _tag(each.tag)), each, explicit, in_force)
                for each in item.elements()
            )
        )
    tag = struct.pack("<HH", element.tag.group, element.tag.elem)
    return _sequence(tag, "SQ" if explicit else None, items)


def _sequence(tag: bytes, vr: str | None, items: Sequence[bytes]) -> bytes:
    """Return an element holding ``items``, all of undefined length."""
    header = tag + (_UNDEFINED if vr is None else vr.encode() + bytes(2) + _UNDEFINED)
    body = b"".join(_ITEM + item + _ITEM_END for item in items)
    return header + body + _SEQUENCE_END


def _buffer(explicit: bool) -> pydicom.filebase.DicomBytesIO:
    buffer = pydicom.filebase.DicomBytesIO()
    buffer.is_little_endian = True
    buffer.is_implicit_VR = not explicit
    return buffer
