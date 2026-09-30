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

"""Check values against their VR and VM before the engine writes them.

Every value the engine writes, whether a replacement, a dummy value, or a
value a user rule supplies, must be valid for its attribute. A value is
checked against its VR's definition in DICOM PS3.5 Table 6.2-1, as the engine
sets it on a data set: a Python string for a text VR, before the encoding
adds any padding byte; an integer or float for a binary number; and bytes for
an OB, OD, OF, OL, OV, OW, or UN value. The number of values is checked
against the attribute's VM in the pinned PS3.6 data dictionary.

What is wrong is described without quoting the value, so the result can be
reported and logged even when the value is identifying.
"""

from __future__ import annotations

import datetime
import math
import re
import unicodedata
from collections.abc import Callable, Sequence

from .standard import VM_PATTERN
from .uid_registry import is_uid

_ESC = "\x1b"
# The controls a text VR (ST, LT, UT) may contain, besides ESC.
_TEXT_CONTROLS = frozenset({"\t", "\n", "\f", "\r", _ESC})
_DEFAULT_REPERTOIRE = re.compile(r"[\x20-\x7e]*")
_FL_MAX = 3.4028234663852886e38
_UNLIMITED = 2**32 - 2

_AS = re.compile(r"[0-9]{3}[DWMY]")
_CS = re.compile(r"[A-Z0-9 _]*")
_DA = re.compile(r"(?P<year>[0-9]{4})(?P<month>[0-9]{2})(?P<day>[0-9]{2})")
# A fixed point number, or a floating point number as ANSI X3.9 (Fortran 77)
# writes one, optionally padded with spaces.
_DS = re.compile(r" *[+-]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)? *")
_IS = re.compile(r" *[+-]?[0-9]+ *")
_TIME = (
    r"(?P<hour>[0-9]{2})(?:(?P<minute>[0-9]{2})"
    r"(?:(?P<second>[0-9]{2})(?:\.[0-9]{1,6})?)?)?"
)
_TM = re.compile(_TIME + " *")
# Each component is optional once those before it are present, and a UTC
# offset may follow whichever is last.
_DT = re.compile(
    r"(?P<year>[0-9]{4})(?:(?P<month>[0-9]{2})(?:(?P<day>[0-9]{2})"
    rf"(?:{_TIME})?)?)?"
    r"(?P<offset>(?P<sign>[+-])(?P<zone_hours>[0-9]{2})(?P<zone_minutes>[0-9]{2}))?"
    r" *"
)
# RFC 3986 Section 2: unreserved and reserved characters, and "%" to start a
# percent-encoded octet.
_UR = re.compile(r"(?:[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=]|%[0-9A-Fa-f]{2})*")

_INTEGER_RANGES = {
    "AT": (0, 2**32 - 1),
    "SL": (-(2**31), 2**31 - 1),
    "SS": (-(2**15), 2**15 - 1),
    "SV": (-(2**63), 2**63 - 1),
    "UL": (0, 2**32 - 1),
    "US": (0, 2**16 - 1),
    "UV": (0, 2**64 - 1),
}
# The size in bytes of each word of a byte VR.
_WORD_BYTES = {"OB": 1, "UN": 1, "OW": 2, "OF": 4, "OL": 4, "OD": 8, "OV": 8}


def _has_controls(value: str, allowed: frozenset[str]) -> bool:
    return any(
        unicodedata.category(char) == "Cc" and char not in allowed for char in value
    )


def _gregorian_date(year: str, month: str, day: str) -> bool:
    try:
        datetime.date(int(year), int(month), int(day))
    except ValueError:
        return False
    return True


def _time_in_range(match: re.Match[str]) -> bool:
    hour, minute, second = (match["hour"], match["minute"], match["second"])
    return (
        (hour is None or int(hour) <= 23)
        and (minute is None or int(minute) <= 59)
        and (second is None or int(second) <= 60)
    )


def _utc_offset_in_range(match: re.Match[str]) -> bool:
    # The range is -1200 to +1400, and -0000 is not allowed (PS3.5 Table
    # 6.2-1, DT).
    if match["offset"] is None:
        return True
    hours, minutes = int(match["zone_hours"]), int(match["zone_minutes"])
    signed = (hours * 60 + minutes) * (-1 if match["sign"] == "-" else 1)
    return (
        minutes <= 59 and -12 * 60 <= signed <= 14 * 60 and match["offset"] != "-0000"
    )


def _check_ae(value: str) -> bool:
    return (
        len(value) <= 16
        and bool(_DEFAULT_REPERTOIRE.fullmatch(value))
        and "\\" not in value
        and (value == "" or value.strip(" ") != "")
    )


def _check_da(value: str) -> bool:
    match = _DA.fullmatch(value)
    return match is not None and _gregorian_date(*match.groups())


