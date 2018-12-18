# Copyright (C) 2018 Cancer Care Associates

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version (the "AGPL-3.0+").

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License and the additional terms for more
# details.

# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

# ADDITIONAL TERMS are also included as allowed by Section 7 of the GNU
# Affero General Public License. These additional terms are Sections 1, 5,
# 6, 7, 8, and 9 from the Apache License, Version 2.0 (the "Apache-2.0")
# where all references to the definition "License" are instead defined to
# mean the AGPL-3.0+.

# You should have received a copy of the Apache-2.0 along with this
# program. If not, see <http://www.apache.org/licenses/LICENSE-2.0>.


# pylint: skip-file

from datetime import datetime
from dateutil import tz

from .._level2.msqdelivery import (
    get_mosaiq_delivery_details, OISDeliveryDetails)

from .._level2.trfdecode import decode_header_from_file


from .._level0.libutils import get_imports
IMPORTS = get_imports(globals())


# TODO Make the field identification run one whole day at a time, searching
# for all logfiles on that day and then attempting to align the logfiles
# to the full day's machine schedule.
# This will allow for the code to be more flexible on time differences and
# result in greater robustness to time differences between TCS and Mosaiq.


def date_convert(date, timezone):
    """Converts logfile UTC date to the provided timezone.
    The date is formatted to match the syntax required by Microsoft SQL."""

    from_timezone = tz.gettz('UTC')
    to_timezone = tz.gettz(timezone)

    utc_datetime = datetime.strptime(
        date, '%y/%m/%d %H:%M:%S Z').replace(tzinfo=from_timezone)
    local_time = utc_datetime.astimezone(to_timezone)
    mosaiq_string_time = local_time.strftime('%Y-%m-%d %H:%M:%S')
    path_string_time = local_time.strftime('%Y-%m-%d_%H%M%S')

    return mosaiq_string_time, path_string_time


def identify_logfile(cursor, filepath, timezone) -> OISDeliveryDetails:
    header = decode_header_from_file(filepath)

    if header.field_label == "":
        raise Exception("No field label in logfile")

    mosaiq_string_time, _ = date_convert(header.date, timezone)

    delivery_details = get_mosaiq_delivery_details(
        cursor, header.machine, mosaiq_string_time,
        header.field_label, header.field_name)

    return delivery_details
