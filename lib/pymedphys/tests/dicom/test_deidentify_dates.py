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

"""Date offsets and shifted dates."""

import datetime
import hashlib
import hmac
import re

from pymedphys._imports import hypothesis, pytest

from pymedphys._dicom.deidentify import dates, keys, pseudonyms

st = hypothesis.strategies

FIXTURE_SECRET = bytes(range(32))
FIXTURE_KEY = keys.DeidKey(FIXTURE_SECRET)
FIXTURE_IDENTITY = pseudonyms.SubjectIdentity.from_patient_id(
    "MRN0001", "FIXTURE HOSPITAL"
)

any_key = st.binary(min_size=32, max_size=32).map(keys.DeidKey)
any_identity = (
    st.text(min_size=1, max_size=16)
    .filter(lambda value: value.strip(" \x00"))
    .map(pseudonyms.SubjectIdentity.from_patient_id)
)
any_weeks = st.integers(
    min_value=dates.MIN_OFFSET_WEEKS, max_value=dates.MAX_OFFSET_WEEKS
)
# Dates far enough from year 1 to shift by up to ten years.
any_date = st.dates(
    min_value=datetime.date(11, 1, 1), max_value=datetime.date(9999, 12, 31)
)


def _da(day):
    # strftime("%Y") does not zero-pad years before 1000 on every platform.
    return f"{day.year:04d}{day.month:02d}{day.day:02d}"


def _frame(value):
    return len(value).to_bytes(4, "big") + value


def test_an_offset_follows_the_specified_derivation():
    token = hmac.new(
        FIXTURE_SECRET,
        _frame(b"pymedphys-deid/1")
        + _frame(b"date-offset")
        + b"".join(_frame(part.encode()) for part in FIXTURE_IDENTITY.parts),
        hashlib.sha256,
    ).digest()

    assert dates.date_offset_weeks(FIXTURE_KEY, FIXTURE_IDENTITY) == (
        52 + int.from_bytes(token[:8], "big") % 469
    )


def test_offsets_are_pinned():
    assert dates.date_offset_weeks(FIXTURE_KEY, FIXTURE_IDENTITY) == 375


@hypothesis.given(any_key, any_identity)
def test_an_offset_is_52_to_520_whole_weeks_and_never_zero(key, identity):
    weeks = dates.date_offset_weeks(key, identity)

    assert 52 <= weeks <= 520
    assert weeks == dates.date_offset_weeks(keys.DeidKey(key.secret), identity)


def test_offsets_spread_across_the_range():
    offsets = [
        dates.date_offset_weeks(
            FIXTURE_KEY, pseudonyms.SubjectIdentity.from_patient_id(f"{number:06d}")
        )
        for number in range(10_000)
    ]

    assert min(offsets) == 52
    assert max(offsets) == 520
    assert len(set(offsets)) == 469


def test_a_date_moves_back_by_whole_weeks():
    assert dates.shift_date("20260927", 52) == "20250928"
    # Across 29 February 2024.
    assert dates.shift_date("20250301", 52) == "20240302"


@hypothesis.given(any_date, any_date, any_weeks)
def test_shifting_preserves_intervals_and_weekdays(first, second, weeks):
    def shifted(day):
        return datetime.datetime.strptime(
            dates.shift_date(_da(day), weeks), "%Y%m%d"
        ).date()

    assert shifted(second) - shifted(first) == second - first
    assert shifted(first).weekday() == first.weekday()
    assert shifted(first) < first


@pytest.mark.parametrize(
    "value",
    [
        "",
        "2026",
        "202609",
        "2026-09-27",
        "2026.09.27",
        "20260230",
        "20261327",
        "2026092",
        "x0260927",
    ],
)
def test_an_invalid_date_is_not_shifted(value):
    with pytest.raises(ValueError, match="not a DA value"):
        dates.shift_date(value, 52)


@pytest.mark.parametrize(
    "value, expected", [("10000101", "09990102"), ("00020108", "00010109")]
)
def test_an_early_date_keeps_four_year_digits(value, expected):
    assert dates.shift_date(value, 52) == expected
    assert dates.shift_datetime(value + "1200+0000", 52) == expected + "1200+0000"


def test_trailing_padding_is_ignored():
    assert dates.shift_date("20260927 ", 52) == "20250928"


