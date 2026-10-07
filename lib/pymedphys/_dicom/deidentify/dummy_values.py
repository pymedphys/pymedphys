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

"""The values that the Z and D actions of Table E.1-1a write.

Z writes a zero-length value, except as below. D writes one conspicuous
constant for each VR, the same whatever the source value, so it reveals
nothing, links no records, and is reproducible: ``DEIDENTIFIED`` for the text
VRs (LO, SH, LT, ST, UC, and UT) and PN, ``19000101`` for DA, ``000000`` for
TM, ``19000101000000`` for DT, and zero for the numeric strings (DS and IS)
and the binary numbers (FL, FD, SL, SS, SV, UL, US, and UV). Where the source
value equals that constant, D writes a second one, so the value always
changes: ``DE-IDENTIFIED``, ``19000102``, ``000001``, ``19000101000001``, or
one. A UI value takes its keyed replacement
(:func:`~pymedphys._dicom.deidentify.uids.replacement_uid`).

Every other VR, such as CS, SQ, AE, AS, AT, OB, OW, UN, and UR, has no
generic dummy value. D on an attribute of such a VR raises
:class:`NoDummyValueError`: the attribute needs a reviewed rule of its own,
and without one its instance is sequestered rather than given an invalid
value. Two sequences have such a rule (:func:`items_for_d`). D writes one
item in Person Identification Code Sequence (0040,1101), with Code Value
``DEIDENTIFIED``, Coding Scheme Designator ``99PYMEDPHYS``, and Code Meaning
``DEIDENTIFIED^DEIDENTIFIED``. In Referenced Performed Procedure Step
Sequence (0008,1111), it writes, for each source item, an item that refers
to a Modality Performed Procedure Step by the keyed replacement of the
source item's Referenced SOP Instance UID. ICC Profile (0028,2000), of VR
OB, has a rule too (:func:`icc_profile_for_d`): D writes a fixed profile of
the source profile's data colour space
(:mod:`~pymedphys._dicom.deidentify.icc_profiles`).

Where an attribute is Type 1 or 1C at its place in the data set, Z writes
D's dummy value, from :func:`values_for_d`, since a zero-length value would
make the attribute invalid there.

Some attributes take other values, which the engine writes instead of
calling this module. Under every preset, Patient ID (0010,0020) and Patient's
Name (0010,0010) take the subject's keyed pseudonyms
(:mod:`~pymedphys._dicom.deidentify.pseudonyms`), whether Z or D applies.
Under ``tps-import``, Patient's Birth Date (0010,0030) is to take a synthetic
birth date kept in the subject's profile
(:mod:`~pymedphys._dicom.deidentify.profiles`), which does not yet record one.

Dummy values never name PyMedPhys; the de-identification markers do. The one
exception is the Coding Scheme Designator above, which names who defines the
code, as a private coding scheme's designator conventionally does.
"""

from __future__ import annotations

import re
import types
from collections.abc import Mapping, Sequence
from typing import NamedTuple

from . import icc_profiles
from .keys import DeidKey
from .standard import VRS
from .uids import normalise_uid, replacement_uid
from .values import vm_problem

_TEXT = ("DEIDENTIFIED", "DE-IDENTIFIED")
_NUMERIC_STRING = ("0", "1")
# Each VR's constant, and the second constant that D writes where the source
# value equals the first. Read-only.
CONSTANTS: Mapping[str, tuple[str | int | float, str | int | float]] = (
    types.MappingProxyType(
        {
            **dict.fromkeys(("LO", "SH", "LT", "ST", "UC", "UT", "PN"), _TEXT),
            "DA": ("19000101", "19000102"),
            "TM": ("000000", "000001"),
            "DT": ("19000101000000", "19000101000001"),
            "DS": _NUMERIC_STRING,
            "IS": _NUMERIC_STRING,
            **dict.fromkeys(("FL", "FD"), (0.0, 1.0)),
            **dict.fromkeys(("SL", "SS", "SV", "UL", "US", "UV"), (0, 1)),
        }
    )
)
# The VRs that have a generic dummy value; UI's is the keyed replacement.
DUMMY_VRS = frozenset({*CONSTANTS, "UI"})

