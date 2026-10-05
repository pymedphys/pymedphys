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

"""Verify that a written file keeps what its source kept, as the source encodes it.

:func:`verify_preservation` compares the evidence of a source file's data
set with that of the file written from it, both read by
:func:`.source.read_source`, against the :class:`Expectations` of which
elements were kept, changed, and removed. Every element of the data set
counts, including Data Set Trailing Padding; the preamble and File Meta
Information are not compared, since :mod:`.file_meta` replaces them. An
unchanged transfer syntax is necessary but not sufficient, so it checks each
element as the bytes encode it, and decodes no value:

- the transfer syntax is the same, since the first supported release does
  not transcode;
- each element of the source is planned once, as kept, changed, or removed;
  each element of the output was kept or changed; each kept element is in
  both; each changed element, being emptied, replaced, or introduced, is in
  the output; and no removed element is in the output. Paths in the output
  number items as the source does, so an item is never dropped on its own;
- a kept element that holds items, such as a sequence, has the same VR as
  written and the same number of items, and its items' elements are checked
  by their own paths, so its length may be defined in one file and undefined
  in the other;
- any other kept element has the same VR as written, which is ``None`` in
  implicit VR, the same header length and length form, and the same Value
  Field, byte for byte; one of undefined length, whose value is fragments
  rather than one field, cannot be verified;
- a kept private element (gggg,xxyy), with xx from 10 to FF, has a Private
  Creator (gggg,00xx) in its own data set with the same bytes in both
  files, or none in either (PS3.5 Section 7.8.1);
- kept text whose VR the Specific Character Set governs, or whose VR is not
  known, is in the same character set: the Specific Character Set
  (0008,0005) of its own data set, or of the nearest item or data set that
  holds it and has one (PS3.5 Section 7.5.3), has the same bytes in both
  files, or gives the Default Character Repertoire in both, by being absent
  or empty (PS3.3 Section C.12.1.1.2).

So a kept element whose VR is ambiguous, such as LUT Descriptor (0028,3002),
which can be US or SS, passes only where the output has the VR that the
source has: the writer must emit kept elements from their source bytes and
never resolve an ambiguous VR again. Changed elements are not checked here;
their new values are validated before they are written.

:class:`PreservationFailed` is raised with a reason and the element's path,
never a value, at the first failure, and the instance is to be sequestered.
Checks run in this order: the transfer syntax; each source element's plan,
in the source's order; each output element's plan, in the output's order;
kept elements absent from the source, then from the output, and changed
elements absent from the output; and then each kept element in the
source's order, through its VR, items, length, value, Private Creator, and
character set.
"""

from __future__ import annotations

import dataclasses
import enum

from .elements import CHARACTER_SET_VRS
from .file_layout import ElementPath, Extent
from .source import SourceEvidence

_CHARACTER_SET = "(0008,0005)"
# Without a VR as written or in the dictionary, text cannot be ruled out.
TEXT_VRS = CHARACTER_SET_VRS | {None, "UN"}


class PreservationReason(enum.Enum):
    """Why preservation cannot be shown, as a stable code."""

    TRANSFER_SYNTAX = "transfer-syntax"  # the output's differs from the source's
    UNPLANNED = "unplanned"  # a source element neither kept, changed, nor removed
    UNEXPECTED = "unexpected"  # an output element neither kept nor changed
    NOT_REMOVED = "not-removed"  # a removed element in the output
    MISSING = "missing"  # a kept element absent from the source or the output
    VR = "vr"  # a kept element whose VR as written differs
    STRUCTURE = "structure"  # items in one file and not the other, or more items
    LENGTH = "length"  # another header length, or defined and undefined length
    UNVERIFIABLE = "unverifiable"  # a kept value of undefined length without items
    VALUE = "value"  # a kept Value Field with other bytes
    PRIVATE_CREATOR = "private-creator"  # a kept private element's creator differs
    CHARACTER_SET = "character-set"  # kept text in another Specific Character Set


class PreservationFailed(Exception):
    """A written file that cannot be shown to preserve what its source kept.

    Not a :class:`ValueError`, which code that rejects invalid input could
    catch by accident. Its message names the reason and the element's path,
    never a value.

    Attributes
    ----------
    reason : PreservationReason
    path : ElementPath, optional
        The element that differs; ``None`` for the transfer syntax.

    Examples
    --------
    >>> path = ElementPath((("(0028,3010)", 0),), "(0028,3002)")
    >>> str(PreservationFailed(PreservationReason.VR, path))
    'preservation cannot be shown (vr) at (0028,3010)[0] > (0028,3002)'
    """

    def __init__(
        self, reason: PreservationReason, path: ElementPath | None = None
    ) -> None:
        super().__init__(reason, path)
        self.reason = reason
        self.path = path

    def __str__(self) -> str:
        where = "" if self.path is None else f" at {self.path}"
        return f"preservation cannot be shown ({self.reason.value}){where}"


