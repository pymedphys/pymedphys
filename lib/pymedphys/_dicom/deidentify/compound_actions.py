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

"""Resolve the actions of Table E.1-1a from an attribute's PS3.3 Type.

Table E.1-1 of DICOM PS3.15 gives some attributes a compound action, such as
X/Z/D: remove the attribute (X) unless the IOD requires it, and otherwise
empty it (Z) or give it a dummy value (D), as Table E.1-1a defines. Which one
applies depends on the attribute's Type in the instance's IOD, at its place in
the data set. The design resolves it from the strictest Type that any of the
IOD's modules gives the attribute there, whatever the module's usage, so that
no condition is evaluated: Type 1 or 1C gives D, Type 2 or 2C gives Z, and
Type 3 gives X. Where the compound action does not offer that action, the
next of X, Z, and D that it offers applies, and in X/Z/U*, U, the replacement
of the instance UIDs that the sequence contains, takes the place of D. An
attribute that the IOD does not define at that place counts as Type 3.

X/Z on a Type 1 or 1C attribute gives D. Table E.1-1a defines Z as a
zero-length value or a non-zero-length dummy value consistent with the VR,
and a plain Z on such an attribute writes D's dummy value, so where the Type
requires a value, the Z that X/Z offers does the same: the resolver returns
D, the action that writes it. No compound action therefore removes an
attribute that its Type requires, or empties one that must have a value.
Where the attribute's VR has no generic dummy value, as for a sequence,
writing D is refused, and the attribute needs a reviewed rule or its instance
is sequestered.

For example, Table E.1-1 gives Institution Name (0008,0080) X/Z/D. The RT
Structure Set IOD makes it Type 3 at the top level of the data set, Type 2 in
ROI Creator Sequence (3006,004D) within Structure Set ROI Sequence
(3006,0020), and Type 1C in Referring Physician Identification Sequence
(0008,0096):

>>> from pymedphys._dicom.deidentify.iods import load_iod_tables
>>> structure_set = load_iod_tables().iods["RT Structure Set"]
>>> resolve_in_iod(structure_set, "(0008,0080)", (), "X/Z/D")
'X'
>>> roi_creator = ("(3006,0020)", "(3006,004D)")
>>> resolve_in_iod(structure_set, "(0008,0080)", roi_creator, "X/Z/D")
'Z'
>>> resolve_in_iod(structure_set, "(0008,0080)", ("(0008,0096)",), "X/Z/D")
'D'

The Type also decides what three plain actions do. A plain D on an
attribute that the IOD does not define at that place gives X, following Note
13 after Table E.1-1a, and a plain Z on a Type 1 or 1C attribute gives D, as
X/Z does there (:func:`resolve_plain_in_iod`). A plain X always removes the
attribute, as Table E.1-1a defines X, whatever its Type
(:func:`resolve_plain_x_in_iod`). Where the IOD requires the attribute at
that place, by its strictest Type, the innermost enclosing sequence that the
IOD makes Type 3 at its own place is removed with it, with everything in
that sequence, so that the output stays valid; where no such sequence
encloses it, the instance is sequestered. Two attributes need neither:
removing Overlay Data (60xx,3000) removes every attribute of its repeating
group where the IOD's Overlay Plane Module is user-optional, and ROI Interpreter Sequence (3006,004E), whose condition lapses once
ROI Creator Sequence (3006,004D) is removed, is removed alone.

For example, the RT Structure Set IOD makes Series Description (0008,103E),
which Table E.1-1 gives X, Type 1 in Source Series Information Sequence
(3006,004C), which is Type 3, so the sequence goes too:

>>> resolve_plain_x_in_iod(structure_set, "(0008,103E)", ("(3006,004C)",))
PlainRemoval(extent=<RemovalExtent.SEQUENCE: 'sequence'>, sequence=0)

This module chooses the action; it writes no value and changes no data set.
Its errors never repeat a value.
"""

from __future__ import annotations

