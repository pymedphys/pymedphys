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
the VR of a value of VR UN decode it as Implicit VR Little Endian. A value of
VR UN, or one read without a VR from Implicit VR Little Endian, that pydicom
has not yet decoded is decoded here, with the character set of the data set
that holds it, even where pydicom's dictionary gives the attribute VR SQ.
pydicom decodes some malformed values without an error, as items that leave
out part of the value, so a value decoded here is accepted only if
:func:`.sequences.decode_items` finds that it holds only items, and its items
encode to the same bytes. A raw value of VR SQ, from Explicit VR, is decoded
by pydicom in place, and so written from its items, once
:func:`.sequences.decode_items` finds that items fill it. pydicom writes the
elements of those items as it read them, except a sequence of undefined
length, which it decodes with the value, so that check does not see into a
sequence of defined length nested in them. Each, at every depth, is decoded here and checked in
the same way, with the character set of the item that holds it.

An item's text is in the Specific Character Set (0008,0005) of the item, or
else of the data set that holds it (PS3.5 Section 7.5.3). pydicom does not
map every value to codecs as it is given: a value that is not among its
terms, or several values that include ISO_IR 192, GB18030, or GBK, which
allow no code extensions. It reads text in such a character set with its
default encoding or one that it guesses, or, raising its validation errors,
raises an error. Such a character set is refused rather than read that way:
in an item, by the path of the sequence that holds the item, since pydicom
may already have read the item as it decoded the sequence, and at the top
level by its own path.

A value of VR UN, or one read without a VR from Implicit VR Little Endian, is
decoded only where the pinned dictionary or pydicom's gives its attribute VR
SQ. pydicom would decode any other with its attribute's VR, which can raise an
error or a warning that quotes the value, as diagnostics must never do, and
would change a value that other rules act on. Such a value holds no items, and
one whose attribute the dictionary does not list is not searched, since the
design has the engine remove an attribute that the dictionary does not list
and no reviewed rule covers. Explicit VR Little Endian can also store a
standard sequence with a VR other than SQ or UN, such as OB. pydicom does not
read such a value as items, so it is refused.

Elements are named by their paths, never by their values. Finding them decodes
no value but those of sequences and of Specific Character Set (0008,0005), so
no private value is decoded. pydicom's warnings and log records can quote the
values that it decodes, so the search runs within
:func:`.diagnostics.redacted_diagnostics`, which summarises pydicom's
warnings and log records while the search runs. pydicom's errors, whose messages can
also quote a value, are replaced by :class:`PrivateAttributeError`, not
chained to it. The File Meta Information is not part of the data set; the
design has the engine replace it whole.