@dataclasses.dataclass(frozen=True)
class Expectations:
    """What the plan for one instance did with each element, by path.

    Attributes
    ----------
    kept : frozenset of ElementPath
        Elements written from their source bytes, and the sequences and
        other elements holding items that are kept as containers.
    changed : frozenset of ElementPath
        Elements emptied, replaced, or introduced, whose values are
        validated elsewhere.
    removed : frozenset of ElementPath
        Elements removed, including every element inside a removed sequence.

    Paths name items by their index in the source, which the output must
    keep: an item is never removed on its own, so that the items after it
    keep their indices.

    Raises
    ------
    ValueError
        If a path is in more than one set.
    """

    kept: frozenset[ElementPath] = frozenset()
    changed: frozenset[ElementPath] = frozenset()
    removed: frozenset[ElementPath] = frozenset()

    def __post_init__(self) -> None:
        twice = (
            (self.kept & self.changed)
            | (self.kept & self.removed)
            | (self.changed & self.removed)
        )
        if twice:
            raise ValueError(f"{min(twice, key=str)} is planned more than once")


def verify_preservation(
    source: SourceEvidence, output: SourceEvidence, expected: Expectations
) -> None:
    """Check that ``output`` keeps what ``expected`` says ``source`` kept.

    Parameters
    ----------
    source, output : SourceEvidence
        The source file, and the file written from it.
    expected : Expectations

    Raises
    ------
    PreservationFailed
        At the first element that does not match its expectation.
    """
    if output.transfer_syntax != source.transfer_syntax:
        raise PreservationFailed(PreservationReason.TRANSFER_SYNTAX)
    planned = expected.kept | expected.changed | expected.removed
    for path in source.paths():
        if path not in planned:
            raise PreservationFailed(PreservationReason.UNPLANNED, path)
    for path in output.paths():
        if path in expected.removed:
            raise PreservationFailed(PreservationReason.NOT_REMOVED, path)
        if path not in expected.kept and path not in expected.changed:
            raise PreservationFailed(PreservationReason.UNEXPECTED, path)
    kept = [path for path in source.paths() if path in expected.kept]
    strays = expected.kept.difference(kept)
    if strays:
        raise PreservationFailed(PreservationReason.MISSING, min(strays, key=str))
    for path in kept:
        if path not in output:
            raise PreservationFailed(PreservationReason.MISSING, path)
    # Each change is written: emptied, replaced, or introduced.
    unwritten = [path for path in expected.changed if path not in output]
    if unwritten:
        raise PreservationFailed(PreservationReason.MISSING, min(unwritten, key=str))
    for path in kept:
        _check_kept(source, output, path)


def _check_kept(
    source: SourceEvidence, output: SourceEvidence, path: ElementPath
) -> None:
    """Check one kept element, which both files hold."""
    before, after = source.element(path), output.element(path)
    if before.vr != after.vr:
        raise PreservationFailed(PreservationReason.VR, path)
    if before.items != after.items:
        raise PreservationFailed(PreservationReason.STRUCTURE, path)
    if before.items is not None:  # a container, whose items are checked by path
        return
    if _length_form(before) != _length_form(after):
        raise PreservationFailed(PreservationReason.LENGTH, path)
    if before.undefined_length:
        raise PreservationFailed(PreservationReason.UNVERIFIABLE, path)
    if source.value_field(path) != output.value_field(path):
        raise PreservationFailed(PreservationReason.VALUE, path)
    creator = _private_creator(path)
    if creator and _field(source, creator, path) != _field(output, creator, path):
        raise PreservationFailed(PreservationReason.PRIVATE_CREATOR, path)
    if before.location.vr in TEXT_VRS and _character_set(
        source, path
    ) != _character_set(output, path):
        raise PreservationFailed(PreservationReason.CHARACTER_SET, path)


def _length_form(extent: Extent) -> tuple[int, bool]:
    """Return how long an element's header is, and whether its length is undefined."""
    return extent.value_start - extent.start, extent.undefined_length


def _private_creator(path: ElementPath) -> ElementPath | None:
    """Return the Private Creator that a private element's tag reserves.

    Element (gggg,xxyy) of an odd group, with xx from 10 to FF, is in the
    block that (gggg,00xx) reserves in the same data set (PS3.5 Section
    7.8.1).
    """
    group, element = int(path.tag[1:5], 16), int(path.tag[6:10], 16)
    if group % 2 == 0 or element < 0x1000:
        return None
    return ElementPath(path.items, f"({group:04X},00{element >> 8:02X})")


def _field(
    evidence: SourceEvidence, holder: ElementPath, path: ElementPath
) -> bytes | None:
    """Return the Value Field of ``holder`` if it is present, for ``path``.

    A holder of undefined length or with items has no single Value Field,
    so the context of the element at ``path`` cannot be shown.
    """
    if holder not in evidence:
        return None
    extent = evidence.element(holder)
    if extent.undefined_length or extent.items is not None:
        reason = (
            PreservationReason.CHARACTER_SET
            if holder.tag == _CHARACTER_SET
            else PreservationReason.PRIVATE_CREATOR
        )
        raise PreservationFailed(reason, path)
    return evidence.value_field(holder)


def _character_set(evidence: SourceEvidence, path: ElementPath) -> bytes | None:
    """Return the Specific Character Set in force at ``path``, as encoded.

    That is the one in the element's own data set, or else in the nearest
    item or data set that holds it (PS3.5 Section 7.5.3), or ``None``. An
    empty value, once its padding is stripped, is ``None`` too, since both
    give the Default Character Repertoire (PS3.3 Section C.12.1.1.2).
    """
    for depth in range(len(path.items), -1, -1):
        holder = ElementPath(path.items[:depth], _CHARACTER_SET)
        if holder in evidence:
            return (_field(evidence, holder, path) or b"").strip(b" ") or None
    return None
