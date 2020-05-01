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
