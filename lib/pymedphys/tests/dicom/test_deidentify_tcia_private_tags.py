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

"""TCIA's Private Tag Dictionary, shipped unchanged and pinned by its SHA-256.

No test here reaches the network.
"""

import collections
import csv
import hashlib
import io
import re

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import tcia_private_tags
from pymedphys._dicom.deidentify.tcia_private_tags import Step

SHIPPED = tcia_private_tags.TCIA_DIR / tcia_private_tags.PIN.file_name
HEADER = "element_sig_pattern,tag_name,vr,private_disposition\r\n"
PET = "Philips PET Private Group"


@pytest.fixture(name="dictionary", scope="module")
def _dictionary():
    return tcia_private_tags.load_tcia_private_tags()


def _parse(*rows):
    """Parse a dictionary of ``rows``, each a tuple of cells or a raw line."""
    text = io.StringIO()
    writer = csv.writer(text, lineterminator="\r\n")
    for row in rows:
        if isinstance(row, str):
            text.write(row + "\r\n")
        else:
            writer.writerow(row)
    content = ("\ufeff" + HEADER + text.getvalue()).encode("utf-8")
    return tcia_private_tags.parse_tcia_private_tags(content, "test.csv")


@pytest.mark.deid_requirement("PS3.15-E.3.10-01", "MIDI-BP-13")
def test_the_shipped_file_is_the_pinned_original_with_its_licence():
    content = SHIPPED.read_bytes()
    pin = tcia_private_tags.PIN

    assert len(content) == pin.size == 674200
    assert hashlib.sha256(content).hexdigest() == pin.sha256
    assert pin.url.startswith("https://wiki.cancerimagingarchive.net/")
    assert pin.file_name in pin.url
    # The file is distributed unchanged, with TCIA's attribution and the
    # licence that TCIA publishes its site under.
    licence = (tcia_private_tags.TCIA_DIR / "LICENSE-CC-BY-3.0.txt").read_text("utf-8")
    assert pin.url in licence
    assert pin.page_url in licence
    assert "The Cancer Imaging Archive (TCIA)" in licence
    assert "Attribution 3.0 Unported" in licence


def test_every_row_is_read_with_its_disposition(dictionary):
    counts = collections.Counter(row.disposition for row in dictionary.rows)

    assert len(dictionary.rows) == 8787
    # Counted by hand from the file: " k" and "K" are read as "k", and "D"
    # as "d".
    assert counts == {
        "d": 4587,
        "k": 3836,
        "na": 210,
        "h": 84,
        "o": 46,
        "": 15,
        "oi": 9,
    }
    assert sum(row.keeps for row in dictionary.rows) == 3836
    assert dictionary.pin == tcia_private_tags.PIN


def test_a_path_is_read_through_its_sequences(dictionary):
    first, *_ = dictionary.rows

    # (0008,1084)[<0>](312f,"Ramsoft Diagnosis Datetime Identifier",10)
    assert first.path == (
        Step(0x0008, 0x1084),
        Step(0x312F, 0x10, "Ramsoft Diagnosis Datetime Identifier"),
    )
    assert (first.vr, first.disposition, first.keeps) == ("DA", "d", False)
    assert not first.path[0].is_private and first.path[1].is_private
    # A private creator nested in the items of private sequences is a tag.
    nested = [row for row in dictionary.rows if row.path[-1] == Step(0x0029, 0x0010)]
    assert len(nested) == 3
    assert all(len(row.path) > 1 and row.path[0].is_private for row in nested)


@pytest.mark.deid_requirement("PS3.15-E.3.10-01", "MIDI-BP-13")
def test_top_level_rows_are_found_by_creator_group_and_element(dictionary):
    (suv,) = dictionary.rows_for(0x7053, PET, 0x00)

    assert (suv.name, suv.vr, suv.keeps) == ("SUV Factor", "DS", True)
    assert dictionary.rows_for(0x7053, PET + " \x00", 0x00) == (suv,)
    assert dictionary.rows_for(0x7053, PET.upper(), 0x00) == ()
    assert dictionary.rows_for(0x7055, PET, 0x00) == ()
    # Only top-level rows are keyed.
    assert all(
        len(row.path) == 1 for each in dictionary.top_level.values() for row in each
    )
    assert sum(len(each) for each in dictionary.top_level.values()) == 6568
    # An attribute can have a row for each of several VRs.
    assert any(
        len({row.vr for row in each}) > 1 for each in dictionary.top_level.values()
    )


def test_a_creator_in_upper_case_matches_only_upper_case(dictionary):
    upper = dictionary.rows_for(0x2005, "PHILIPS MR IMAGING DD 001", 0x35)
    mixed = dictionary.rows_for(0x2005, "Philips MR Imaging DD 001", 0x35)

    assert {row.vr for row in upper} == {"CS", "SS"}
    assert upper != mixed


