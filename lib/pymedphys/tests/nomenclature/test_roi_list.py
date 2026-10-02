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

"""Converting an institutional list of ROI names from CSV to JSON.

Every list here is invented.
"""

import hashlib
import json
import re

from pymedphys._imports import pytest

from pymedphys._nomenclature import roi_list

CSV = "Name,Description\nLung_L,Left lung\nPTV_Boost,\nSpinal Cord PRV,Cord plus 5 mm\n"
ENTRIES = (
    roi_list.Entry("Lung_L", "Left lung"),
    roi_list.Entry("PTV_Boost", ""),
    roi_list.Entry("Spinal Cord PRV", "Cord plus 5 mm"),
)


def _write(tmp_path, text, name="site-roi-names.csv", encoding="utf-8"):
    path = tmp_path / name
    path.write_bytes(text.encode(encoding))
    return path


def test_read_csv(tmp_path):
    path = _write(tmp_path, CSV)
    names = roi_list.read_csv(path, version="2026-10")

    assert names.entries == ENTRIES
    assert names.source == roi_list.Source(
        kind="institutional-list",
        file="site-roi-names.csv",
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        version="2026-10",
    )


def test_a_name_column_alone_is_enough(tmp_path):
    names = roi_list.read_csv(_write(tmp_path, "Name\nHeart\nLiver\n"), version="1")
    assert names.entries == (roi_list.Entry("Heart", ""), roi_list.Entry("Liver", ""))


def test_columns_are_found_by_header_in_any_order(tmp_path):
    text = "Description,Name\nLeft lung,Lung_L\n"
    names = roi_list.read_csv(_write(tmp_path, text), version="1")
    assert names.entries == (roi_list.Entry("Lung_L", "Left lung"),)


def test_excel_byte_order_mark_crlf_and_padding_are_accepted(tmp_path):
    text = "﻿ Name , Description \r\n  Lung_L  , Left lung \r\n\r\n,\r\n"
    names = roi_list.read_csv(_write(tmp_path, text), version="1")
    assert names.entries == (roi_list.Entry("Lung_L", "Left lung"),)


def test_quoted_values_may_hold_commas(tmp_path):
    text = 'Name,Description\nLung_L,"Left lung, whole"\n'
    names = roi_list.read_csv(_write(tmp_path, text), version="1")
    assert names.entries == (roi_list.Entry("Lung_L", "Left lung, whole"),)


@pytest.mark.parametrize(
    "text, message",
    [
        ("", "empty"),
        ("Description\nLeft lung\n", "missing column 'Name'"),
        ("Name,Site\nLung_L,A\n", "unknown column 'Site'"),
        ("Name,\nLung_L,\n", "unknown column ''"),
        ("Name,Name\nLung_L,Lung_R\n", "column 'Name' appears 2 times"),
        ("Name\n", "no names"),
        ("Name\nLung_L,extra\n", "row 2 has more cells than the header"),
        ("Name,Description\n,Left lung\n", "row 2: 'Name' is empty"),
        ("Name\nLung_L\nLung_L\n", "'Lung_L' appears 2 times"),
        ("Name\nLung\\L\n", "row 2: 'Name' is not a valid LO value"),
        ("Name\nLung\tL\n", "row 2: 'Name' is not a valid LO value"),
        ("Name\n" + "x" * 65 + "\n", "row 2: 'Name' is not a valid LO value"),
        ('Name\n"Lung\nL"\n', "row 2: 'Name' is not a valid LO value"),
    ],
)
def test_invalid_lists_fail(tmp_path, text, message):
    with pytest.raises(roi_list.RoiListError, match=re.escape(message)):
        roi_list.read_csv(_write(tmp_path, text), version="1")


def test_a_64_character_name_is_valid(tmp_path):
    names = roi_list.read_csv(_write(tmp_path, "Name\n" + "x" * 64 + "\n"), version="1")
    assert names.entries == (roi_list.Entry("x" * 64, ""),)