The Retain Safe Private Option keeps the private attributes that are known to
be safe. No reviewed rules yet say which are, so a policy that selects it is
refused.
"""

from __future__ import annotations

import contextlib
import copy
import struct
from collections.abc import Sequence

from pymedphys._imports import pydicom


from .diagnostics import redacted_diagnostics
from .file_layout import ElementPath
from .policy import Policy, PolicyError, refuse_retain_safe_private
from .sequences import UnreadableItems, decode_items
from .standard import PRIVATE_ATTRIBUTES_TAG, sequence_tags

# The action that removes an attribute, and a sequence with all its items.
REMOVE = "X"
_SPECIFIC_CHARACTER_SET = 0x00080005
# The VRs with which a Specific Character Set can be stored: CS, or none in
# Implicit VR, or UN, which pydicom reads with the dictionary's CS.
_CHARACTER_SET_VRS = frozenset({None, "CS", "UN"})
_TOP_LEVEL_CHARACTER_SET = ElementPath((), "(0008,0005)")
# What pydicom raises when it cannot decode a value as items. Raising its
# validation errors, it raises LookupError for a character set that it does
# not know, and KeyError, a LookupError, for an element without a VR whose
# attribute its dictionary does not list. Where the caller's warning filters
# turn pydicom's warnings into errors, it raises the warning, whose message
# can quote a value.
_DECODING_ERRORS = (
    EOFError,
    LookupError,
    OSError,
    ValueError,
    struct.error,
    Warning,
)
_Items = tuple[tuple[str, int], ...]


class PrivateAttributeError(Exception):
    """A value that may hold private attributes cannot be decoded exactly.

    The value is that of a standard sequence, whose items can also be
    refused for their Specific Character Set (0008,0005), or of the top
    level's Specific Character Set, which applies to the text of each item
    that does not have its own.

    The private attributes in it cannot all be found, so its instance is
    sequestered, unless a sequence that is removed holds the value, or is the
    value, and so removes it with everything in it. This is not a
    :class:`ValueError`, so a handler for invalid arguments cannot catch it
    by accident. The message names the element by its path and never quotes
    a value.

    Attributes
    ----------
    path : ElementPath
        The element whose value cannot be decoded exactly.
    """

    def __init__(self, path: ElementPath) -> None:
        super().__init__(
            f"the value of {path} cannot be decoded exactly, so the private "
            "attributes that the data set may hold cannot all be found"
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
        its items, does not decode to items that encode it exactly; if a
        standard sequence is stored with a VR other than SQ or UN; or if the
        data set, or an item of a standard sequence, has a Specific Character
        Set that pydicom does not map to codecs as it is given, or that is
        stored with a VR other than CS.

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
    with redacted_diagnostics():
        encodings = _encodings(dataset, None, _TOP_LEVEL_CHARACTER_SET)
        return tuple(_visit(dataset, (), encodings, remove=False))


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
    with redacted_diagnostics():
        result = copy.deepcopy(dataset)
        encodings = _encodings(result, None, _TOP_LEVEL_CHARACTER_SET)
        _visit(result, (), encodings, remove=True)
    return result


def _check(policy: Policy) -> None:
    """Refuse a policy that does not remove every private attribute."""
    refuse_retain_safe_private(policy)
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
            item_encodings = _encodings(item, encodings, path)
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
    pydicom's gives its attribute VR SQ; no other is decoded. A value whose
    VR is neither SQ nor UN, where either dictionary gives its attribute VR
    SQ, is refused, since its items could not be searched. A raw value of VR
    UN or of none, and a raw element in an item that :func:`_decoded` checked
    (``exact``), whose bytes pydicom would write as they are, are decoded and
    checked here, since pydicom can decode a malformed value without an
    error; one that pydicom deferred is read first. Any other raw value, of
    VR SQ from Explicit VR, is decoded by pydicom in place, and written from
    its items, once :func:`.sequences.decode_items` finds that items fill it.
    A sequence that pydicom decoded as it read it is used as it is.
    """
    element: pydicom.DataElement | pydicom.dataelem.RawDataElement = dataset.get_item(
        tag, keep_deferred=True
    )
    if element.VR in (None, "UN"):
        if not _is_sequence(tag, path):
            return (), False
    elif element.VR != "SQ":
        if _is_sequence(tag, path):
            raise PrivateAttributeError(path)
        return (), False
    if isinstance(element, pydicom.dataelem.RawDataElement) and (
        exact or element.VR in (None, "UN")
    ):
        return _decoded(_raw_value(dataset, element, path), path, encodings), True
    if isinstance(element, pydicom.dataelem.RawDataElement):
        # Of VR SQ, from Explicit VR. pydicom decodes it in place, and it is
        # then written from its items, but it reads malformed items silently.
        try:
            decode_items(
                _raw_value(dataset, element, path) or b"",
                explicit=True,
                codecs=encodings,
                little_endian=element.is_little_endian,
                nested=False,
            )
        except UnreadableItems:
            raise PrivateAttributeError(path) from None
    try:
        element = dataset[tag]
    except _DECODING_ERRORS:
        raise PrivateAttributeError(path) from None
    if element.VR == "SQ":
        return element.value, False
    if element.VR == "UN":
        return _decoded(element.value, path, encodings), True
    return (), False