_NUMBERS = frozenset({"DS", "IS", "FL", "FD", "SL", "SS", "SV", "UL", "US", "UV"})
# The VRs whose values are numbers, not text, as values_problem takes them.
_BINARY_NUMBERS = _NUMBERS - {"DS", "IS"}
# Padding that a source value may carry: spaces, and NUL from some writers.
_PADDING = " \x00"
_UTC_OFFSET = re.compile(r"[+-][0-9]{4}$")
# The least value of each component that may be absent: a DT's month, day,
# hour, minute, and second, and a TM's minute and second.
_LEAST = {"DT": "00000101000000", "TM": "000000"}
# More values than any VM of PS3.6 requires: its largest least count is 16.
_MAX_COUNT = 64
_TAG_PATTERN = re.compile(r"\([0-9A-F]{4},[0-9A-F]{4}\)")

PERSON_IDENTIFICATION_CODE_SEQUENCE = "(0040,1101)"
REFERENCED_PERFORMED_PROCEDURE_STEP_SEQUENCE = "(0008,1111)"
ICC_PROFILE = "(0028,2000)"
_REFERENCED_SOP_CLASS_UID = "(0008,1150)"
_REFERENCED_SOP_INSTANCE_UID = "(0008,1155)"
# The Modality Performed Procedure Step SOP Class (PS3.4 Annex F), which the
# items written in Referenced Performed Procedure Step Sequence refer to.
MODALITY_PERFORMED_PROCEDURE_STEP = "1.2.840.10008.3.1.2.3.3"
# The descriptions of the profiles that D writes in place of ICC Profile, by
# data colour space; the second is written where the source equals the first.
_ICC_DESCRIPTIONS = {
    icc_profiles.RGB: (icc_profiles.srgb_profile, "sRGB"),
    icc_profiles.GREY: (icc_profiles.grey_profile, "grey"),
}
_CODE_VALUE = "(0008,0100)"
_CODING_SCHEME_DESIGNATOR = "(0008,0102)"
_CODE_MEANING = "(0008,0104)"
# The private coding scheme of PS3.16 Chapter 8 that defines the dummy code.
_DESIGNATOR = "99PYMEDPHYS"
# Code Meaning follows the rules of PN there, but not as a single component
# (PS3.3 Table 10-1), so each constant has two.
_MEANINGS = tuple(f"{text}^{text}" for text in _TEXT)


class DummyElement(NamedTuple):
    """One element of an item that D writes in a sequence."""

    tag: str
    vr: str
    value: str


class NoDummyValueError(Exception):
    """No generic dummy value can replace an attribute's value.

    D on an attribute of a VR without a generic dummy value, or on a UI
    attribute without a source UID to replace, needs a reviewed rule for that
    attribute, such as :func:`items_for_d` gives one sequence; without one,
    the instance is sequestered. This is not a
    :class:`ValueError`, so a handler for invalid arguments cannot catch it
    by accident. The message names the VR and never quotes a value.

    Attributes
    ----------
    vr : str
        The attribute's VR.
    """

    def __init__(self, vr: str, reason: str) -> None:
        super().__init__(reason)
        self.vr = vr


def _check_vr(vr: str) -> None:
    if vr not in VRS:
        raise ValueError("the VR must be one of PS3.5 Table 6.2-1, and only one")


def _least_count(vm: str) -> int:
    """Return the fewest values, other than none, that ``vm`` allows."""
    for count in range(1, _MAX_COUNT + 1):
        if vm_problem(vm, count) is None:
            return count
    raise ValueError("the VM must allow at least one value")


def _check_types(vr: str, source: Sequence[object]) -> None:
    """Refuse a source value of another type than values_problem takes."""
    if vr in _BINARY_NUMBERS:
        kind = "a number"
        wrong = any(
            isinstance(value, bool) or not isinstance(value, (int, float))
            for value in source
        )
    else:
        kind = "text"
        wrong = any(not isinstance(value, str) for value in source)
    if wrong:
        raise TypeError(f"each source value of VR {vr} must be {kind}")