import dataclasses
import enum
import re
from collections.abc import Mapping, Sequence

from .iods import IOD, AttributeDefinition

# The actions in the order in which they retain more: remove, empty, then
# replace with a dummy value.
_ORDER = ("X", "Z", "D")
# What each compound action of Table E.1-1a, in the table's order, offers in
# the place of X, Z, and D. In X/Z/U*, U takes the place of D. In X/Z, Z with
# a non-zero-length dummy value, which D writes, takes the place of D.
_OFFERS: Mapping[str, Mapping[str, str]] = {
    "Z/D": {"Z": "Z", "D": "D"},
    "X/Z": {"X": "X", "Z": "Z", "D": "D"},
    "X/D": {"X": "X", "D": "D"},
    "X/Z/D": {"X": "X", "Z": "Z", "D": "D"},
    "X/Z/U*": {"X": "X", "Z": "Z", "D": "U"},
}
COMPOUND_ACTIONS = frozenset(_OFFERS)
# The plain actions of Table E.1-1a.
PLAIN_ACTIONS = frozenset({"C", "D", "K", "U", "X", "Z"})

# Each Type of PS3.5 Section 7.4 by its strictness. No condition is
# evaluated, so 1C counts as 1 and 2C as 2.
_STRICTNESS = {"1": "1", "1C": "1", "2": "2", "2C": "2", "3": "3"}
# The action that each strictness calls for.
_TARGET = {"1": "D", "2": "Z", "3": "X"}

# A tag as the IOD tables give it, with upper-case hexadecimal digits.
_TAG_PATTERN = re.compile(r"\([0-9A-F]{4},[0-9A-F]{4}\)")
# Overlay Data (60xx,3000) in each overlay group, the even groups 6000 to
# 601E (PS3.5 Section 7.6). Odd groups, such as 6001, are private.
_OVERLAY_DATA = re.compile(r"\(60[01][02468ACE],3000\)")
# ROI Interpreter Sequence, Type 1C only while ROI Creator Sequence, which
# Table E.1-1 also removes, is present.
_ROI_INTERPRETER_SEQUENCE = "(3006,004E)"


class RemovalExtent(enum.Enum):
    """What a plain X removes with an attribute, or else sequesters."""

    ATTRIBUTE = "attribute"  # the attribute alone
    SEQUENCE = "sequence"  # an enclosing sequence, with everything in it
    OVERLAY_GROUP = "overlay group"  # every attribute of the overlay group
    SEQUESTER = "sequester"  # nothing: the instance is sequestered


@dataclasses.dataclass(frozen=True)
class PlainRemoval:
    """What a plain X on an attribute at a place requires.

    Attributes
    ----------
    extent : RemovalExtent
        :attr:`~RemovalExtent.ATTRIBUTE` to remove the attribute alone;
        :attr:`~RemovalExtent.SEQUENCE` to remove the enclosing sequence that
        ``sequence`` names, with every item, and so the attribute;
        :attr:`~RemovalExtent.OVERLAY_GROUP` to remove every attribute of
        the attribute's overlay group, in the same data set or item; or
        :attr:`~RemovalExtent.SEQUESTER` where no removal keeps the instance
        valid, so the instance is sequestered.
    sequence : int or None
        For :attr:`~RemovalExtent.SEQUENCE`, the position in the attribute's
        path of the sequence to remove, counting from 0 at the outermost:
        ``path[sequence]`` is its tag, and ``path[:sequence]`` the sequences
        whose items contain it. Otherwise ``None``.

    Raises
    ------
    ValueError
        If ``extent`` is not a :class:`RemovalExtent`, or if ``sequence`` is
        not an integer from 0 for :attr:`~RemovalExtent.SEQUENCE`, or not
        ``None`` for any other extent.
    """

    extent: RemovalExtent
    sequence: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.extent, RemovalExtent):
            raise ValueError("extent is not a RemovalExtent")
        if self.extent is RemovalExtent.SEQUENCE:
            if (
                not isinstance(self.sequence, int)
                or isinstance(self.sequence, bool)
                or self.sequence < 0
            ):
                raise ValueError(
                    "sequence is not an integer from 0, the position of the "
                    "sequence to remove"
                )
        elif self.sequence is not None:
            raise ValueError("sequence is given for an extent other than SEQUENCE")