def test_a_shift_before_year_1_is_rejected():
    with pytest.raises(ValueError, match="before"):
        dates.shift_date("00010105", 52)


@pytest.mark.parametrize(
    "value, expected",
    [
        ("20260927", "20250928"),
        ("2026092714", "2025092814"),
        ("202609271430", "202509281430"),
        ("20260927143015", "20250928143015"),
        ("20260927143015.123456", "20250928143015.123456"),
        ("20260927143015.123456+1000", "20250928143015.123456+1000"),
        ("20260927-0500", "20250928-0500"),
        ("20260927-1200", "20250928-1200"),
        ("20260927+1400", "20250928+1400"),
        ("20260927+0000", "20250928+0000"),
        ("20260927+0545", "20250928+0545"),
    ],
)
def test_a_datetime_moves_its_date_and_keeps_its_time_and_utc_offset(value, expected):
    assert dates.shift_datetime(value, 52) == expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        "2026",
        "202609",
        "2026+1000",
        "20260927 1430",
        "2026092724",
        "202609271460",
        "20260927143061",
        "20260927143015.",
        "20260927143015.1234567",
        "20260927+10",
        "20260927+1401",
        "20260927+1459",
        "20260927-1201",
        "20260927-1259",
        "20260927-0000",
        "20260230",
    ],
)
def test_a_partial_or_invalid_datetime_is_not_shifted(value):
    with pytest.raises(ValueError, match="not a DT value with a full date"):
        dates.shift_datetime(value, 52)


@pytest.mark.parametrize("weeks", [0, 51, 521, -52])
def test_an_offset_outside_the_range_is_rejected(weeks):
    with pytest.raises(ValueError, match="52 to 520"):
        dates.shift_date("20260927", weeks)


def _instant(value, local):
    """Return the instant a DT value denotes, at its own offset or ``local``."""
    match = re.fullmatch(r"([0-9]{12})([0-9.]*)([+-][0-9]{4})?", value)
    offset = match[3] or local
    minutes = int(offset[1:3]) * 60 + int(offset[3:])
    zone = datetime.timezone(
        datetime.timedelta(minutes=-minutes if offset[0] == "-" else minutes)
    )
    return datetime.datetime.strptime(match[1], "%Y%m%d%H%M").replace(tzinfo=zone)


def test_the_local_offset_is_the_instances_timezone_offset():
    # PS3.3 C.12.1.1.8: it governs every date and time without its own offset.
    assert dates.local_offset("+1000 ", ["20260927013000+0000"]) == "+1000"


def test_without_a_timezone_offset_the_earliest_own_offset_is_local():
    values = ["20260927120000+1000", "20260927013000+0000", "20260927090000"]

    assert dates.local_offset(None, values) == "+0000"


def test_without_any_offset_there_is_no_local_offset():
    assert dates.local_offset(None, ["20260927120000", "20260927"]) is None


@pytest.mark.parametrize(
    "values",
    [
        # The first value is 58 seconds earlier, in the same UTC minute.
        ["20260927120001+1000", "20260927020059+0000"],
        # The first value is 0.8 seconds earlier, in the same UTC second.
        ["20260927120000.1+1000", "20260927020000.9+0000"],
    ],
)
def test_the_earliest_value_is_found_to_the_fraction_of_a_second(values):
    assert dates.local_offset(None, values) == "+1000"
    assert dates.local_offset(None, values[::-1]) == "+1000"


def test_values_at_the_same_instant_are_ordered_by_offset():
    # Different fraction precision, same instant: the choice is deterministic.
    values = ["20260927120000.5+1000", "20260927020000.50+0000"]

    assert dates.local_offset(None, values) == "+0000"
    assert dates.local_offset(None, values[::-1]) == "+0000"


@pytest.mark.parametrize(
    "value, expected",
    [("00010101000000+1400", "+1400"), ("99991231230000-1200", "-1200")],
)
def test_the_earliest_value_is_found_at_the_ends_of_the_calendar(value, expected):
    assert dates.local_offset(None, [value]) == expected


