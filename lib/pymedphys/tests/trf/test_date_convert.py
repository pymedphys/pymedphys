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


import pymedphys
from pymedphys._trf.manage import identify


def test_date_convert_parity():
    """Verify that using pandas instead of dateutil achieves the same end"""
    path = pymedphys.data_path("negative-metersetmap.trf")
    header, _ = pymedphys.trf.read(path)

    utc_date = header["date"][0]
    timezone = "Australia/Sydney"

    dateutil_version = (
        identify._date_convert_using_dateutil(  # pylint: disable = protected-access
            utc_date, timezone
        )
    )
    pandas_version = identify.date_convert(utc_date, timezone)

    assert dateutil_version == pandas_version