def _checked_path(tag: object, path: object) -> tuple[str, ...]:
    if not isinstance(tag, str) or not _TAG_PATTERN.fullmatch(tag):
        raise ValueError(
            "tag is not of the form (gggg,eeee) with upper-case hexadecimal digits"
        )
    if (
        isinstance(path, str)
        or not isinstance(path, Sequence)
        or not all(isinstance(t, str) and _TAG_PATTERN.fullmatch(t) for t in path)
    ):
        raise ValueError(
            "path is not a sequence of tags of the form (gggg,eeee) with "
            "upper-case hexadecimal digits"
        )
    return tuple(path)


def strictest_type(iod: IOD, tag: str, path: Sequence[str] = ()) -> str:
    """Return the strictest Type that an IOD gives an attribute at one place.

    Parameters
    ----------
    iod : IOD
        The instance's IOD, from
        :func:`~pymedphys._dicom.deidentify.iods.load_iod_tables`.
    tag : str
        The attribute's tag, such as ``"(0010,0020)"``, with upper-case
        hexadecimal digits.
    path : sequence of str, optional
        The tags of the sequences whose items contain the attribute,
        outermost first. Defaults to the top level of the data set.

    Returns
    -------
    str
        ``"1"``, ``"2"``, or ``"3"``: the strictest Type of every definition
        of the attribute at that place (:meth:`IOD.lookup
        <pymedphys._dicom.deidentify.iods.IOD.lookup>`), from modules of
        every usage, with 1C counted as 1 and 2C as 2; or ``"3"`` if the IOD
        does not define the attribute there.

    Raises
    ------
    ValueError
        If ``tag``, or a tag of ``path``, is not of the form ``(gggg,eeee)``
        with upper-case hexadecimal digits, or if ``path`` is a single
        string.
    """
    return _strictest(iod.lookup(tag, _checked_path(tag, path)))


def _strictest(definitions: Sequence[AttributeDefinition]) -> str:
    return min((_STRICTNESS[d.type] for d in definitions), default="3")


def resolve(action: str, attribute_type: str) -> str:
    """Return the action that a compound action gives an attribute of a Type.

    The Type calls for D (1 or 1C), Z (2 or 2C), or X (3). Where ``action``
    does not offer it, the next of X, Z, and D that ``action`` offers
    applies. In X/Z/U*, U takes the place of D, and in X/Z, D, the
    non-zero-length dummy value that Table E.1-1a allows Z.

    Plain actions (D, Z, X, K, C, and U) are rejected rather than passed
    through: what D and Z do depends on whether and how the IOD defines the
    attribute, not only on its Type, so :func:`resolve_plain_in_iod`
    resolves them.

    Parameters
    ----------
    action : str
        A compound action of Table E.1-1a, one of :data:`COMPOUND_ACTIONS`,
        such as ``"X/Z/D"``.
    attribute_type : str
        The attribute's Type: ``"1"``, ``"1C"``, ``"2"``, ``"2C"``, or
        ``"3"``.

    Returns
    -------
    str
        ``"X"``, ``"Z"``, ``"D"``, or ``"U"``.

    Raises
    ------
    ValueError
        If ``action`` is not a compound action, or ``attribute_type`` is not
        a Type.

    Examples
    --------
    >>> resolve("X/Z", "1")
    'D'
    >>> resolve("X/D", "2")
    'D'
    >>> resolve("Z/D", "3")
    'Z'
    >>> resolve("X/Z/U*", "1C")
    'U'
    """
    if not isinstance(action, str) or action not in _OFFERS:
        raise ValueError(
            "action is not a compound action of Table E.1-1a: " + ", ".join(_OFFERS)
        )
    if not isinstance(attribute_type, str) or attribute_type not in _STRICTNESS:
        raise ValueError("attribute_type is not a Type: 1, 1C, 2, 2C, or 3")
    offers = _OFFERS[action]
    target = _TARGET[_STRICTNESS[attribute_type]]
    # Every compound action offers D, or U in its place, so one follows.
    return next(offers[c] for c in _ORDER[_ORDER.index(target) :] if c in offers)


