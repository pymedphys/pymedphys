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
    .filter(str.strip)
    .map(pseudonyms.SubjectIdentity.from_patient_id)
)
any_weeks = st.integers(
    min_value=dates.MIN_OFFSET_WEEKS, max_value=dates.MAX_OFFSET_WEEKS
)
# Dates far enough from year 1 to shift by up to ten years.
any_date = st.dates(
    min_value=datetime.date(1900, 1, 1), max_value=datetime.date(9999, 12, 31)
)


def _frame(value):
    return len(value).to_bytes(4, "big") + value


def test_an_offset_follows_d_006():
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
            dates.shift_date(day.strftime("%Y%m%d"), weeks), "%Y%m%d"
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
        "20260927143015.",
        "20260927143015.1234567",
        "20260927+10",
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
