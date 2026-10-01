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

"""Remove a data set's private attributes, as the Basic Profile requires.

Table E.1-1 of DICOM PS3.15 gives "Private Attributes", tagged "(gggg,eeee)
where gggg is odd", the action X under the Basic Application Level
Confidentiality Profile, and Section E.3.10 says "When this Option is not
specified, all Private Attributes shall be removed". A de-identifier protects
every instance of an attribute of the table, "whether contained in the top
level Data Set or embedded in an Item of a Sequence of Items" (Section E.1.1),
so they are removed at every level of nesting.

The row names attributes by their group alone, so every element of an odd
group is removed:

- each private creator, (gggg,0010) to (gggg,00FF), including one that
  reserves a block with no elements, which PS3.5 Section 7.8.1 lets a
  de-identifier keep or remove;
- each private data element, whether or not its block has a creator;
- each element that PS3.5 Section 7.8.1 does not allow, in groups 0001, 0003,
  0005, 0007, and FFFF, or at (gggg,0001) to (gggg,000F) and (gggg,0100) to
  (gggg,0FFF), and each retired group length, (gggg,0000).

X removes a sequence with all its items and the attributes in them (Table
E.1-1a), so a private sequence is removed whole, whatever it holds, and is
listed without its contents.

Private attributes are found in the items of every standard sequence,
including one of VR UN, as pydicom reads a sequence that it does not know
from Implicit VR Little Endian. PS3.5 Section 6.2.2 lets a reader that knows
the VR of a value of VR UN decode it as Implicit VR Little Endian. A value
that pydicom leaves as UN, as it does where its own dictionary does not give
the attribute VR SQ, is decoded here, with the character set of the data set
that holds it. pydicom decodes some malformed values without an error, as
items that leave out part of the value, so a value decoded here is accepted
only if its items encode to the same bytes. pydicom writes the elements of
those items as it read them, except a sequence of undefined length, which it
decodes with the value, so that check does not see into a sequence of defined
length nested in them. Each, at every depth, is decoded here and checked in
the same way, with the character set of the item that holds it.

A value of VR UN, or one read without a VR from Implicit VR Little Endian, is
decoded only where the pinned dictionary or pydicom's gives its attribute VR
SQ. pydicom would decode any other with its attribute's VR, which can raise an
error or a warning that quotes the value, as diagnostics must never do, and
would change a value that other rules act on. Such a value holds no items, and
one whose attribute the dictionary does not list is not searched, since the
design has the engine remove an attribute that the dictionary does not list
and no reviewed rule covers.

Elements are named by their paths, never by their values. Finding them decodes
no value but those of sequences and of Specific Character Set (0008,0005), so
no private value is decoded. The File Meta Information is not part of the data
set; the design has the engine replace it whole.

The Retain Safe Private Option keeps the private attributes that are known to
be safe. No reviewed rules yet say which are, so a policy that selects it is
refused.
"""

from __future__ import annotations

import copy
import struct
from collections.abc import Sequence

from pymedphys._imports import pydicom

from .file_layout import ElementPath
from .policy import Policy, PolicyError
from .standard import PRIVATE_ATTRIBUTES_TAG, sequence_tags

RETAIN_SAFE_PRIVATE = "retain_safe_private"
# The action that removes an attribute, and a sequence with all its items.
REMOVE = "X"
_SPECIFIC_CHARACTER_SET = 0x00080005
# What pydicom raises when it cannot decode a value as items.
_DECODING_ERRORS = (EOFError, OSError, ValueError, struct.error)
_Items = tuple[tuple[str, int], ...]


class PrivateAttributeError(Exception):
    """A value that may hold private attributes cannot be read as items.

    The private attributes in it cannot all be found, so its instance is
    sequestered, unless a sequence that is removed holds the value, or is the
    value, and so removes it with everything in it. This is not a
    :class:`ValueError`, so a handler for invalid arguments cannot catch it
    by accident. The message names the element by its path and never quotes
    a value.

    Attributes
    ----------
    path : ElementPath
        The element whose value cannot be read.
    """

    def __init__(self, path: ElementPath) -> None:
        super().__init__(
            f"the value of {path} cannot be read as items, so the private "
            "attributes that it may hold cannot be found"
        )
        self.path = path


