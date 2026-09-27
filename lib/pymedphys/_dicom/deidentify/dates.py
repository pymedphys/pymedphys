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

"""Per-subject date offsets and shifted dates (design decision D-006).

Where Retain Longitudinal Temporal Information with Modified Dates is
selected, a subject's subject-event and radiation-source dates (D-007) move
backwards by the same whole number of weeks, between 52 and 520 and never
zero. Whole weeks keep intervals, times of day, and weekdays, which
fractionation analyses need, and moving backwards avoids future-dated plans.
Under a project key the offset is read from the subject's profile (D-004);
:func:`date_offset_weeks` gives the offset a new subject receives.
"""

from __future__ import annotations

import datetime
import re

from .keys import DeidKey
from .pseudonyms import SubjectIdentity

MIN_OFFSET_WEEKS = 52
MAX_OFFSET_WEEKS = 520
_OFFSET_CHOICES = MAX_OFFSET_WEEKS - MIN_OFFSET_WEEKS + 1
# Trailing padding a DA or DT value may carry.
_PADDING = " \x00"
_DA = re.compile(r"[0-9]{8}")
# A DT value with a full date (PS3.5 Table 6.2-1): YYYYMMDD, then optionally
# HH, MM, SS, and a fraction of one to six digits, each only after the one
# before, and optionally a UTC offset &ZZXX.
_DT = re.compile(
    r"(?P<date>[0-9]{8})"
    r"(?P<time>(?:(?P<hour>[0-9]{2})(?:(?P<minute>[0-9]{2})"
    r"(?:(?P<second>[0-9]{2})(?:\.[0-9]{1,6})?)?)?)?)"
    r"(?P<offset>[+-][0-9]{4})?"
)


def date_offset_weeks(key: DeidKey, identity: SubjectIdentity) -> int:
    """Return the date offset, in whole weeks backwards, for a new subject.

    It is 52 plus the first 64 bits of the key's ``"date-offset"``
    derivation of the identity, modulo 469, so every offset from 52 to 520
    weeks is equally likely, to within one part in 10^16, and none is zero.
    """
    token = key.derive("date-offset", *identity.parts)
    return MIN_OFFSET_WEEKS + int.from_bytes(token[:8], "big") % _OFFSET_CHOICES


def _check_weeks(weeks: int) -> None:
    if (
        isinstance(weeks, bool)
        or not isinstance(weeks, int)
        or not MIN_OFFSET_WEEKS <= weeks <= MAX_OFFSET_WEEKS
    ):
        raise ValueError("a date offset must be 52 to 520 whole weeks")


def _shifted(date: str, weeks: int, invalid: str) -> str:
    """Return ``date`` moved back by ``weeks``, raising ``invalid`` if it is no date."""
    try:
        day = datetime.datetime.strptime(date, "%Y%m%d").date()
    except ValueError:
        raise ValueError(invalid) from None
    try:
        return (day - datetime.timedelta(weeks=weeks)).strftime("%Y%m%d")
    except OverflowError:
        raise ValueError("the shifted date would be before year 1") from None


def shift_date(value: str, weeks: int) -> str:
    """Return a DA value moved back by ``weeks`` whole weeks.

    Parameters
    ----------
    value : str
        A DA value, ``YYYYMMDD``, possibly with trailing padding.
    weeks : int
        The subject's offset, 52 to 520.

    Raises
    ------
    ValueError
        If ``value`` is not a valid DA value, if ``weeks`` is out of range,
        or if the shifted date would be before year 1.

    Examples
    --------
    >>> shift_date("20260927", 52)
    '20250928'
    """
    _check_weeks(weeks)
    date = value.rstrip(_PADDING)
    invalid = "the value is not a DA value"
    if not _DA.fullmatch(date):
        raise ValueError(invalid)
    return _shifted(date, weeks, invalid)


def shift_datetime(value: str, weeks: int) -> str:
    """Return a DT value with its date moved back by ``weeks`` whole weeks.

    The time and UTC offset are kept, so the time of day is unchanged. A
    value without a full date, such as ``"2026"``, cannot be moved by whole
    weeks and is rejected; the caller decides what to write instead.

    Raises
    ------
    ValueError
        If ``value`` is not a valid DT value with a full date, if ``weeks``
        is out of range, or if the shifted date would be before year 1.

    Examples
    --------
    >>> shift_datetime("20260927143015.123+1000", 52)
    '20250928143015.123+1000'
    """
    _check_weeks(weeks)
    invalid = "the value is not a DT value with a full date"
    stripped = value.rstrip(_PADDING)
    match = _DT.fullmatch(stripped)
    if not match or not _valid_time(match) or not _valid_utc_offset(match):
        raise ValueError(invalid)
    return _shifted(match["date"], weeks, invalid) + stripped[len(match["date"]) :]


def _valid_time(match: re.Match[str]) -> bool:
    limits = (("hour", 23), ("minute", 59), ("second", 60))
    return all(match[part] is None or int(match[part]) <= top for part, top in limits)


def _valid_utc_offset(match: re.Match[str]) -> bool:
    offset = match["offset"]
    if offset is None:
        return True
    hours, minutes = int(offset[1:3]), int(offset[3:])
    return minutes <= 59 and (hours <= 14 if offset[0] == "+" else hours <= 12)
