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
import pathlib

from pymedphys._imports import pytest

from pymedphys._dev.deid_tables import generate
from pymedphys._dicom.deidentify import standard

E1_1 = standard.STANDARD_DIR / "e1_1.json"


def _document():
    return json.loads(E1_1.read_text(encoding="utf-8"))


def _write(path, document):
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "name, source",
    [
        ("e1_1.json", "part15/chapter_E.html"),
        ("e1_1a.json", "part15/chapter_E.html"),
        ("e3_10_1.json", "part15/sect_E.3.10.html"),
    ],
)
def test_each_table_is_generated_from_the_pinned_edition(name, source):
    # A new pin without regenerated tables, or the reverse, fails here.
    document = json.loads((standard.STANDARD_DIR / name).read_text(encoding="utf-8"))
    pinned = {pinned.path: pinned.sha256 for pinned in generate.PIN.sources}

    assert document["edition"] == generate.PIN.edition
    assert document["sources"] == [{"path": source, "sha256": pinned[source]}]


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


def test_an_altered_row_is_rejected(tmp_path):
    document = _document()
    document["rows"][0]["basic_profile"] = "K"

    with pytest.raises(standard.StandardTableError, match="recorded digest"):
        standard.load_table_e1_1(_write(tmp_path / "e1_1.json", document))


_MISSING = object()


@pytest.mark.parametrize(
    "edition",
    [_MISSING, None, "", 2026, ["2026d"]],
    ids=["missing", "null", "empty", "number", "list"],
)
def test_an_edition_that_is_not_text_is_rejected(tmp_path, edition):
    # The acknowledgement is made to match, so only the edition is wrong.
    document = _document()
    if edition is _MISSING:
        del document["edition"]
        edition = None
    else:
        document["edition"] = edition
    document["acknowledgement"] = f"DICOM PS3.15 {edition}, \u00a9 NEMA"

    with pytest.raises(standard.StandardTableError, match="edition"):
        standard.load_table_e1_1(_write(tmp_path / "e1_1.json", document))


def test_rows_that_cannot_be_encoded_are_rejected(tmp_path):
    # JSON can escape a lone surrogate, which has no UTF-8 encoding.
    document = _document()
    document["rows"][0]["name"] = "\ud800"
    path = tmp_path / "e1_1.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(standard.StandardTableError, match="row"):
        standard.load_table_e1_1(path)


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


def _redigested(document):
    """Record the digest of the rows as they now are, as a careful editor would."""
    document["content_sha256"] = standard.content_sha256(document["rows"])
    return document


def _set(field, value):
    def change(row):
        row[field] = value

    return change


def _remove(field):
    def change(row):
        del row[field]

    return change


@pytest.mark.parametrize(
    "change",
    [
        pytest.param(_remove("tag"), id="missing-field"),
        pytest.param(_set("note", "extra"), id="extra-field"),
        pytest.param(_set("name", ["Accession Number"]), id="name-not-text"),
        pytest.param(_set("name", ""), id="empty-name"),
        pytest.param(_set("tag", ""), id="empty-tag"),
        pytest.param(_set("retired", "false"), id="retired-as-text"),
        pytest.param(_set("in_standard_iod", 1), id="in-iod-as-number"),
        pytest.param(_set("basic_profile", "Q"), id="undefined-action"),
        pytest.param(_set("basic_profile", ["Z"]), id="action-not-text"),
        pytest.param(
            _set("options", [["retain_uids", "K"]]), id="options-not-a-mapping"
        ),
        pytest.param(_set("options", {"retain_uids": ["K"]}), id="option-not-text"),
        pytest.param(
            _set("options", {"retain_uids": "Q"}), id="undefined-option-action"
        ),
        pytest.param(_set("options", {"retain_all": "K"}), id="unknown-option"),
    ],
)
def test_a_malformed_row_is_rejected(tmp_path, change):
    # The digest is recomputed, so only the row itself is wrong.
    document = _document()
    change(document["rows"][0])

    with pytest.raises(standard.StandardTableError, match="row 1"):
        standard.load_table_e1_1(_write(tmp_path / "e1_1.json", _redigested(document)))


def test_a_row_that_is_not_an_object_is_rejected(tmp_path):
    document = _document()
    document["rows"][0] = ["Accession Number", "(0008,0050)"]

    with pytest.raises(standard.StandardTableError, match="row 1"):
        standard.load_table_e1_1(_write(tmp_path / "e1_1.json", _redigested(document)))


@pytest.mark.parametrize("rows", [[], {}], ids=["empty-list", "object"])
def test_a_table_without_a_list_of_rows_is_rejected(tmp_path, rows):
    document = _document()
    document["rows"] = rows

    with pytest.raises(standard.StandardTableError, match="no rows"):
        standard.load_table_e1_1(_write(tmp_path / "e1_1.json", _redigested(document)))


def test_a_repeated_tag_is_rejected(tmp_path):
    document = _document()
    document["rows"].append(dict(document["rows"][0]))

    with pytest.raises(standard.StandardTableError, match="row 658 repeats"):
        standard.load_table_e1_1(_write(tmp_path / "e1_1.json", _redigested(document)))


def test_relative_paths_are_resolved_before_caching(tmp_path, monkeypatch):
    # The same relative path names different files in different directories.
    valid, invalid = tmp_path / "valid", tmp_path / "invalid"
    valid.mkdir()
    invalid.mkdir()
    _write(valid / "e1_1.json", _document())
    (invalid / "e1_1.json").write_text("{", encoding="utf-8")

    monkeypatch.chdir(valid)
    standard.load_table_e1_1(pathlib.Path("e1_1.json"))
    monkeypatch.chdir(invalid)
    with pytest.raises(standard.StandardTableError):
        standard.load_table_e1_1(pathlib.Path("e1_1.json"))