def private_attribute_paths(
    dataset: pydicom.Dataset, policy: Policy
) -> tuple[ElementPath, ...]:
    """Return the path of each private attribute that ``policy`` removes.

    Parameters
    ----------
    dataset : pydicom.Dataset
        The data set, which is not changed, apart from pydicom decoding the
        values of its sequences as it does whenever they are read.
    policy : Policy
        A validated policy that does not select Retain Safe Private.

    Returns
    -------
    tuple of ElementPath
        Each element of an odd group, at the top level and in the items of
        each standard sequence, in the order the data set holds them: by tag,
        and depth first. A private sequence is listed without its contents.

    Raises
    ------
    PolicyError
        If ``policy`` selects the Retain Safe Private Option, or gives private
        attributes another action than removal (X).
    PrivateAttributeError
        If pydicom cannot decode a standard sequence, or a standard sequence
        that pydicom leaves as VR UN, or a sequence nested at any depth in
        its items, does not decode to items that encode it exactly.

    Examples
    --------
    >>> from pymedphys._dicom.deidentify.policy import compose_policy
    >>> dataset = pydicom.Dataset()
    >>> dataset.add_new(0x00090010, "LO", "SYNTHETIC CREATOR")
    >>> dataset.add_new(0x00091001, "DS", "1.5")
    >>> beam = pydicom.Dataset()
    >>> beam.add_new(0x300B0010, "LO", "SYNTHETIC CREATOR")
    >>> dataset.BeamSequence = [pydicom.Dataset(), beam]
    >>> paths = private_attribute_paths(dataset, compose_policy("basic"))
    >>> [str(path) for path in paths]
    ['(0009,0010)', '(0009,1001)', '(300A,00B0)[1] > (300B,0010)']
    """
    _check(policy)
    return tuple(_visit(dataset, (), _encodings(dataset, None), remove=False))


def without_private_attributes(
    dataset: pydicom.Dataset, policy: Policy
) -> pydicom.Dataset:
    """Return a copy of ``dataset`` without the private attributes ``policy`` removes.

    The copy is a deep copy, from which the elements that
    :func:`private_attribute_paths` lists are removed, and nothing else
    changes, except that a standard sequence of VR UN from which one is
    removed holds its decoded items, with VR SQ, and so does each sequence
    nested in those items from which one is removed.

    Parameters
    ----------
    dataset : pydicom.Dataset
        The data set, which is not changed, apart from pydicom decoding the
        values of its sequences as it does whenever they are read.
    policy : Policy
        A validated policy that does not select Retain Safe Private.

    Returns
    -------
    pydicom.Dataset
        Of the same type as ``dataset``, such as a
        :class:`pydicom.dataset.FileDataset`.

    Raises
    ------
    PolicyError
        As :func:`private_attribute_paths` raises it.
    PrivateAttributeError
        As :func:`private_attribute_paths` raises it.
    """
    _check(policy)
    result = copy.deepcopy(dataset)
    _visit(result, (), _encodings(result, None), remove=True)
    return result


def _check(policy: Policy) -> None:
    """Refuse a policy that does not remove every private attribute."""
    if RETAIN_SAFE_PRIVATE in policy.options:
        raise PolicyError(
            "the Retain Safe Private Option keeps the private attributes that "
            "are known to be safe, and no reviewed rules yet say which are, so "
            "a policy that selects it cannot yet be applied"
        )
    action = policy.actions.get(PRIVATE_ATTRIBUTES_TAG)
    if action != REMOVE:
        raise PolicyError(
            f"the policy gives private attributes {action or 'no action'}, "
            f"but only their removal ({REMOVE}) is implemented"
        )