def resolve_in_iod(iod: IOD, tag: str, path: Sequence[str], action: str) -> str:
    """Return the action that a compound action gives an attribute in an IOD.

    This combines :func:`strictest_type` and :func:`resolve`.

    Parameters
    ----------
    iod : IOD
        The instance's IOD.
    tag : str
        The attribute's tag, such as ``"(0008,0080)"``, with upper-case
        hexadecimal digits.
    path : sequence of str
        The tags of the sequences whose items contain the attribute,
        outermost first, or ``()`` at the top level of the data set.
    action : str
        A compound action of Table E.1-1a, such as ``"X/Z/D"``.

    Returns
    -------
    str
        ``"X"``, ``"Z"``, ``"D"``, or ``"U"``.

    Raises
    ------
    ValueError
        If ``action`` is not a compound action, or ``tag`` or ``path`` is
        malformed, as for :func:`strictest_type` and :func:`resolve`.
    """
    return resolve(action, strictest_type(iod, tag, path))


def resolve_plain_in_iod(iod: IOD, tag: str, path: Sequence[str], action: str) -> str:
    """Return the action that a plain action gives an attribute in an IOD.

    A plain D on an attribute that the IOD does not define at that place
    gives X: Note 13 after Table E.1-1a says that an attribute given D
    because an IOD requires it, "if encountered in an image instance, it
    should simply be removed (treated as X)". A plain Z on an attribute that
    is Type 1 or 1C there, by :func:`strictest_type`, gives D, the
    non-zero-length dummy value that Table E.1-1a allows Z. Every other plain
    action, and D and Z elsewhere, is returned unchanged; a plain Z on an
    attribute that the IOD does not define there stays Z.

    Parameters
    ----------
    iod : IOD
        The instance's IOD.
    tag : str
        The attribute's tag, such as ``"(0040,A073)"``, with upper-case
        hexadecimal digits.
    path : sequence of str
        The tags of the sequences whose items contain the attribute,
        outermost first, or ``()`` at the top level of the data set.
    action : str
        A plain action of Table E.1-1a, one of :data:`PLAIN_ACTIONS`.

    Returns
    -------
    str
        ``"X"``, ``"Z"``, ``"D"``, ``"K"``, ``"C"``, or ``"U"``.

    Raises
    ------
    ValueError
        If ``action`` is not a plain action, or ``tag`` or ``path`` is
        malformed, as for :func:`strictest_type`.

    Examples
    --------
    Verifying Observer Sequence (0040,A073), which Table E.1-1 gives D, is
    defined only in Structured Report IODs:

    >>> from pymedphys._dicom.deidentify.iods import load_iod_tables
    >>> iods = load_iod_tables().iods
    >>> resolve_plain_in_iod(iods["CT Image"], "(0040,A073)", (), "D")
    'X'
    >>> resolve_plain_in_iod(iods["Comprehensive SR"], "(0040,A073)", (), "D")
    'D'
    """
    definitions = iod.lookup(tag, _checked_path(tag, path))
    if not isinstance(action, str) or action not in PLAIN_ACTIONS:
        raise ValueError(
            "action is not a plain action of Table E.1-1a: "
            + ", ".join(sorted(PLAIN_ACTIONS))
        )
    if action == "D" and not definitions:
        return "X"
    if action == "Z" and _strictest(definitions) == "1":
        return "D"
    return action