def _comparable(vr: str, value: object) -> object:
    """Return ``value`` in the form in which D compares it with a constant."""
    text = str(value).strip(_PADDING)
    if vr in _NUMBERS:
        try:
            return float(text)
        except ValueError:
            return text
    if vr == "DA":
        # ACR-NEMA wrote dates as yyyy.mm.dd.
        return text.replace(".", "")
    if vr in _LEAST:
        if vr == "DT":
            text = _UTC_OFFSET.sub("", text)
        # ACR-NEMA wrote times as hh:mm:ss.
        whole, _, fraction = text.replace(":", "").partition(".")
        return whole + _LEAST[vr][len(whole) :], fraction.rstrip("0")
    if vr == "PN":
        # Trailing component and group delimiters do not change a name.
        text = text.rstrip("^=" + _PADDING)
    return text.casefold()


def comparison_key(vr: str, value: object) -> object:
    """Return ``value`` in the hashable form in which D compares it for ``vr``.

    Two values are the same as D compares them where their keys are equal,
    as :func:`same_value` gives.
    """
    return _comparable(vr, value)


def same_value(vr: str, value: object, other: object) -> bool:
    """Return whether two values are the same as D compares them for ``vr``.

    :func:`values_for_d` describes the comparison. For example, ``"0.0"``
    and ``"0"`` are the same DS value, and ``"Deidentified "`` and
    ``"DEIDENTIFIED"`` the same LO value.
    """
    return comparison_key(vr, value) == comparison_key(vr, other)


def values_for_z(vr: str) -> tuple[()]:
    """Return the values that Z writes: none, a zero-length value.

    An attribute without values is valid for every VR and VM, and is encoded
    with a value length of zero; for SQ, it is a sequence of no items. Where
    the attribute is Type 1 or 1C at its place in the data set, Z writes the
    values of :func:`values_for_d` instead.

    Raises
    ------
    ValueError
        If ``vr`` is not a single VR of PS3.5, such as ``"US or SS"``.
    """
    _check_vr(vr)
    return ()


def values_for_d(
    vr: str, vm: str, source: Sequence[object], key: DeidKey
) -> tuple[str | int | float, ...]:
    """Return the values that D writes in place of ``source``.

    D writes the VR's constant from :data:`CONSTANTS`, as many times as the
    fewest values the VM allows: once for VM 1 or 1-n, and twice for 2-2n.
    Where any source value equals the constant, it writes the second constant
    instead, so the value written always differs from the source's. A source
    value equals the constant when the two are the same once both are read
    as their VR defines them:

    - text and PN: ignoring case, and leading and trailing spaces and NULs;
      for PN, also trailing ``^`` and ``=`` delimiters, which do not change a
      name;
    - DA: ignoring padding and the full stops of the ACR-NEMA form
      ``yyyy.mm.dd``;
    - TM and DT: the same time, ignoring padding, a DT's UTC offset, the
      colons of the ACR-NEMA form ``hh:mm:ss``, and a fraction's trailing
      zeros, with absent components at their least values, so that ``00``
      and ``000000.000`` are both midnight and the DT ``1900`` is
      ``19000101000000``;
    - DS, IS, and the binary numbers: the same number, so that ``0.0``,
      ``-0``, and ``0e5`` all equal zero.

    Equality is deliberately broad: a value treated as equal only takes the
    second constant, which also differs from it.

    A UI attribute takes the keyed replacement of each source UID instead.

    Parameters
    ----------
    vr : str
        The VR that applies in the data set, such as ``"DA"``.
    vm : str
        The attribute's VM as PS3.6 gives it, such as ``"1-n"``.
    source : sequence
        The source values, as :func:`~pymedphys._dicom.deidentify.values.values_problem`
        takes them, or none.
    key : DeidKey
        The run's key, for a UI attribute.

    Returns
    -------
    tuple of str, int, or float
        The values, each as the engine sets it on a data set.

    Raises
    ------
    NoDummyValueError
        If ``vr`` has no generic dummy value, or is UI and a source value is
        empty or there is none.
    TypeError
        If ``source`` is a single value, such as a string, not a sequence, or
        holds a value of another type than ``values_problem`` takes for the
        VR: text for the string VRs, and an ``int`` or ``float`` for the
        binary numbers.
    ValueError
        If ``vr`` is not a single VR of PS3.5, or ``vm`` is not of a form
        PS3.6 uses.

    Examples
    --------
    >>> key = DeidKey(bytes(32))
    >>> values_for_d("DA", "1", ["20240229"], key)
    ('19000101',)
    >>> values_for_d("DA", "1", ["19000101"], key)
    ('19000102',)
    """
    if isinstance(source, (str, bytes, bytearray)) or not isinstance(source, Sequence):
        raise TypeError("source must be a sequence of values, not a single value")
    _check_vr(vr)
    count = _least_count(vm)
    if vr == "UI":
        _check_types(vr, source)
        if not source or not all(normalise_uid(str(value)) for value in source):
            raise NoDummyValueError(vr, "an empty UI value has no keyed replacement")
        return tuple(replacement_uid(key, str(value)) for value in source)
    if vr not in CONSTANTS:
        raise NoDummyValueError(vr, f"VR {vr} has no generic dummy value")
    _check_types(vr, source)
    first, second = CONSTANTS[vr]
    equal = any(same_value(vr, value, first) for value in source)
    return (second if equal else first,) * count