def _check_dt(value: str) -> bool:
    match = _DT.fullmatch(value)
    if match is None or len(value) > 26:
        return False
    month, day = match["month"], match["day"]
    if month is not None and not 1 <= int(month) <= 12:
        return False
    if day is not None and not _gregorian_date(match["year"], month, day):
        return False
    return _time_in_range(match) and _utc_offset_in_range(match)


def _check_tm(value: str) -> bool:
    match = _TM.fullmatch(value)
    return match is not None and len(value) <= 14 and _time_in_range(match)


def _check_is(value: str) -> bool:
    return (
        len(value) <= 12
        and bool(_IS.fullmatch(value))
        and -(2**31) <= int(value) <= 2**31 - 1
    )


def _check_pn(value: str) -> bool:
    groups = value.split("=")
    return (
        "\\" not in value
        and not _has_controls(value, frozenset({_ESC}))
        and len(groups) <= 3
        and all(len(group) <= 64 and group.count("^") <= 4 for group in groups)
    )


def _check_ur(value: str) -> bool:
    # A space is allowed only as trailing padding.
    return bool(_UR.fullmatch(value.rstrip(" ")))


def _short_text(max_length: int) -> Callable[[str], bool]:
    """Check LO, SH, and UC: no backslash, and no control except ESC."""
    return lambda value: (
        len(value) <= max_length
        and "\\" not in value
        and not _has_controls(value, frozenset({_ESC}))
    )


def _text(max_length: int) -> Callable[[str], bool]:
    """Check ST, LT, and UT, which may contain a backslash and some controls."""
    return lambda value: (
        len(value) <= max_length and not _has_controls(value, _TEXT_CONTROLS)
    )


# Each text VR's check and what a valid value is, from PS3.5 Table 6.2-1.
# Lengths are in characters, which for the Default Character Repertoire are
# also bytes.
_STRING_CHECKS: dict[str, tuple[Callable[[str], bool], str]] = {
    "AE": (_check_ae, "at most 16 printable characters, no backslash, not only spaces"),
    "AS": (lambda value: bool(_AS.fullmatch(value)), "nnnD, nnnW, nnnM, or nnnY"),
    "CS": (
        lambda value: len(value) <= 16 and bool(_CS.fullmatch(value)),
        "at most 16 upper-case letters, digits, spaces, and underscores",
    ),
    "DA": (_check_da, "YYYYMMDD, a date of the Gregorian calendar"),
    "DS": (
        lambda value: len(value) <= 16 and bool(_DS.fullmatch(value)),
        "a fixed or floating point number of at most 16 characters",
    ),
    "DT": (
        _check_dt,
        "YYYYMMDDHHMMSS.FFFFFF&ZZXX, with trailing components optional, "
        "values in range, and a UTC offset from -1200 to +1400",
    ),
    "IS": (_check_is, "an integer from -2**31 to 2**31 - 1 in at most 12 characters"),
    "LO": (_short_text(64), "at most 64 characters, no backslash or control"),
    "LT": (_text(10240), "at most 10240 characters, no control but TAB, CR, LF, FF"),
    "PN": (
        _check_pn,
        "up to three groups of at most 64 characters and five components, "
        "no backslash or control",
    ),
    "SH": (_short_text(16), "at most 16 characters, no backslash or control"),
    "ST": (_text(1024), "at most 1024 characters, no control but TAB, CR, LF, FF"),
    "TM": (_check_tm, "HHMMSS.FFFFFF, with trailing components optional"),
    "UC": (_short_text(_UNLIMITED), "no backslash or control"),
    "UI": (
        lambda value: value == "" or is_uid(value),
        "numeric components without leading zeros, in at most 64 characters",
    ),
    "UR": (_check_ur, "a URI of RFC 3986 characters, with no leading space"),
    "UT": (_text(_UNLIMITED), "no control but TAB, CR, LF, FF"),
}

# Every VR whose values can be checked: all but SQ, whose values are items.
CHECKED_VRS = frozenset({*_STRING_CHECKS, *_INTEGER_RANGES, "FL", "FD", *_WORD_BYTES})


def _number_problem(vr: str, value: object) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return f"is not a number, as an {vr} value must be"
    if vr in _INTEGER_RANGES:
        low, high = _INTEGER_RANGES[vr]
        if not isinstance(value, int) or not low <= value <= high:
            return f"is not an integer from {low} to {high}, as an {vr} value must be"
    elif vr == "FL" and math.isfinite(value) and abs(value) > _FL_MAX:
        return "is outside the range of a 32-bit float, as an FL value must not be"
    return None


def _bytes_problem(vr: str, value: object) -> str | None:
    if not isinstance(value, (bytes, bytearray)):
        return f"is not bytes, as an {vr} value must be"
    if len(value) % _WORD_BYTES[vr]:
        return f"is not a whole number of {_WORD_BYTES[vr]}-byte words"
    return None


