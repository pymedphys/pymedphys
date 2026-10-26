# Copyright (C) 2026 Derek Lane

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Session clustering tests that need no Mosaiq database."""

from datetime import datetime, timedelta

from pymedphys._imports import numpy as np
from pymedphys._imports import pytest

from pymedphys._mosaiq import sessions
from pymedphys._mosaiq.sessions import (
    DEFAULT_SESSION_INTERVAL,
    cluster_sessions,
    mean_session_offset_for_site,
    session_interval_for_site,
    session_offsets_for_site,
    sessions_for_site,
)

DAY = datetime(2021, 3, 1)


def at(hours=0.0, days=0):
    return DAY + timedelta(days=days, hours=hours)


def mosaiq_oracle(tx_datetimes, interval, split_on_date=True):
    """Session numbers per treatment, written directly from Mosaiq's rule"""
    numbers = []
    first = None
    for tx in tx_datetimes:
        if (
            first is None
            or (tx - first).total_seconds() > interval.total_seconds()
            or (split_on_date and tx.date() != first.date())
        ):
            first = tx
            numbers.append(numbers[-1] + 1 if numbers else 1)
        else:
            numbers.append(numbers[-1])
    return numbers


def test_default_interval_is_mosaiq_default():
    # Config.Tx_Interval_Time defaults to 1,080,000 hundredths of a second
    assert DEFAULT_SESSION_INTERVAL == timedelta(seconds=1_080_000 / 100)


def test_empty_and_single_treatment():
    assert not list(cluster_sessions([]))
    assert list(cluster_sessions([at(10)])) == [(1, at(10), at(10))]


def test_session_measured_from_first_treatment():
    hourly = [at(h) for h in range(6)]
    assert list(cluster_sessions(hourly, timedelta(hours=3))) == [
        (1, at(0), at(3)),
        (2, at(4), at(5)),
    ]


def test_interval_is_inclusive():
    assert list(cluster_sessions([at(8), at(11)], timedelta(hours=3))) == [
        (1, at(8), at(11))
    ]
    just_over = at(11) + timedelta(microseconds=1)
    assert len(list(cluster_sessions([at(8), just_over], timedelta(hours=3)))) == 2


def test_fractional_seconds_in_interval():
    tx = [at(0), at(0) + timedelta(seconds=1.5)]
    assert len(list(cluster_sessions(tx, timedelta(seconds=1.5)))) == 1
    assert len(list(cluster_sessions(tx, timedelta(seconds=1.4)))) == 2


def test_sessions_split_at_midnight():
    tx = [at(23), at(23.5), at(24.5)]
    assert list(cluster_sessions(tx, timedelta(hours=3))) == [
        (1, at(23), at(23.5)),
        (2, at(24.5), at(24.5)),
    ]
    assert len(list(cluster_sessions(tx, timedelta(hours=3), False))) == 1


def test_multi_day_interval_keeps_whole_days():
    tx = [at(10, days=d) for d in range(3)]
    assert len(list(cluster_sessions(tx, timedelta(days=2), False))) == 1
    assert len(list(cluster_sessions(tx, timedelta(days=1), False))) == 2


def test_matches_mosaiq_rule_on_random_times():
    rng = np.random.default_rng(2141)
    for _ in range(200):
        offsets = sorted(rng.uniform(0, 72 * 3600, rng.integers(0, 30)))
        tx = [DAY + timedelta(seconds=float(s)) for s in offsets]
        interval = timedelta(seconds=float(rng.uniform(60, 6 * 3600)))
        split = bool(rng.integers(2))

        expected = mosaiq_oracle(tx, interval, split)
        clustered = list(cluster_sessions(tx, interval, split))
        numbers = [
            number for number, start, end in clustered for t in tx if start <= t <= end
        ]
        assert numbers == expected


