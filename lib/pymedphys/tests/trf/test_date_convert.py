# Copyright (C) 2026 Matthew Jennings
# Copyright (C) 2020 Simon Biggs

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


from pymedphys._imports import pytest

import pymedphys
from pymedphys._trf.manage import identify


def test_date_convert_parity():
    """Verify that using pandas instead of dateutil achieves the same end"""
    path = pymedphys.data_path("negative-metersetmap.trf")
    header, _ = pymedphys.trf.read(path)

    utc_date = header["date"][0]
    timezone = "Australia/Sydney"

    dateutil_version = identify._date_convert_using_dateutil(  # pylint: disable = protected-access
        utc_date, timezone
    )
    pandas_version = identify.date_convert(utc_date, timezone)

    assert dateutil_version == pandas_version


# Sydney daylight saving time ended at 03:00 AEDT (16:00 UTC) on 6 April 2025
# and started at 02:00 AEST (16:00 UTC) on 5 October 2025.
@pytest.mark.parametrize(
    ("utc_date", "expected"),
    [
        ("25/04/05 15:59:59 Z", ("2025-04-06 02:59:59", "2025-04-06_025959")),
        ("25/04/05 16:00:00 Z", ("2025-04-06 02:00:00", "2025-04-06_020000")),
        ("25/10/04 15:59:59 Z", ("2025-10-05 01:59:59", "2025-10-05_015959")),
        ("25/10/04 16:00:00 Z", ("2025-10-05 03:00:00", "2025-10-05_030000")),
        ("24/12/31 13:00:00 Z", ("2025-01-01 00:00:00", "2025-01-01_000000")),
    ],
)
def test_date_convert_across_daylight_saving_transitions(utc_date, expected):
    """A logfile's UTC date converts to local time either side of each
    daylight saving transition, as the dateutil conversion does."""
    timezone = "Australia/Sydney"

    assert identify.date_convert(utc_date, timezone) == expected
    assert (
        identify._date_convert_using_dateutil(  # pylint: disable = protected-access
            utc_date, timezone
        )
        == expected
    )
