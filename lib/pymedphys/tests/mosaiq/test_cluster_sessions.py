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

"""Session clustering of treatment times, without a Mosaiq database."""

from datetime import datetime, timedelta

from pymedphys._imports import pytest

from pymedphys._mosaiq.sessions import cluster_sessions

pytest.importorskip("sklearn")

START = datetime(2024, 1, 1, 8, 0)


def test_times_closer_than_the_interval_share_a_session():
    times = [START + timedelta(minutes=m) for m in (0, 10, 20, 300, 310)]

    assert list(cluster_sessions(times)) == [
        (1, times[0], times[2]),
        (2, times[3], times[4]),
    ]


def test_an_interval_of_a_day_or_more_is_not_truncated():
    # timedelta.seconds is 0 for a two-day interval, which put every
    # treatment in a session of its own.
    times = [START, START + timedelta(hours=30), START + timedelta(days=5)]

    assert list(cluster_sessions(times, interval=timedelta(days=2))) == [
        (1, times[0], times[1]),
        (2, times[2], times[2]),
    ]


def test_a_single_treatment_is_one_session():
    assert list(cluster_sessions([START])) == [(1, START, START)]


def test_no_treatments_give_no_sessions():
    assert not list(cluster_sessions([]))