def _visit(
    dataset: pydicom.Dataset,
    items: _Items,
    encodings: list[str],
    remove: bool,
    exact: bool = False,
) -> list[ElementPath]:
    """Return the paths of the private attributes in ``dataset``, at every level.

    Remove them too if ``remove`` is true. ``items`` is the path to
    ``dataset``, and ``encodings`` the Python encodings of its text.
    ``exact`` is true in the items of a value that :func:`_decoded` checked,
    and in every item nested in them, at any depth.
    """
    found: list[ElementPath] = []
    for tag in sorted(dataset.keys()):
        path = ElementPath(items, f"({tag.group:04X},{tag.element:04X})")
        if tag.group % 2:
            found.append(path)
            if remove:
                del dataset[tag]
            continue
        sequence, decoded = _items(dataset, tag, path, encodings, exact)
        inner: list[ElementPath] = []
        for index, item in enumerate(sequence):
            within = (*items, (path.tag, index))
            item_encodings = _encodings(item, encodings)
            inner += _visit(item, within, item_encodings, remove, exact or decoded)
        if remove and inner and decoded:
            dataset[tag] = pydicom.DataElement(tag, "SQ", sequence)
        found += inner
    return found


def _items(
    dataset: pydicom.Dataset,
    tag: pydicom.tag.BaseTag,
    path: ElementPath,
    encodings: list[str],
    exact: bool,
) -> tuple[Sequence[pydicom.Dataset], bool]:
    """Return the items at ``tag``, and whether :func:`_decoded` decoded them.

    pydicom keeps an element that it has not decoded raw, with the VR it was
    read with, or none if it was read from Implicit VR Little Endian. A value
    of VR UN, or of none, holds items only if the pinned dictionary or
    pydicom's gives its attribute VR SQ; no other is decoded. pydicom decodes
    a sequence when it is read, but a value that it leaves as UN, and a raw
    element in an item that :func:`_decoded` checked (``exact``), whose bytes
    pydicom would write as they are, are decoded and checked here.
    """
    element: pydicom.DataElement | pydicom.dataelem.RawDataElement = dataset.get_item(
        tag, keep_deferred=True
    )
    if element.VR in (None, "UN"):
        if not _is_sequence(tag, path):
            return (), False
    elif element.VR != "SQ":
        return (), False
    if exact and isinstance(element, pydicom.dataelem.RawDataElement):
        return _decoded(element.value, path, encodings), True
    try:
        element = dataset[tag]
    # pydicom raises KeyError, when it raises its validation errors, for an
    # element without a VR whose attribute its dictionary does not list.
    except (*_DECODING_ERRORS, KeyError) as error:
        raise PrivateAttributeError(path) from error
    if element.VR == "SQ":
        return element.value, False
    if element.VR == "UN":
        return _decoded(element.value, path, encodings), True
    return (), False


def _is_sequence(tag: pydicom.tag.BaseTag, path: ElementPath) -> bool:
    """Return whether the pinned dictionary or pydicom's gives an attribute VR SQ."""
    if path.tag in sequence_tags():
        return True
    try:
        return pydicom.datadict.dictionary_VR(tag) == "SQ"
    except KeyError:
        return False


def _decoded(
    value: bytes | None, path: ElementPath, encodings: list[str]
) -> pydicom.Sequence:
    """Decode a value as Implicit VR Little Endian items, if they encode it."""
    if not value:  # pydicom reads a value of zero length as None
        return pydicom.Sequence()
    try:
        sequence = pydicom.values.convert_SQ(value, True, True, encodings)
        encoded = pydicom.filebase.DicomBytesIO()
        encoded.is_little_endian = True
        encoded.is_implicit_VR = True
        for item in sequence:
            pydicom.filewriter.write_sequence_item(encoded, item, encodings)
    except _DECODING_ERRORS as error:
        raise PrivateAttributeError(path) from error
    if encoded.getvalue() != value:
        raise PrivateAttributeError(path)
    return sequence


def _encodings(dataset: pydicom.Dataset, inherited: list[str] | None) -> list[str]:
    """Return the Python encodings of the text in ``dataset``.

    A data set's Specific Character Set (0008,0005) applies to it and to the
    items it holds, unless an item has one of its own.
    """
    element = dataset.get(_SPECIFIC_CHARACTER_SET)
    if element is not None and element.value:
        return pydicom.charset.convert_encodings(element.value)
    return inherited or pydicom.charset.convert_encodings(None)