def items_for_d(
    tag: str,
    source: Sequence[Mapping[str, str]],
    key: DeidKey | None = None,
) -> tuple[tuple[DummyElement, ...], ...]:
    """Return the items that D writes in a sequence with a reviewed rule.

    Two sequences have one:

    - Person Identification Code Sequence (0040,1101): one item, with Code
      Value (0008,0100) ``DEIDENTIFIED``, Coding Scheme Designator
      (0008,0102) ``99PYMEDPHYS``, and Code Meaning (0008,0104)
      ``DEIDENTIFIED^DEIDENTIFIED``. Where any source item's Code Value
      equals ``DEIDENTIFIED`` as SH text, or its Code Meaning equals
      ``DEIDENTIFIED^DEIDENTIFIED`` as a PN, as :func:`values_for_d` compares
      them, the item takes ``DE-IDENTIFIED`` and
      ``DE-IDENTIFIED^DE-IDENTIFIED`` instead, with the same designator.
    - Referenced Performed Procedure Step Sequence (0008,1111): for each
      source item, one item, with Referenced SOP Class UID (0008,1150) the
      Modality Performed Procedure Step SOP Class,
      :data:`MODALITY_PERFORMED_PROCEDURE_STEP`, and Referenced SOP Instance
      UID (0008,1155) the keyed replacement of the source item's, as D
      replaces a UI value. A sequence without items, or with an item
      without a Referenced SOP Instance UID, has no dummy value.

    Parameters
    ----------
    tag : str
        The sequence's tag, such as ``"(0040,1101)"``, with upper-case
        hexadecimal digits.
    source : sequence of mapping
        The source items, each mapping a tag, such as ``"(0008,0100)"``, to
        that element's value as text. Only Code Value and Code Meaning, or
        Referenced SOP Instance UID, are read.
    key : DeidKey, optional
        The run's key, which Referenced Performed Procedure Step Sequence
        needs.

    Returns
    -------
    tuple of tuple of DummyElement
        The items, each its elements in the order of their tags.

    Raises
    ------
    NoDummyValueError
        If no reviewed rule gives the sequence items, or the source has no
        UID for its rule to replace.
    TypeError
        If ``source`` is not a sequence of mappings, a value it reads is not
        text, or Referenced Performed Procedure Step Sequence is given no key.
    ValueError
        If ``tag`` is not of the form ``(gggg,eeee)`` with upper-case
        hexadecimal digits.

    Examples
    --------
    >>> (item,) = items_for_d("(0040,1101)", [])
    >>> [element.value for element in item]
    ['DEIDENTIFIED', '99PYMEDPHYS', 'DEIDENTIFIED^DEIDENTIFIED']
    >>> source = [{"(0008,1155)": "1.2.3.4"}]
    >>> (item,) = items_for_d("(0008,1111)", source, DeidKey(bytes(32)))
    >>> item[0].value
    '1.2.840.10008.3.1.2.3.3'
    """
    if not isinstance(tag, str) or not _TAG_PATTERN.fullmatch(tag):
        raise ValueError(
            "tag is not of the form (gggg,eeee) with upper-case hexadecimal digits"
        )
    if (
        isinstance(source, (str, bytes, bytearray, Mapping))
        or not isinstance(source, Sequence)
        or not all(isinstance(item, Mapping) for item in source)
    ):
        raise TypeError("source must be a sequence of items, each a mapping")
    if tag == REFERENCED_PERFORMED_PROCEDURE_STEP_SEQUENCE:
        if key is None:
            raise TypeError("a key is needed to replace a Referenced SOP Instance UID")
        return _procedure_step_items(source, key)
    if tag != PERSON_IDENTIFICATION_CODE_SEQUENCE:
        raise NoDummyValueError("SQ", "no reviewed rule gives this sequence items")
    # Each source value with the VR as which it is compared, and its constant.
    compared = [
        (vr, item[t], constant)
        for item in source
        for t, vr, constant in (
            (_CODE_VALUE, "SH", _TEXT[0]),
            (_CODE_MEANING, "PN", _MEANINGS[0]),
        )
        if t in item
    ]
    if not all(isinstance(value, str) for _, value, _ in compared):
        raise TypeError("each source Code Value and Code Meaning must be text")
    equal = any(same_value(vr, value, constant) for vr, value, constant in compared)
    index = 1 if equal else 0
    return (
        (
            DummyElement(_CODE_VALUE, "SH", _TEXT[index]),
            DummyElement(_CODING_SCHEME_DESIGNATOR, "SH", _DESIGNATOR),
            DummyElement(_CODE_MEANING, "LO", _MEANINGS[index]),
        ),
    )