def _raw_value(
    dataset: pydicom.Dataset,
    element: pydicom.dataelem.RawDataElement,
    path: ElementPath,
) -> bytes | None:
    """Return a raw element's value, reading it now if pydicom deferred it.

    pydicom leaves a value longer than ``defer_size`` unread, as ``None``
    with its length, until it is accessed, so read as it is, a deferred
    sequence would pass for an empty one. Its bytes are read from the file or
    buffer the data set was read from, as pydicom reads a deferred value,
    without converting them, and the value is refused by ``path`` if they
    cannot be read, including from a source cut short since, or are not of
    the length the element was stored with.
    """
    if element.value is not None or element.length == 0:
        return element.value
    filename = getattr(dataset, "filename", None)
    buffer = getattr(dataset, "buffer", None)
    source = filename or buffer
    if filename and buffer and not getattr(buffer, "closed", False):
        source = buffer
    if source is None or (source is filename and not isinstance(filename, str)):
        # A filename that is not a path, such as the descriptor of a closed
        # reader, names nothing that can be opened again safely.
        raise PrivateAttributeError(path)
    fileobj_type = getattr(dataset, "fileobj_type", None) or open
    try:
        # pydicom closes a file that it opens itself only when the read
        # succeeds, so the file is opened, and always closed, here.
        with contextlib.ExitStack() as stack:
            if source is filename:
                source = stack.enter_context(fileobj_type(filename, "rb"))
            read = pydicom.filereader.read_deferred_data_element(
                fileobj_type, source, None, element
            )
    except (*_DECODING_ERRORS, TypeError, StopIteration):
        # pydicom raises StopIteration when the source ends at or within the
        # element's header.
        raise PrivateAttributeError(path) from None
    if not isinstance(read.value, bytes) or len(read.value) != element.length:
        raise PrivateAttributeError(path)
    return read.value


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
    """Decode a value as Implicit VR Little Endian items that fill and encode it."""
    if not value:  # pydicom reads a value of zero length as None
        return pydicom.Sequence()
    try:
        # Each sequence of defined length in the items is decoded here in turn.
        sequence = decode_items(value, explicit=False, codecs=encodings, nested=False)
    except UnreadableItems:
        raise PrivateAttributeError(path) from None
    try:
        encoded = pydicom.filebase.DicomBytesIO()
        encoded.is_little_endian = True
        encoded.is_implicit_VR = True
        for item in sequence:
            pydicom.filewriter.write_sequence_item(encoded, item, encodings)
    except _DECODING_ERRORS:
        raise PrivateAttributeError(path) from None
    if encoded.getvalue() != value:
        raise PrivateAttributeError(path)
    return sequence


def _encodings(
    dataset: pydicom.Dataset, inherited: list[str] | None, path: ElementPath
) -> list[str]:
    """Return the Python encodings of the text in ``dataset``.

    A data set's Specific Character Set (0008,0005) applies to it and to the
    items it holds, unless an item has one of its own. One is refused, by
    ``path``, unless pydicom maps it to codecs as it is given: each value is
    one of pydicom's terms, and, where there are several, none is ISO_IR 192,
    GB18030, or GBK, which allow no code extensions. One stored with a VR
    other than CS is refused too, before pydicom converts it, since
    converting it could raise an error that quotes the value.
    """
    stored = dataset.get_item(_SPECIFIC_CHARACTER_SET, keep_deferred=True)
    if stored is not None and stored.VR not in _CHARACTER_SET_VRS:
        raise PrivateAttributeError(path)
    try:
        element = dataset.get(_SPECIFIC_CHARACTER_SET)
    except _DECODING_ERRORS:
        raise PrivateAttributeError(path) from None
    if element is None or not element.value:
        return inherited or pydicom.charset.convert_encodings(None)
    value = element.value
    terms = [value] if isinstance(value, str) else list(value)
    if not all(term in pydicom.charset.python_encoding for term in terms) or (
        len(terms) > 1
        and any(term in pydicom.charset.STAND_ALONE_ENCODINGS for term in terms)
    ):
        raise PrivateAttributeError(path)
    return pydicom.charset.convert_encodings(terms)
