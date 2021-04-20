# Copyright (C) 2018 Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import pathlib
from datetime import datetime

from pymedphys._imports import dateutil
from pymedphys._imports import pandas as pd

from pymedphys._mosaiq import api as _msq_api
from pymedphys._mosaiq import delivery as _delivery
from pymedphys._trf.decode import header as _header

# TODO Make the field identification run one whole day at a time, searching
# for all logfiles on that day and then attempting to align the logfiles
# to the full day's machine schedule.
# This will allow for the code to be more flexible on time differences and
# result in greater robustness to time differences between TCS and Mosaiq.


def _date_convert_using_dateutil(date, timezone):
    """Converts logfile UTC date to the provided timezone.
    The date is formatted to match the syntax required by Microsoft SQL.

    This is the function that was originally used, but it has an
    incompatibility with Streamlit. This will be removed along with the
    dateutil dependency in the near future.

    """

    from_timezone = dateutil.tz.gettz("UTC")
    to_timezone = dateutil.tz.gettz(timezone)

    utc_datetime = datetime.strptime(date, "%y/%m/%d %H:%M:%S Z").replace(
        tzinfo=from_timezone
    )
    local_time = utc_datetime.astimezone(to_timezone)
    mosaiq_string_time = local_time.strftime("%Y-%m-%d %H:%M:%S")
    path_string_time = local_time.strftime("%Y-%m-%d_%H%M%S")

    return mosaiq_string_time, path_string_time


def date_convert(date, timezone):
    """Converts logfile UTC date to the provided timezone.
    The date is formatted to match the syntax required by Microsoft SQL."""

    utc_datetime = pd.DatetimeIndex(
        [datetime.strptime(date, "%y/%m/%d %H:%M:%S Z")], tz="UTC"
    )
    local_time = utc_datetime.tz_convert(timezone)[0]  # pylint: disable = no-member

    mosaiq_string_time = local_time.strftime("%Y-%m-%d %H:%M:%S")
    path_string_time = local_time.strftime("%Y-%m-%d_%H%M%S")

    return mosaiq_string_time, path_string_time


def identify_logfile(
    connection: _msq_api.Connection, filepath: pathlib.Path, timezone: str
):
    """Query a Mosaiq database to associate a TRF with its corresponding
    delivery and therefore its patient information.

    Parameters
    ----------
    connection : pymedphys.mosaiq.Connection
        A connection instance to the Mosaiq MSSQL database. Only
        requirement is that it is a `PEP-0249 <https://www.python.org/dev/peps/pep-0249/#connection-objects>`_
        compliant ``connection`` object.
    filepath : pathlib.Path
        Path to the TRF
    timezone : str
        The timezone that matches the Mosaiq MSSQL instance being queried.
        This is utilised internally to convert the TRF's UTC timestamp
        to a timestamp that matches the time of delivery in Mosaiq.
        The conversion happens utilising
        `tz_convert <https://pandas.pydata.org/docs/reference/api/pandas.DatetimeIndex.tz_convert.html#pandas.DatetimeIndex.tz_convert>`_
        within the Pandas library. So anything that its `tz` parameter
        accepts can be provided here.

    Returns
    -------
    OISDeliveryDetails
        An ``attrs`` class that has the following attributes:

        - ``patient_id``
        - ``field_id``
        - ``last_name``
        - ``first_name``
        - ``qa_mode``
        - ``field_type``
        - ``beam_completed``
    """
    header = _header.decode_header_from_file(filepath)

    if header.field_label == "":
        raise ValueError("No field label in logfile")

    mosaiq_string_time, _ = date_convert(header.date, timezone)

    delivery_details = _delivery.get_mosaiq_delivery_details(
        connection,
        header.machine,
        mosaiq_string_time,
        header.field_label,
        header.field_name,
    )

    return delivery_details
