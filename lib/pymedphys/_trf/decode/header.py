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

from pymedphys._imports import numpy as np

Header = namedtuple(
    "Header",
    [
        "machine",
        "date",
        "timezone",
        "field_label",
        "field_name",
        "mu",
        "version",
        "item_parts_number",
        "item_parts_length",
        "item_parts",
    ],
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

    # Date regex match (any 25 characters \x00-\x19) with pattern (\d\d/\d\d/\d\d \d\d:\d\d:\d\d Z)
    # UTC offset regex (any 25 characters \x00-\x19) with pattern ([\+|\-]\d\d:\d\d)
    # Treatment name regex match (any 50 characters \x00-\x32) with pattern ([\x20-\x7F]*) according to ASCII table encoding
    # Machine number (any 10 characters \x00-\x10) with pattern ([\x20-\x7F]*) according to ASCII table encoding
    # Treatment Record related header

    regex_trf = (
        rb"[\x00-\x19]"  # start bit
        + rb"(\d\d[/|-]\d\d[/|-]\d\d \d\d:\d\d:\d\d Z)"  # date
        + rb"[\x00-\x19]"  # divider bit
        + rb"([\+|\-]\d\d:\d\d)"  # time zone
        + rb"[\x00-\x32]"  # divider bit
        + rb"([\x20-\x7F]*)"  # field label and name
        + rb"[\x00-\x10]"  # divider bit
        + rb"([\x20-\x7F]*)"  # machine name
        + rb"([\x00-\xFFF]*)"  # divider bit
    )

    # The first 4 groups in the regex match are dynamically allocated as
    # depend on the date, timezone, field and machine
    # The field is likely to change the number of bytes.

    start_header_length = 0
    match = re.match(regex_trf, trf_contents)

    if match:
        groups = match.groups()
        start_header_length = match.span(4)[1]

    else:
        raise ValueError("Unexpected header content found")

    item_parts_number = np.frombuffer(groups[4][12:16], dtype=np.int32).item()
    final_header_length = len(groups[4][0 : 16 + 4 * item_parts_number])

    header_length = start_header_length + final_header_length

    return header_length


def _header_match(contents):
    regex_trf = (
        rb"[\x00-\x19]"  # start bit
        + rb"(\d\d[/|-]\d\d[/|-]\d\d \d\d:\d\d:\d\d Z)"  # date
        + rb"[\x00-\x19]"  # divider bit
        + rb"([\+|\-]\d\d:\d\d)"  # time zone
        + rb"[\x00-\x32]"  # divider bit
        + rb"([\x20-\x7F]*)"  # field label and name
        + rb"[\x00-\x10]"  # divider bit
        + rb"([\x20-\x7F]*)"  # machine name
        + rb"([\x00-\xFFF]*)"  # mu, version, and item parts numbers
    )

    match = re.match(regex_trf, contents)

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

    # Decode data from first half of header. This comes from the first split groups
    date = groups[0].decode("utf-8")
    timezone = groups[1].decode("utf-8")
    field = groups[2].decode("utf-8")
    machine = groups[3].decode("utf-8")

    # Decode data from the second half of header. This comes from the first bytes of the last group
    mu = np.frombuffer(groups[4][0:8], dtype=np.float64).item()
    version = np.frombuffer(groups[4][8:12], dtype=np.int32).item()
    item_parts_number = np.frombuffer(groups[4][12:16], dtype=np.int32).item()

    # With the item_parts_length read from the header we can get a list of IPVs. This will be useful for a lookup later. These have to be read as in
    item_parts = np.frombuffer(
        groups[4][16 : 16 + 4 * item_parts_number], dtype=np.int16
    )

    item_parts_length = int(len(item_parts))

    split_field = field.split("/")
    if len(split_field) == 2:
        field_label, field_name = split_field
    else:
        field_label, field_name = "", field

    header = Header(
        machine,
        date,
        timezone,
        field_label,
        field_name,
        mu,
        version,
        item_parts_number,
        item_parts_length,
        item_parts,
    )

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