class FakeConnection:
    """Answers the queries in sessions.py from in-memory rows"""

    def __init__(self, tx_datetimes, intervals=(), offsets=()):
        self.tx_datetimes = tx_datetimes
        self.intervals = intervals
        # (Study_DtTm, Superior_Offset, Anterior_Offset, Lateral_Offset)
        self.offsets = offsets


def fake_execute(connection, query, parameters=None):  # pylint: disable = unused-argument
    if "Config.Tx_Interval_Time" in query:
        return [(value,) for value in connection.intervals]
    if "FROM Dose_Hst" in query:
        assert "WasQAMode = 0" in query
        return [(tx,) for tx in connection.tx_datetimes]
    if "FROM Offset" in query:
        # SQL Server converts string parameters to datetimes for the comparison
        start, end = (
            datetime.fromisoformat(value) if isinstance(value, str) else value
            for value in (parameters["window_start"], parameters["window_end"])
        )
        return sorted(row for row in connection.offsets if start < row[0] < end)
    raise AssertionError(f"unexpected query: {query}")


@pytest.fixture(autouse=True)
def patch_execute(monkeypatch):
    monkeypatch.setattr(sessions.api, "execute", fake_execute)


def test_department_interval_from_config():
    # 30 minutes, in hundredths of a second
    connection = FakeConnection([], [180_000])
    assert session_interval_for_site(connection, 1) == timedelta(minutes=30)


def test_department_interval_defaults_without_config():
    assert session_interval_for_site(FakeConnection([]), 1) == timedelta(hours=3)


def test_conflicting_department_intervals_raise():
    with pytest.raises(ValueError, match="different treatment session intervals"):
        session_interval_for_site(FakeConnection([], [180_000, 1_080_000]), 1)


def test_sessions_for_site_uses_department_interval():
    tx = [at(10), at(10.75), at(11.5)]
    connection = FakeConnection(tx, [360_000])  # 1 hour
    assert len(list(sessions_for_site(connection, 1))) == 2
    assert len(list(sessions_for_site(connection, 1, timedelta(hours=3)))) == 1


def test_empty_site_has_no_sessions_or_mean_offset():
    connection = FakeConnection([])
    assert not list(sessions_for_site(connection, 1))
    assert mean_session_offset_for_site(connection, 1) is None


def offsets_by_session(connection):
    return [
        (number, None if offset is None else offset.tolist())
        for number, offset in session_offsets_for_site(connection, 1)
    ]


def test_session_offset_not_taken_from_previous_session():
    # 11:00:40 is more than 3 hours after 08:00, so it starts session 2,
    #   whose 1 hour look-back reaches the 10:25 re-image for session 1
    tx = [at(8), at(10.5), at(11) + timedelta(seconds=40)]
    offsets = [
        (at(8) - timedelta(minutes=5), 1.0, 0.0, 0.0),
        (at(10.5) - timedelta(minutes=5), 2.0, 0.0, 0.0),
        (at(11) + timedelta(seconds=20), 3.0, 0.0, 0.0),
    ]
    connection = FakeConnection(tx, offsets=offsets)
    assert offsets_by_session(connection) == [
        (1, [1.0, 0.0, 0.0]),
        (2, [3.0, 0.0, 0.0]),
    ]


def test_session_offsets_split_within_the_same_minute():
    # with a 30 minute interval, 08:30:00 ends session 1 and 08:30:50
    #   starts session 2, which was imaged at 08:30:20
    tx = [at(8), at(8.5), at(8.5) + timedelta(seconds=50)]
    offsets = [
        (at(8) - timedelta(minutes=2), 1.0, 0.0, 0.0),
        (at(8.5) + timedelta(seconds=20), 2.0, 0.0, 0.0),
    ]
    connection = FakeConnection(tx, [180_000], offsets)
    assert offsets_by_session(connection) == [
        (1, [1.0, 0.0, 0.0]),
        (2, [2.0, 0.0, 0.0]),
    ]
