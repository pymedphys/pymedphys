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


from datetime import datetime

from pymedphys._imports import dateutil

from pymedphys._mosaiq.delivery import get_mosaiq_delivery_details
from pymedphys._trf.header import decode_header_from_file

# TODO Make the field identification run one whole day at a time, searching
# for all logfiles on that day and then attempting to align the logfiles
# to the full day's machine schedule.
# This will allow for the code to be more flexible on time differences and
# result in greater robustness to time differences between TCS and Mosaiq.


def date_convert(date, timezone):
    """Converts logfile UTC date to the provided timezone.
    The date is formatted to match the syntax required by Microsoft SQL."""

    from_timezone = dateutil.tz.gettz("UTC")
    to_timezone = dateutil.tz.gettz(timezone)

    utc_datetime = datetime.strptime(date, "%y/%m/%d %H:%M:%S Z").replace(
        tzinfo=from_timezone
    )
    local_time = utc_datetime.astimezone(to_timezone)
    mosaiq_string_time = local_time.strftime("%Y-%m-%d %H:%M:%S")
    path_string_time = local_time.strftime("%Y-%m-%d_%H%M%S")

    return mosaiq_string_time, path_string_time


def identify_logfile(cursor, filepath, timezone):
    header = decode_header_from_file(filepath)

    if header.field_label == "":
        raise Exception("No field label in logfile")

    mosaiq_string_time, _ = date_convert(header.date, timezone)

    delivery_details = get_mosaiq_delivery_details(
        cursor,
        header.machine,
        mosaiq_string_time,
        header.field_label,
        header.field_name,
    )

    return delivery_details
