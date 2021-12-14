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


def determine_header_length(trf_contents: bytes) -> int:
    """Returns the header length of a TRF file

    Determined through brute force reverse engineering only. Not based
    upon official documentation.

    Parameters
    ----------
    trf_contents : bytes

    Returns
    -------
    header_length : int
        The length of the TRF header, prior to the table portion of the
        TRF file.
    """

    column_end = b"\t\xdc\x00\xe8\t\xdc\x00\xe9\t\xdc\x00\xea\t\xdc\x00\xeb\t\xdc\x00"
    header_length = trf_contents.index(column_end) + len(column_end)

    # test = trf_contents.split(b"\t")
    # row_skips = 6
    # i = next(i for i, item in enumerate(test[row_skips::]) if len(item) > 3) + row_skips
    # header_length_old_method = len(b"\t".join(test[0:i])) + 3

    # if header_length_old_method != header_length:
    #     raise ValueError("Inconsistent header length determination")

    return header_length


def _header_match(contents):
    match = re.match(
        br"[\x00-\x19]"  # start bit
        br"(\d\d[/-]\d\d[/-]\d\d \d\d:\d\d:\d\d Z)"  # date
        br"[\x00-\x19]"  # divider bit
        br"((\+|\-)\d\d:\d\d)"  # time zone
        br"[\x00-\x25]"  # divider bit
        br"([\x20-\x7F]*)"  # field label and name
        br"[\x00-\x19]"  # divider bit
        br"([\x20-\x7F]+)"  # machine name
        br"[\x00-\x19]",  # divider bit
        contents,
    )

    if match is None:
        print(contents)
        raise ValueError("TRF header not in an expected form.")

    return match


def decode_header(trf_header_contents: bytes) -> Header:
    """Decodes the header of a TRF file

    Parameters
    ----------
    trf_header_contents : bytes
        The header portion only of a TRF file. Use
        `determine_header_length` to extract the header portion only.

    Returns
    -------
    machine : str
        Machine ID. If it is set up to be serial number based something
        like '2619' could be expected.
    date : str
        UTC date. Eg '20/09/24 06:29:58 Z'.
    timezone : str
        Eg '+02:00'.
    field_label : str
        The first item that identifies the delivered field. Eg '1-1'.
        This item will be blank for service mode created beams.
    field_name : str
        The second item that identifies the delivered field. Eg 'AP G0'.
    """

    match = _header_match(trf_header_contents)

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


def _raw_header_from_file(filepath):
    with open(filepath, "rb") as file:
        trf_contents = file.read()

    header_length = determine_header_length(trf_contents)
    trf_header_contents = trf_contents[0:header_length]

    return trf_header_contents


def decode_header_from_file(filepath):
    trf_header_contents = _raw_header_from_file(filepath)

    return decode_header(trf_header_contents)
