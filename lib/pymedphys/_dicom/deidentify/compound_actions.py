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

"""Resolve the compound actions of Table E.1-1a from an attribute's PS3.3 Type.

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

This module chooses the action; it writes no value. Its errors never repeat
a value.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from .iods import IOD

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

# Each Type of PS3.5 Section 7.4 by its strictness. No condition is
# evaluated, so 1C counts as 1 and 2C as 2.
_STRICTNESS = {"1": "1", "1C": "1", "2": "2", "2C": "2", "3": "3"}
# The action that each strictness calls for.
_TARGET = {"1": "D", "2": "Z", "3": "X"}

# A tag as the IOD tables give it, with upper-case hexadecimal digits.
_TAG_PATTERN = re.compile(r"\([0-9A-F]{4},[0-9A-F]{4}\)")


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
    types = (_STRICTNESS[d.type] for d in iod.lookup(tag, _checked_path(tag, path)))
    return min(types, default="3")


def resolve(action: str, attribute_type: str) -> str:
    """Return the action that a compound action gives an attribute of a Type.

    The Type calls for D (1 or 1C), Z (2 or 2C), or X (3). Where ``action``
    does not offer it, the next of X, Z, and D that ``action`` offers
    applies. In X/Z/U*, U takes the place of D, and in X/Z, D, the
    non-zero-length dummy value that Table E.1-1a allows Z.

    Plain actions (D, Z, X, K, C, and U) are rejected rather than passed
    through. They do not depend on the Type, and passing X through would
    suggest that removing the attribute had been checked against its Type,
    which this module does not do for plain actions.

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
