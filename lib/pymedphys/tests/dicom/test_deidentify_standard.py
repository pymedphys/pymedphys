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

"""The rule tables generated from DICOM PS3.15, and their loader."""

import collections
import json

from pymedphys._imports import pytest

from pymedphys._dev.deid_tables import generate
from pymedphys._dicom.deidentify import standard

E1_1 = standard.STANDARD_DIR / "e1_1.json"
LICENCE = standard.STANDARD_DIR / "LICENSE-NEMA-DICOM"


def _document():
    return json.loads(E1_1.read_text(encoding="utf-8"))


def _write(path, document):
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    return path


def test_table_e1_1_is_generated_from_the_pinned_edition():
    # A new pin without regenerated tables, or the reverse, fails here.
    document = _document()

    assert document["edition"] == generate.PIN.edition
    assert document["sources"] == [
        {"path": source.path, "sha256": source.sha256}
        for source in generate.PIN.sources
    ]


def test_table_e1_1_has_every_row_of_the_2026d_table():
    # Counts measured from the published 2026d table.
    table = standard.load_table_e1_1()

    assert table.edition == "2026d"
    assert len(table.attributes) == 657
    assert collections.Counter(a.basic_profile for a in table.attributes) == {
        "X": 417,
        "D": 93,
        "U": 55,
        "Z": 42,
        "X/D": 23,
        "X/Z": 11,
        "X/Z/D": 8,
        "Z/D": 6,
        "X/Z/U*": 2,
    }


@pytest.mark.parametrize(
    "tag, name, basic_profile, options",
    [
        ("(0010,0010)", "Patient's Name", "Z", {}),
        ("(0010,0020)", "Patient ID", "Z/D", {}),
        (
            "(0008,0020)",
            "Study Date",
            "Z",
            {
                "retain_longitudinal_full_dates": "K",
                "retain_longitudinal_modified_dates": "C",
            },
        ),
        ("(0008,0018)", "SOP Instance UID", "U", {"retain_uids": "K"}),
        ("(3006,0026)", "ROI Name", "Z", {"clean_descriptors": "C"}),
        ("(300A,0083)", "Referenced Dose Reference UID", "U", {"retain_uids": "K"}),
        (
            "(300A,00B2)",
            "Treatment Machine Name",
            "X/Z",
            {"retain_device_identity": "K"},
        ),
        (
            "(gggg,eeee) where gggg is odd",
            "Private Attributes",
            "X",
            {"retain_safe_private": "C"},
        ),
    ],
)
def test_table_e1_1_rows(tag, name, basic_profile, options):
    rows = {a.tag: a for a in standard.load_table_e1_1().attributes}

    assert rows[tag].name == name
    assert rows[tag].basic_profile == basic_profile
    assert rows[tag].options == options


def test_rows_are_hashable_and_read_only():
    attribute = standard.load_table_e1_1().attributes[0]

    hash(attribute)
    with pytest.raises(TypeError):
        attribute.options["retain_uids"] = "K"  # type: ignore[index]


def test_the_licence_names_each_table_and_its_acknowledgement():
    # LICENSE-NEMA-DICOM carries each table's acknowledgement and the
    # statement that the standard is under continuous maintenance.
    licence = LICENCE.read_text(encoding="utf-8")

    assert (
        "The DICOM Standard is under continuous maintenance, and the current "
        "official\nversion is available at http://www.dicomstandard.org"
    ) in licence
    for path in sorted(standard.STANDARD_DIR.glob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        assert f"- {path.name}:" in licence
        assert f"Source: {document['acknowledgement']}." in licence


def test_an_altered_row_is_rejected(tmp_path):
    document = _document()
    document["rows"][0]["basic_profile"] = "K"

    with pytest.raises(standard.StandardTableError, match="recorded digest"):
        standard.load_table_e1_1(_write(tmp_path / "e1_1.json", document))


def test_a_missing_acknowledgement_is_rejected(tmp_path):
    document = _document()
    del document["acknowledgement"]

    with pytest.raises(standard.StandardTableError, match="acknowledgement"):
        standard.load_table_e1_1(_write(tmp_path / "e1_1.json", document))


@pytest.mark.parametrize(
    "field, value", [("schema", "pymedphys-deid-table/0"), ("table", "Table E.1-1a")]
)
def test_another_schema_or_table_is_rejected(tmp_path, field, value):
    document = _document()
    document[field] = value

    with pytest.raises(standard.StandardTableError, match="is not a"):
        standard.load_table_e1_1(_write(tmp_path / "e1_1.json", document))


def test_a_malformed_row_is_rejected(tmp_path):
    # The digest is recomputed, so only the row's shape is wrong.
    document = _document()
    del document["rows"][0]["tag"]
    document["content_sha256"] = standard.content_sha256(document["rows"])

    with pytest.raises(standard.StandardTableError, match="malformed row"):
        standard.load_table_e1_1(_write(tmp_path / "e1_1.json", document))


@pytest.mark.parametrize("text", ["", "[]", "{"])
def test_an_unreadable_file_is_rejected(tmp_path, text):
    path = tmp_path / "e1_1.json"
    path.write_text(text, encoding="utf-8")

    with pytest.raises(standard.StandardTableError):
        standard.load_table_e1_1(path)


def test_a_missing_file_is_rejected(tmp_path):
    with pytest.raises(standard.StandardTableError, match="could not be read"):
        standard.load_table_e1_1(tmp_path / "e1_1.json")