@pytest.mark.parametrize("value", ["20260230010100", "20260931", "20260230010100 "])
def test_a_datetime_without_an_offset_must_have_a_real_date(value):
    with pytest.raises(ValueError, match="not a DT value"):
        dates.local_offset(None, [value])
    with pytest.raises(ValueError, match="not a DT value"):
        dates.to_local_datetime(value, "+1000")


@pytest.mark.parametrize("offset", ["+1500", "-1201", "-0000", "1000", "+10"])
def test_a_local_offset_outside_the_range_is_rejected(offset):
    with pytest.raises(ValueError, match="-1200 to \\+1400"):
        dates.local_offset(offset, [])


@pytest.mark.parametrize(
    "value, offset, expected",
    [
        # Already local: returned without padding.
        ("20260927120000 ", "+1000", "20260927120000"),
        ("20260927113000+1000", "+1000", "20260927113000+0000"),
        ("20260927013000+0000", "+1000", "20260927113000+0000"),
        # Across midnight, forwards and backwards.
        ("20260926233000.5-0200", "+1000", "20260927113000.5+0000"),
        ("20260927003000+1400", "-1000", "20260926003000+0000"),
        # Precision is kept.
        ("2026092714+0500", "+1000", "2026092719+0000"),
        ("202609271430+0530", "+1000", "202609271900+0000"),
        ("20260927+1000", "+1000", "20260927+0000"),
    ],
)
def test_a_datetime_converts_to_local_time(value, offset, expected):
    assert dates.to_local_datetime(value, offset) == expected


@pytest.mark.parametrize(
    "value",
    [
        # The leap second at the end of 2016, in UTC and at +1000.
        "20161231235960+0000",
        "20161231235960.5+0000",
        "20170101095960+1000",
        # Local time with no offset of its own.
        "20161231235960",
    ],
)
def test_a_leap_second_is_not_supported(value):
    # PS3.5 allows a second of 60 only at a real leap second, which a shifted
    # or converted value would no longer be.
    with pytest.raises(ValueError, match="leap seconds are not supported"):
        dates.shift_datetime(value, 52)
    with pytest.raises(ValueError, match="leap seconds are not supported"):
        dates.to_local_datetime(value, "+1000")
    with pytest.raises(ValueError, match="leap seconds are not supported"):
        dates.local_offset(None, [value])


@pytest.mark.parametrize(
    "value, offset, message",
    [
        ("20260927+1000", "+1100", "precision"),
        ("2026092714+0530", "+1000", "precision"),
        ("20260927120000+1000", "+1500", "local offset"),
        ("20260927120000+1401", "+1000", "not a DT value"),
        ("2026+1000", "+1000", "not a DT value"),
        ("00010101000000+0100", "-1200", "outside years 1 to 9999"),
        ("99991231230000-1200", "+1400", "outside years 1 to 9999"),
    ],
)
def test_a_datetime_that_cannot_convert_exactly_is_rejected(value, offset, message):
    with pytest.raises(ValueError, match=message):
        dates.to_local_datetime(value, offset)


def test_local_times_keep_their_interval_to_values_with_their_own_offset():
    # An instance at +1000: a local time 30 minutes after a value with its own
    # offset, and one 30 minutes before a value recorded in UTC.
    local = dates.local_offset("+1000", [])
    pairs = [
        ("20260927120000", "20260927113000+1000", 30),
        ("20260927010000", "20260926153000+0000", -30),
    ]
    for implicit, explicit, minutes in pairs:
        before = _instant(implicit, local) - _instant(explicit, local)
        shifted = [
            dates.shift_datetime(dates.to_local_datetime(v, local), 52)
            for v in (implicit, explicit)
        ]
        after = _instant(shifted[0], dates.NOMINAL_UTC_OFFSET) - _instant(
            shifted[1], dates.NOMINAL_UTC_OFFSET
        )

        assert before == after == datetime.timedelta(minutes=minutes)


any_offset = (
    st.integers(min_value=-12 * 60, max_value=14 * 60)
    .map(lambda m: f"{'-' if m < 0 else '+'}{abs(m) // 60:02d}{abs(m) % 60:02d}")
    .filter(lambda o: o != "-0000")
)
any_minute = st.datetimes(
    min_value=datetime.datetime(1900, 1, 1), max_value=datetime.datetime(9990, 1, 1)
).map(lambda d: d.replace(second=0, microsecond=0))


