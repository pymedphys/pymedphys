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

Z writes a zero-length value. D writes one conspicuous constant for each VR,
the same whatever the source value, so it reveals nothing, links no records,
and is reproducible: ``DEIDENTIFIED`` for the text VRs (LO, SH, LT, ST, UC,
and UT) and PN, ``19000101`` for DA, ``000000`` for TM, ``19000101000000``
for DT, and zero for the numeric strings (DS and IS) and the binary numbers
(FL, FD, SL, SS, SV, UL, US, and UV). Where the source value equals that
constant, D writes a second one, so the value always changes:
``DE-IDENTIFIED``, ``19000102``, ``000001``, ``19000101000001``, or one. A UI
value takes its keyed replacement
(:func:`~pymedphys._dicom.deidentify.uids.replacement_uid`).

Every other VR, such as CS, SQ, AE, AS, AT, OB, OW, UN, and UR, has no
generic dummy value. D on an attribute of such a VR raises
:class:`NoDummyValueError`: the attribute needs a reviewed rule of its own,
and without one its instance is sequestered rather than given an invalid
value.

Some attributes take other values, which the engine writes instead of
calling this module. Under every preset, Patient ID (0010,0020) and Patient's
Name (0010,0010) take the subject's keyed pseudonyms
(:mod:`~pymedphys._dicom.deidentify.pseudonyms`), whether Z or D applies.
Under ``tps-import``, Patient's Birth Date (0010,0030) is to take a synthetic
birth date kept in the subject's profile
(:mod:`~pymedphys._dicom.deidentify.profiles`), which does not yet record one.

Dummy values never name PyMedPhys; the de-identification markers do.
"""

from __future__ import annotations

import re
import types
from collections.abc import Mapping, Sequence

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
# Padding that a source value may carry: spaces, and NUL from some writers.
_PADDING = " \x00"
_UTC_OFFSET = re.compile(r"[+-][0-9]{4}$")
# The least value of each component that may be absent: a DT's month, day,
# hour, minute, and second, and a TM's minute and second.
_LEAST = {"DT": "00000101000000", "TM": "000000"}
# More values than any VM of PS3.6 requires: its largest least count is 16.
_MAX_COUNT = 64


class NoDummyValueError(Exception):
    """No generic dummy value can replace an attribute's value.

    D on an attribute of a VR without a generic dummy value, or on a UI
    attribute without a source UID to replace, needs a reviewed rule for that
    attribute; without one, the instance is sequestered. This is not a
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


def values_for_z(vr: str) -> tuple[()]:
    """Return the values that Z writes: none, a zero-length value.

    An attribute without values is valid for every VR and VM, and is encoded
    with a value length of zero; for SQ, it is a sequence of no items.

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
    instead, so no source value is written. A source value equals the
    constant when the two are the same once both are read as their VR
    defines them:

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
        If ``source`` is a single value, such as a string, not a sequence.
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
        if not source or not all(normalise_uid(str(value)) for value in source):
            raise NoDummyValueError(vr, "an empty UI value has no keyed replacement")
        return tuple(replacement_uid(key, str(value)) for value in source)
    if vr not in CONSTANTS:
        raise NoDummyValueError(vr, f"VR {vr} has no generic dummy value")
    first, second = CONSTANTS[vr]
    equal = any(_comparable(vr, value) == _comparable(vr, first) for value in source)
    return (second if equal else first,) * count
