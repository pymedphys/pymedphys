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


import re
from collections import namedtuple

Header = namedtuple(
    "Header", ["machine", "date", "timezone", "field_label", "field_name"]
)


def determine_header_length(trf_contents):
    test = trf_contents.split(b"\t")
    row_skips = 6
    i = next(i for i, item in enumerate(test[row_skips::]) if len(item) > 3) + row_skips
    header_length = len(b"\t".join(test[0:i])) + 3

    return header_length


def decode_header(trf_header_contents):
    match = re.match(
        br"[\x00-\x19]"  # start bit
        br"(\d\d/\d\d/\d\d \d\d:\d\d:\d\d Z)"  # date
        br"[\x00-\x19]"  # divider bit
        br"((\+|\-)\d\d:\d\d)"  # time zone
        br"[\x00-\x25]"  # divider bit
        br"([\x20-\xFF]*)"  # field label and name
        br"[\x00-\x19]"  # divider bit
        br"([\x20-\xFF]+)"  # machine name
        br"[\x00-\x19]",  # divider bit
        trf_header_contents,
    )

    if match is None:
        print(trf_header_contents)
        raise ValueError("Logfile header not of an expected form.")

    groups = match.groups()
    date = groups[0].decode("ascii")
    timezone = groups[1].decode("ascii")
    field = groups[3].decode("ascii")
    machine = groups[4].decode("ascii")

    split_field = field.split("/")
    if len(split_field) == 2:
        field_label, field_name = split_field
    else:
        field_label, field_name = "", field

    header = Header(machine, date, timezone, field_label, field_name)

    return header


def convert_header_section_to_string(section):
    return "".join([chr(item) for item in section[1::]])


def raw_header_from_file(filepath):
    with open(filepath, "rb") as file:
        trf_contents = file.read()

    header_length = determine_header_length(trf_contents)
    trf_header_contents = trf_contents[0:header_length]

    return trf_header_contents


def decode_header_from_file(filepath):
    trf_header_contents = raw_header_from_file(filepath)

    return decode_header(trf_header_contents)