def _string_problem(vr: str, value: object) -> str | None:
    if not isinstance(value, str):
        return f"is not text, as an {vr} value must be"
    check, description = _STRING_CHECKS[vr]
    if value and not check(value):
        return f"is not a valid {vr} value: {description}"
    return None


def value_problem(vr: str, value: object) -> str | None:
    """Return what is wrong with a value for its VR, or None if it is valid.

    Parameters
    ----------
    vr : str
        One VR other than SQ, such as ``"DA"``.
    value : str, int, float, or bytes
        One value, as the engine sets it on a data set: a string for a text
        VR, without the padding byte that encoding adds; an integer, or for
        FL and FD also a float, for a binary number or AT; bytes for OB, OD,
        OF, OL, OV, OW, and UN. An empty string or empty bytes is a valid
        empty value for its VR.

    Returns
    -------
    str or None
        What is wrong, such as ``"is not a valid DA value: YYYYMMDD, a date
        of the Gregorian calendar"``, without quoting the value; or None.

    Raises
    ------
    ValueError
        If ``vr`` is SQ or not a single VR of PS3.5.

    Examples
    --------
    >>> value_problem("AS", "018M") is None
    True
    >>> value_problem("DA", "19930230")
    'is not a valid DA value: YYYYMMDD, a date of the Gregorian calendar'
    """
    if vr not in CHECKED_VRS:
        raise ValueError("the VR must be one of PS3.5 Table 6.2-1 other than SQ")
    if vr in _WORD_BYTES:
        return _bytes_problem(vr, value)
    if vr in _STRING_CHECKS:
        return _string_problem(vr, value)
    return _number_problem(vr, value)


def _vm_bounds(vm: str) -> tuple[int, int | None, int]:
    """Return the least count, the greatest (None if unbounded), and the step."""
    match = VM_PATTERN.fullmatch(vm)
    if match is None:
        raise ValueError("the VM must be of a form PS3.6 uses, such as 1-n or 2-2n")
    low, high = match.groups()
    if high is None:
        return int(low), int(low), 1
    if high == "n":
        return int(low), None, 1
    if high.endswith("n"):
        if high[:-1] != low:
            raise ValueError("a VM such as 2-2n must repeat its first number")
        return int(low), None, int(low)
    if int(high) < int(low):
        raise ValueError("a VM's greatest count must not be less than its least")
    return int(low), int(high), 1


def vm_problem(vm: str, count: int) -> str | None:
    """Return what is wrong with a number of values for a VM, or None.

    Parameters
    ----------
    vm : str
        The VM as PS3.6 gives it, such as ``"1"``, ``"1-3"``, ``"2-2n"``, or
        alternatives such as ``"1-n or 1"``.
    count : int
        The number of values. An empty attribute has none, which every VM
        allows.

    Returns
    -------
    str or None
        What is wrong, such as ``"has 2 values where VM 3 requires 3"``; or
        None.

    Raises
    ------
    ValueError
        If ``vm`` is not of a form PS3.6 uses.
    """
    bounds = [_vm_bounds(alternative) for alternative in vm.split(" or ")]
    if count == 0:
        return None
    for low, high, step in bounds:
        if count >= low and (high is None or count <= high) and count % step == 0:
            return None
    return f"has {count} values where VM {vm} does not allow that many"


def values_problem(vr: str, vm: str, values: Sequence[object]) -> str | None:
    """Return what is wrong with an attribute's values, or None if they are valid.

    Parameters
    ----------
    vr : str
        The VR as PS3.6 gives it, such as ``"DS"``, or alternatives such as
        ``"US or SS"``, of which every value must fit the same one.
    vm : str
        The VM as PS3.6 gives it, as for :func:`vm_problem`.
    values : sequence
        The values, each as :func:`value_problem` takes it, or none for an
        empty attribute.

    Returns
    -------
    str or None
        What is wrong with the number of values, or with the first value that
        fits no alternative, such as ``"value 2 is not a valid CS value: ..."``;
        or None.

    Raises
    ------
    ValueError
        If ``vr`` or ``vm`` is not of a form PS3.6 uses, or a VR is SQ.
    """
    alternatives = vr.split(" or ")
    if not all(alternative in CHECKED_VRS for alternative in alternatives):
        raise ValueError("each VR must be one of PS3.5 Table 6.2-1 other than SQ")
    problem = vm_problem(vm, len(values))
    if problem or not values:
        return problem
    first = None
    for alternative in alternatives:
        found = next(
            (
                f"value {number} {problem}"
                for number, value in enumerate(values, start=1)
                if (problem := value_problem(alternative, value))
            ),
            None,
        )
        if found is None:
            return None
        first = first or found
    return first