def _overlay_plane_is_user_optional(iod: IOD) -> bool:
    """Return whether every module of ``iod`` that defines Overlay Data is U.

    Removing an overlay's whole group keeps the output valid only where its
    module is user-optional; where the IOD does not define Overlay Data at
    all, removing the group removes nothing the IOD requires.
    """
    usage = {module.module: module.usage for module in iod.modules}
    return all(
        usage[definition.module] == "U"
        for definition in iod.definitions
        if definition.tag == "(60xx,3000)"
    )


def resolve_plain_x_in_iod(iod: IOD, tag: str, path: Sequence[str]) -> PlainRemoval:
    """Return what a plain X on an attribute in an IOD removes with it.

    A plain X removes the attribute, as Table E.1-1a defines X, whatever its
    Type. Where the attribute is Type 3 at that place, by
    :func:`strictest_type`, or the IOD does not define it there, it is
    removed alone. Where the IOD requires it there, the innermost enclosing
    sequence that is Type 3 at its own place is removed with it, so that the
    output stays valid, and where no such sequence encloses it, the instance
    is sequestered. Two attributes are exceptions. Removing Overlay Data
    (60xx,3000) of an overlay group, one of the even groups 6000 to 601E,
    removes every attribute of the group, whatever their Types, where every
    module of the IOD that defines Overlay Data is user-optional, so the
    instance stays valid without it; of the first supported release's IODs,
    only CT Image, MR Image, and Positron Emission Tomography Image include
    the Overlay Plane Module, each as user-optional.
    Where the module is conditional, the general rule applies.
    ROI Interpreter Sequence (3006,004E) is removed alone, since its Type 1C
    condition needs ROI Creator Sequence (3006,004D), which Table E.1-1
    removes too.

    This decides from the IOD's Types alone; it changes no data set.

    Parameters
    ----------
    iod : IOD
        The instance's IOD.
    tag : str
        The attribute's tag, such as ``"(0010,2297)"``, with upper-case
        hexadecimal digits; for Overlay Data, the tag in its group, such as
        ``"(6000,3000)"``.
    path : sequence of str
        The tags of the sequences whose items contain the attribute,
        outermost first, or ``()`` at the top level of the data set.

    Returns
    -------
    PlainRemoval
        What to remove with the attribute, or that the instance is
        sequestered.

    Raises
    ------
    ValueError
        If ``tag`` or ``path`` is malformed, as for :func:`strictest_type`.

    Examples
    --------
    Responsible Person (0010,2297) is Type 2C at the top level of the
    Patient Module, so no sequence encloses it:

    >>> from pymedphys._dicom.deidentify.iods import load_iod_tables
    >>> ct = load_iod_tables().iods["CT Image"]
    >>> resolve_plain_x_in_iod(ct, "(0010,2297)", ()).extent
    <RemovalExtent.SEQUESTER: 'sequester'>
    >>> resolve_plain_x_in_iod(ct, "(0008,009C)", ()).extent
    <RemovalExtent.ATTRIBUTE: 'attribute'>
    >>> resolve_plain_x_in_iod(ct, "(6000,3000)", ()).extent
    <RemovalExtent.OVERLAY_GROUP: 'overlay group'>
    """
    checked = _checked_path(tag, path)
    if _OVERLAY_DATA.fullmatch(tag) and _overlay_plane_is_user_optional(iod):
        return PlainRemoval(RemovalExtent.OVERLAY_GROUP)
    if tag == _ROI_INTERPRETER_SEQUENCE:
        return PlainRemoval(RemovalExtent.ATTRIBUTE)
    if _strictest(iod.lookup(tag, checked)) == "3":
        return PlainRemoval(RemovalExtent.ATTRIBUTE)
    for depth in reversed(range(len(checked))):
        if _strictest(iod.lookup(checked[depth], checked[:depth])) == "3":
            return PlainRemoval(RemovalExtent.SEQUENCE, depth)
    return PlainRemoval(RemovalExtent.SEQUESTER)