@hypothesis.given(st.lists(st.tuples(any_minute, any_offset), min_size=2, max_size=5))
def test_converting_to_local_time_keeps_every_interval(values):
    texts = [f"{d:%Y%m%d%H%M}{o}" for d, o in values]
    local = dates.local_offset(None, texts)
    converted = [dates.to_local_datetime(text, local) for text in texts]

    originals = [_instant(text, local) for text in texts]
    locals_ = [_instant(text, dates.NOMINAL_UTC_OFFSET) for text in converted]
    assert all(value.endswith(dates.NOMINAL_UTC_OFFSET) for value in converted)
    assert [b - a for a, b in zip(originals, originals[1:])] == [
        b - a for a, b in zip(locals_, locals_[1:])
    ]


any_moment = st.datetimes(
    min_value=datetime.datetime(1900, 1, 1), max_value=datetime.datetime(9990, 1, 1)
)


@hypothesis.given(
    st.lists(st.tuples(any_moment, any_offset), min_size=1, max_size=5).filter(
        lambda values: len({_utc(*value) for value in values}) == len(values)
    )
)
def test_the_local_offset_is_that_of_the_earliest_instant(values):
    # Seconds and microseconds included, compared with the standard library.
    texts = [f"{d:%Y%m%d%H%M%S.%f}{o}" for d, o in values]
    earliest = min(values, key=lambda value: _utc(*value))

    assert dates.local_offset(None, texts) == earliest[1]


@hypothesis.given(
    any_minute,
    st.lists(
        st.tuples(
            st.integers(min_value=0, max_value=59),
            st.integers(min_value=0, max_value=999_999),
            any_offset,
        ),
        min_size=2,
        max_size=5,
        unique_by=lambda value: value[:2],
    ),
)
def test_within_one_utc_minute_seconds_and_fractions_decide(minute, parts):
    # Every value is in the same UTC minute, recorded at its own offset.
    texts = []
    for second, microsecond, offset in parts:
        moment = minute + datetime.timedelta(seconds=second, microseconds=microsecond)
        texts.append(
            f"{moment - _utc(minute, offset) + minute:%Y%m%d%H%M%S.%f}{offset}"
        )
    earliest = min(parts, key=lambda value: value[:2])

    assert dates.local_offset(None, texts) == earliest[2]


def _utc(moment, offset):
    minutes = int(offset[1:3]) * 60 + int(offset[3:])
    return moment - datetime.timedelta(
        minutes=-minutes if offset[0] == "-" else minutes
    )


def _ptp(seconds, nanoseconds=0):
    return seconds.to_bytes(6, "big") + nanoseconds.to_bytes(4, "big")


def test_a_frame_origin_timestamp_moves_back_by_whole_weeks():
    shifted = dates.shift_frame_origin_timestamp(_ptp(1_790_000_000, 123), 52)

    assert shifted == _ptp(1_790_000_000 - 52 * 7 * 24 * 60 * 60, 123)


@hypothesis.given(
    st.lists(
        st.tuples(
            st.integers(min_value=10**9, max_value=2**48 - 1),
            st.integers(min_value=0, max_value=10**9 - 1),
        ),
        min_size=2,
        max_size=5,
    ),
    any_weeks,
)
def test_frame_origin_timestamps_keep_their_intervals(timestamps, weeks):
    def nanoseconds(value):
        return int.from_bytes(value[:6], "big") * 10**9 + int.from_bytes(
            value[6:], "big"
        )

    originals = [_ptp(s, n) for s, n in timestamps]
    shifted = [dates.shift_frame_origin_timestamp(v, weeks) for v in originals]

    assert [nanoseconds(b) - nanoseconds(a) for a, b in zip(shifted, shifted[1:])] == [
        nanoseconds(b) - nanoseconds(a) for a, b in zip(originals, originals[1:])
    ]


@pytest.mark.parametrize(
    "value, message",
    [
        (bytes(9), "IEEE 1588"),
        (bytes(11), "IEEE 1588"),
        (_ptp(10**9, 10**9), "IEEE 1588"),
        (_ptp(1000), "before 1970"),
    ],
)
def test_an_invalid_frame_origin_timestamp_is_rejected(value, message):
    with pytest.raises(ValueError, match=message):
        dates.shift_frame_origin_timestamp(value, 52)
