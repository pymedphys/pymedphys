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

"""Per-subject date offsets and shifted dates.

Where Retain Longitudinal Temporal Information with Modified Dates is
selected, a subject's subject-event and radiation-source dates move backwards
by the same whole number of weeks, between 52 and 520 and never zero. Whole
weeks keep intervals, times of day, and weekdays, which fractionation analyses
need, and moving backwards avoids future-dated plans. Under a project key the
offset is read from the subject's profile; :func:`date_offset_weeks` gives the
offset a new subject receives. Before a DT value with its own UTC offset is
shifted, :func:`to_local_datetime` puts it in the instance's local time under
the nominal offset, and :func:`shift_frame_origin_timestamp` moves an IEEE 1588
frame timestamp.
"""

from __future__ import annotations

import datetime
import re
from collections.abc import Iterable

from .keys import DeidKey
from .pseudonyms import SubjectIdentity

MIN_OFFSET_WEEKS = 52
MAX_OFFSET_WEEKS = 520
# Every UTC offset under Modified Dates, once each value is in local time.
NOMINAL_UTC_OFFSET = "+0000"
_WEEK_SECONDS = 7 * 24 * 60 * 60
# An IEEE 1588 timestamp: 6 bytes of seconds and 4 of nanoseconds.
_PTP_SECONDS_BYTES = 6
_PTP_TIMESTAMP_BYTES = 10
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
_OFFSET = re.compile(r"[+-][0-9]{4}")


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
        shifted = day - datetime.timedelta(weeks=weeks)
    except OverflowError:
        raise ValueError("the shifted date would be before year 1") from None
    # strftime("%Y") does not zero-pad years before 1000 on every platform.
    return f"{shifted.year:04d}{shifted.month:02d}{shifted.day:02d}"


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

    The time and UTC offset are kept, so the time of day is unchanged; under
    Modified Dates, a value with its own offset is first put in the instance's
    local time with :func:`to_local_datetime`. A value without a full date,
    such as ``"2026"``, cannot be moved by whole weeks and is rejected; the
    caller decides what to write instead.

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
    return match["offset"] is None or _valid_offset(match["offset"])


def _valid_offset(offset: str) -> bool:
    if not _OFFSET.fullmatch(offset):
        return False
    hours, minutes = int(offset[1:3]), int(offset[3:])
    # PS3.5 Table 6.2-1: from -1200 to +1400, with UTC as +0000.
    return (
        minutes <= 59
        and hours * 60 + minutes <= (14 * 60 if offset[0] == "+" else 12 * 60)
        and offset != "-0000"
    )


def _offset_minutes(offset: str) -> int:
    minutes = int(offset[1:3]) * 60 + int(offset[3:])
    return -minutes if offset[0] == "-" else minutes


def _datetime_match(value: str) -> re.Match[str]:
    match = _DT.fullmatch(value.rstrip(_PADDING))
    if not match or not _valid_time(match) or not _valid_utc_offset(match):
        raise ValueError("the value is not a DT value with a full date")
    return match


def _wall_clock(match: re.Match[str]) -> datetime.datetime:
    """Return the value's date, hour, and minute, missing parts as zero."""
    date = match["date"]
    try:
        return datetime.datetime(
            int(date[:4]),
            int(date[4:6]),
            int(date[6:]),
            int(match["hour"] or 0),
            int(match["minute"] or 0),
        )
    except ValueError:
        raise ValueError("the value is not a DT value with a full date") from None


def local_offset(timezone_offset: str | None, datetimes: Iterable[str]) -> str | None:
    """Return the UTC offset of an instance's local time.

    This is the offset :func:`to_local_datetime` converts to. It is the
    instance's Timezone Offset From UTC (0008,0201) where present, because
    PS3.3 C.12.1.1.8 makes it the offset of every date and time without its
    own. Otherwise it is the offset of the earliest DT value that has one, so
    the values with offsets keep their intervals; with neither, ``None``.

    Raises
    ------
    ValueError
        If ``timezone_offset`` is not a UTC offset from -1200 to +1400, or a
        value is not a valid DT value with a full date.

    Examples
    --------
    >>> local_offset("+1000", ["20260927013000+0000"])
    '+1000'
    >>> local_offset(None, ["20260927120000+1000", "20260927013000+0000"])
    '+0000'
    """
    if timezone_offset is not None:
        offset = timezone_offset.rstrip(" ")
        if not _valid_offset(offset):
            raise ValueError("the time zone offset is not from -1200 to +1400")
        return offset
    earliest: tuple[datetime.datetime, str] | None = None
    for value in datetimes:
        match = _datetime_match(value)
        if match["offset"] is None:
            continue
        instant = _wall_clock(match) - datetime.timedelta(
            minutes=_offset_minutes(match["offset"])
        )
        if earliest is None or (instant, match["offset"]) < earliest:
            earliest = (instant, match["offset"])
    return None if earliest is None else earliest[1]