def _procedure_step_items(
    source: Sequence[Mapping[str, str]], key: DeidKey
) -> tuple[tuple[DummyElement, ...], ...]:
    """Return D's items for Referenced Performed Procedure Step Sequence."""
    uids = [item.get(_REFERENCED_SOP_INSTANCE_UID) for item in source]
    if not all(isinstance(uid, str) or uid is None for uid in uids):
        raise TypeError("each source Referenced SOP Instance UID must be text")
    if not uids or not all(uid is not None and normalise_uid(uid) for uid in uids):
        raise NoDummyValueError(
            "SQ", "a source item has no Referenced SOP Instance UID to replace"
        )
    return tuple(
        (
            DummyElement(
                _REFERENCED_SOP_CLASS_UID, "UI", MODALITY_PERFORMED_PROCEDURE_STEP
            ),
            DummyElement(
                _REFERENCED_SOP_INSTANCE_UID, "UI", replacement_uid(key, str(uid))
            ),
        )
        for uid in uids
    )


def icc_profile_for_d(source: bytes) -> bytes:
    """Return the profile that D writes in place of ICC Profile (0028,2000).

    The profile is fixed for the source profile's data colour space, which
    its header gives: the sRGB profile of
    :func:`~pymedphys._dicom.deidentify.icc_profiles.srgb_profile` for RGB,
    described ``DEIDENTIFIED sRGB``, or the grey profile of
    :func:`~pymedphys._dicom.deidentify.icc_profiles.grey_profile` for grey,
    described ``DEIDENTIFIED grey``. Where the source has the same bytes,
    the profile is described with ``DE-IDENTIFIED`` instead, so the value
    always changes.

    Raises
    ------
    NoDummyValueError
        If the source is not an ICC profile, or its data colour space is
        neither RGB nor grey.
    TypeError
        If ``source`` is not bytes.

    Examples
    --------
    >>> from pymedphys._dicom.deidentify import icc_profiles
    >>> source = icc_profiles.srgb_profile("A scanner's profile")
    >>> icc_profiles.data_colour_space(icc_profile_for_d(source))
    b'RGB '
    """
    if not isinstance(source, (bytes, bytearray)):
        raise TypeError("the source ICC Profile must be bytes")
    colour_space = icc_profiles.data_colour_space(bytes(source))
    if colour_space not in _ICC_DESCRIPTIONS:
        raise NoDummyValueError(
            "OB", "the source ICC Profile is neither an RGB nor a grey profile"
        )
    build, name = _ICC_DESCRIPTIONS[colour_space]
    first = build(f"{_TEXT[0]} {name}")
    return build(f"{_TEXT[1]} {name}") if bytes(source) == first else first