def test_names_that_differ_only_in_case_are_different_names(tmp_path):
    names = roi_list.read_csv(_write(tmp_path, "Name\nLung_L\nLUNG_L\n"), version="1")
    assert [entry.name for entry in names.entries] == ["Lung_L", "LUNG_L"]


def test_a_file_that_is_not_utf8_fails(tmp_path):
    path = _write(tmp_path, "Name\nPoumon_é\n", encoding="latin-1")
    with pytest.raises(roi_list.RoiListError, match="not UTF-8"):
        roi_list.read_csv(path, version="1")


@pytest.mark.parametrize("version", ["", " ", " 1", "a\nb"])
def test_the_version_must_be_given(tmp_path, version):
    with pytest.raises(roi_list.RoiListError, match="version"):
        roi_list.read_csv(_write(tmp_path, CSV), version=version)


def test_json_round_trip(tmp_path):
    names = roi_list.read_csv(_write(tmp_path, CSV), version="2026-10")
    path = tmp_path / "roi-list.json"
    path.write_text(roi_list.to_json(names), encoding="utf-8")
    assert roi_list.load_json(path) == names


def test_json_is_deterministic_and_carries_its_provenance(tmp_path):
    names = roi_list.read_csv(_write(tmp_path, CSV), version="2026-10")
    text = roi_list.to_json(names)
    document = json.loads(text)

    assert text == roi_list.to_json(names)
    assert text.endswith("\n")
    assert list(document) == ["format", "source", "content_sha256", "entries"]
    assert document["format"] == "pymedphys-roi-list/1"
    assert document["source"]["kind"] == "institutional-list"
    assert document["content_sha256"] == roi_list.content_sha256(document["entries"])


def _document(tmp_path):
    names = roi_list.read_csv(_write(tmp_path, CSV), version="2026-10")
    return json.loads(roi_list.to_json(names))


def _set(document, keys, value):
    target = document
    for key in keys[:-1]:
        target = target[key]
    target[keys[-1]] = value


@pytest.mark.parametrize(
    "keys, value, message",
    [
        (("format",), "pymedphys-tg263/1", "format"),
        (("source", "kind"), "aapm-tg263", "malformed source"),
        (("source", "sha256"), "ABC", "malformed source"),
        (("source", "version"), "", "malformed source"),
        (("entries",), {}, "no list of entries"),
        (("entries",), [], "no names"),
        (("entries", 0, "name"), "", "entry 1: 'name' is empty"),
        (("entries", 0, "extra"), "", "keys other than"),
        (("entries", 1, "name"), "Lung_L", "'Lung_L' appears 2 times"),
        (("entries", 0, "description"), 3, "entry 1: 'description' is not text"),
    ],
)
def test_malformed_json_is_rejected(tmp_path, keys, value, message):
    document = _document(tmp_path)
    _set(document, keys, value)
    path = tmp_path / "roi-list.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(roi_list.RoiListError, match=re.escape(message)):
        roi_list.load_json(path)


def test_a_missing_or_extra_key_is_rejected(tmp_path):
    document = _document(tmp_path)
    document["attribution"] = ""
    path = tmp_path / "roi-list.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(roi_list.RoiListError, match="does not have the keys"):
        roi_list.load_json(path)


def test_json_edited_without_its_digest_is_rejected(tmp_path):
    document = _document(tmp_path)
    document["entries"][0]["name"] = "ClinicX_Lung"
    path = tmp_path / "roi-list.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(roi_list.RoiListError, match="content_sha256"):
        roi_list.load_json(path)


def test_unreadable_json_is_rejected(tmp_path):
    path = tmp_path / "roi-list.json"
    path.write_text("{", encoding="utf-8")
    with pytest.raises(roi_list.RoiListError, match="not valid JSON"):
        roi_list.load_json(path)