def to_local_datetime(value: str, offset: str) -> str:
    """Return a DT value in local time at ``offset``, labelled with the nominal offset.

    Under Retain Longitudinal Temporal Information with Modified Dates, every
    UTC offset in an instance becomes :data:`NOMINAL_UTC_OFFSET`. A value with
    its own offset is first converted to the instance's local time, from
    :func:`local_offset`, so it keeps its interval to the instance's other
    dates and times, including across midnight. The conversion keeps the
    value's precision, and seconds and fractions are unchanged. A value
    without its own offset is already local time and is returned without its
    padding.

    Raises
    ------
    ValueError
        If ``value`` is not a valid DT value with a full date, ``offset`` is
        not a UTC offset from -1200 to +1400, the value's precision cannot
        express the conversion exactly (a date alone between different
        offsets, or hours alone by a part of an hour), or the result would be
        before year 1.

    Examples
    --------
    >>> to_local_datetime("20260926233000.5-0200", "+1000")
    '20260927113000.5+0000'
    """
    match = _datetime_match(value)
    if not _valid_offset(offset):
        raise ValueError("the local offset is not from -1200 to +1400")
    if match["offset"] is None:
        return value.rstrip(_PADDING)
    difference = _offset_minutes(offset) - _offset_minutes(match["offset"])
    if (match["hour"] is None and difference) or (
        match["minute"] is None and difference % 60
    ):
        raise ValueError("the value's precision cannot express the conversion")
    try:
        local = _wall_clock(match) + datetime.timedelta(minutes=difference)
    except OverflowError:
        raise ValueError("the converted date would be before year 1") from None
    parts = [f"{local.year:04d}{local.month:02d}{local.day:02d}"]
    if match["hour"] is not None:
        parts.append(f"{local.hour:02d}")
    if match["minute"] is not None:
        parts.append(f"{local.minute:02d}")
    seconds = match["time"][4:]
    return "".join(parts) + seconds + NOMINAL_UTC_OFFSET


def shift_frame_origin_timestamp(value: bytes, weeks: int) -> bytes:
    """Return a Frame Origin Timestamp (0034,0007) moved back by ``weeks`` whole weeks.

    PS3.3 C.7.6.27.1.1 defines the value as an IEEE 1588 (PTPv2) timestamp:
    six bytes of seconds since 1970-01-01 00:00:00 TAI, then four bytes of
    nanoseconds, each in IEEE 1588's big-endian order. Only the seconds
    change, so the intervals between frames are kept exactly.

    Raises
    ------
    ValueError
        If ``value`` is not ten bytes with fewer than 10^9 nanoseconds,
        ``weeks`` is out of range, or the result would be before 1970.

    Examples
    --------
    >>> seconds = (1_790_000_000).to_bytes(6, "big")
    >>> shifted = shift_frame_origin_timestamp(seconds + bytes(4), 52)
    >>> int.from_bytes(shifted[:6], "big")
    1758550400
    """
    _check_weeks(weeks)
    if len(value) != _PTP_TIMESTAMP_BYTES or (
        int.from_bytes(value[_PTP_SECONDS_BYTES:], "big") >= 10**9
    ):
        raise ValueError("the value is not an IEEE 1588 timestamp")
    seconds = int.from_bytes(value[:_PTP_SECONDS_BYTES], "big")
    shifted = seconds - weeks * _WEEK_SECONDS
    if shifted < 0:
        raise ValueError("the shifted timestamp would be before 1970")
    return shifted.to_bytes(_PTP_SECONDS_BYTES, "big") + value[_PTP_SECONDS_BYTES:]