@pytest.mark.parametrize("text", ["", "[]", "{"])
def test_an_unreadable_file_is_rejected(tmp_path, text):
    path = tmp_path / "e1_1.json"
    path.write_text(text, encoding="utf-8")

    with pytest.raises(standard.StandardTableError):
        standard.load_table_e1_1(path)


def test_a_missing_file_is_rejected(tmp_path):
    with pytest.raises(standard.StandardTableError, match="could not be read"):
        standard.load_table_e1_1(tmp_path / "e1_1.json")


E1_1A = standard.STANDARD_DIR / "e1_1a.json"
E3_10_1 = standard.STANDARD_DIR / "e3_10_1.json"


def _loaded(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_table_e1_1a_defines_every_implemented_action_code():
    table = standard.load_table_e1_1a()

    assert table.edition == "2026d"
    assert table.acknowledgement == "DICOM PS3.15 2026d, \u00a9 NEMA"
    assert [action.code for action in table.codes] == [
        "D",
        "Z",
        "X",
        "K",
        "C",
        "U",
        "Z/D",
        "X/Z",
        "X/D",
        "X/Z/D",
        "X/Z/U*",
    ]
    assert table.codes[0].description == (
        "replace with a non-zero length value that may be a dummy value and "
        "consistent with the VR"
    )


def test_table_e3_10_1_has_every_row_of_the_2026d_table():
    # Counts measured from the published 2026d table.
    table = standard.load_table_e3_10_1()

    assert table.edition == "2026d"
    assert len(table.attributes) == 479
    assert len({a.private_creator for a in table.attributes}) == 20
    assert sum(1 for a in table.attributes if not a.vr) == 5


@pytest.mark.parametrize(
    "row",
    [
        standard.SafePrivateAttribute(
            "(7053,xx00)",
            "Philips PET Private Group",
            "DS",
            "1",
            "SUV Factor - Multiplying Stored Pixel Values by Rescale Slope then "
            "this factor results in SUVbw in g/l",
        ),
        standard.SafePrivateAttribute("(00E1,xx21)", "ELSCINT1", "DS", "1", "DLP"),
        # Published with a lower-case hexadecimal digit.
        standard.SafePrivateAttribute(
            "(2001,xx0a)", "Philips Imaging DD 001", "IS", "1", "Image Plane Number"
        ),
        # Published without a VR.
        standard.SafePrivateAttribute(
            "(0119,xx11)", "SIEMENS Ultrasound SC2000", "", "1", "Stage Timer Time"
        ),
        standard.SafePrivateAttribute(
            "(2001,xx7d)", "Philips Imaging DD 001", "OW/OB", "1", "Frame Pixel Data"
        ),
    ],
)
def test_table_e3_10_1_rows(row):
    assert row in standard.load_table_e3_10_1().attributes


def test_the_new_rows_are_hashable():
    hash(standard.load_table_e1_1a())
    hash(standard.load_table_e3_10_1())


@pytest.mark.parametrize(
    "load, path",
    [
        (standard.load_table_e1_1a, E1_1),
        (standard.load_table_e3_10_1, E1_1),
        (standard.load_table_e1_1, E3_10_1),
    ],
)
def test_a_loader_rejects_another_table(tmp_path, load, path):
    with pytest.raises(standard.StandardTableError, match="is not a"):
        load(_write(tmp_path / path.name, _loaded(path)))


@pytest.mark.parametrize(
    "change, message",
    [
        (lambda rows: rows.pop(0), "does not define the action codes D"),
        (lambda rows: rows[0].update(code="U*"), "row 1 has a code"),
        (lambda rows: rows[0].update(description=""), "row 1 has a description"),
        (lambda rows: rows[0].update(note="extra"), "row 1 does not have exactly"),
        (lambda rows: rows.append(dict(rows[0])), "row 12 repeats an action code"),
    ],
)
def test_a_malformed_table_e1_1a_is_rejected(tmp_path, change, message):
    document = _loaded(E1_1A)
    change(document["rows"])

    with pytest.raises(standard.StandardTableError, match=message):
        standard.load_table_e1_1a(
            _write(tmp_path / "e1_1a.json", _redigested(document))
        )


@pytest.mark.parametrize(
    "field, value, message",
    [
        ("tag", "(7054,xx00)", "row 1 has a tag"),
        ("tag", "(7053,0000)", "row 1 has a tag"),
        ("tag", ["(7053,xx00)"], "row 1 has a tag"),
        ("private_creator", "", "row 1 has a private creator"),
        ("vr", "ds", "row 1 has a VR"),
        ("vr", None, "row 1 has a VR"),
        ("vm", "n", "row 1 has a VM"),
        ("meaning", None, "row 1 has a meaning"),
    ],
)
def test_a_malformed_table_e3_10_1_row_is_rejected(tmp_path, field, value, message):
    document = _loaded(E3_10_1)
    document["rows"][0][field] = value

    with pytest.raises(standard.StandardTableError, match=message):
        standard.load_table_e3_10_1(
            _write(tmp_path / "e3_10_1.json", _redigested(document))
        )


def test_a_repeated_private_creator_and_tag_is_rejected(tmp_path):
    # Tags are compared without regard to the case of their hexadecimal digits.
    document = _loaded(E3_10_1)
    lower = next(row for row in document["rows"] if row["tag"] == "(2001,xx0a)")
    document["rows"].append(dict(lower, tag="(2001,xx0A)"))

    with pytest.raises(standard.StandardTableError, match="repeats a private creator"):
        standard.load_table_e3_10_1(
            _write(tmp_path / "e3_10_1.json", _redigested(document))
        )