def test_attributes_without_a_creator_are_read_with_an_empty_one(dictionary):
    rows = [
        row for row in dictionary.rows if any(s.private_creator == "" for s in row.path)
    ]

    assert len(rows) == 333
    assert {row.disposition for row in rows} == {"d"}
    assert dictionary.rows_for(0x0009, "", 0x02)


@pytest.mark.deid_requirement("PS3.15-E.3.10-01", "MIDI-BP-13")
def test_an_altered_or_missing_copy_is_refused(tmp_path):
    content = bytearray(SHIPPED.read_bytes())
    content[-1] = ord("k") if content[-1] != ord("k") else ord("d")
    altered = tmp_path / tcia_private_tags.PIN.file_name
    altered.write_bytes(bytes(content))

    with pytest.raises(
        tcia_private_tags.TciaPrivateTagError,
        match="its length or SHA-256 does not match the pin",
    ):
        tcia_private_tags.load_tcia_private_tags(altered)
    with pytest.raises(
        tcia_private_tags.TciaPrivateTagError, match="could not be read"
    ):
        tcia_private_tags.load_tcia_private_tags(tmp_path / "missing.csv")


def test_dispositions_are_read_without_spaces_or_case():
    # Raw lines, quoted as the file quotes its patterns.
    parsed = _parse(
        '"(0019,GEMS_ACQU_01"",23)",Table Speed,DS, k',
        '"(0019,""GEMS_ACQU_01"",24)",Mid Scan Time,DS,D',
        '"(0019,GEMS_ACQU_01,27)",Rotation Speed,DS,K',
    )

    assert [row.disposition for row in parsed.rows] == ["k", "d", "k"]
    assert [row.path[0].private_creator for row in parsed.rows] == ["GEMS_ACQU_01"] * 3
    assert parsed.rows_for(0x0019, "GEMS_ACQU_01", 0x27)[0].keeps


def test_a_creator_with_a_comma_is_read_whole():
    (row,) = _parse('"(7E01,""HOLOGIC, Inc."",01)",Codec Version,LO,k').rows

    assert row.path == (Step(0x7E01, 0x01, "HOLOGIC, Inc."),)


@pytest.mark.parametrize(
    "row, message",
    [
        (("(0019,GEMS_ACQU_01,23)", "x", "DS"), "does not have the 4 columns"),
        (("(0019,GEMS_ACQU_01,23)", "x", "DS", "k", "x"), "does not have the 4"),
        (("(0019,GEMS_ACQU_01,123)", "x", "DS", "k"), "is not a path of tags"),
        (("(0018,GEMS_ACQU_01,23)", "x", "DS", "k"), "is not a path of tags"),
        (("(0001,GEMS_ACQU_01,23)", "x", "DS", "k"), "is not a path of tags"),
        (("(FFFF,GEMS_ACQU_01,23)", "x", "DS", "k"), "is not a path of tags"),
        (("(0008,1115)(0019,A,23)", "x", "DS", "k"), "is not a path of tags"),
        (("(0008,1115)[<1>](0019,A,23)", "x", "DS", "k"), "is not a path of tags"),
        (
            ("(0008,1115)[<0>](0008,1140)[<0>](0019,A,23)", "x", "DS", "k"),
            "is not a path of tags",
        ),
        (("(0019,A,23)[<0>]", "x", "DS", "k"), "is not a path of tags"),
        (("(0008,1115)[<0>](0008,1140)", "x", "SQ", "k"), "describes no private"),
        (("(0019,A,23)", "x", "XX", "k"), "has a VR that is not empty or one PS3.5"),
        (("(0019,A,23)", "x", "OW/OB", "k"), "has a VR that is not empty or one"),
        (("(0019,A,23)", "x", "DS", "keep"), "has a disposition that is not one of"),
    ],
)
def test_a_malformed_row_is_refused_by_its_number(row, message):
    with pytest.raises(
        tcia_private_tags.TciaPrivateTagError,
        match=re.escape("test.csv row 2 ") + ".*" + re.escape(message),
    ):
        _parse(("(0019,GEMS_ACQU_01,24)", "Mid Scan Time", "DS", "d"), row)


def test_a_file_with_other_columns_or_encoding_is_refused():
    for content, message in (
        (b"pattern,name,vr,disposition\r\n", "does not have the columns"),
        (b"", "does not have the columns"),
        (HEADER.encode() + b'"(0019,\xff,23)",x,DS,k', "is not UTF-8 CSV"),
    ):
        with pytest.raises(tcia_private_tags.TciaPrivateTagError, match=message):
            tcia_private_tags.parse_tcia_private_tags(content, "test.csv")
