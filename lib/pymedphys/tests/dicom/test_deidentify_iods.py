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

"""The attribute Types of the supported IODs, generated from DICOM PS3.3."""

import copy
import json

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import iods, standard

MODULES_FILE = standard.STANDARD_DIR / "iod_modules.json"
ATTRIBUTES_FILE = standard.STANDARD_DIR / "module_attributes.json"


@pytest.fixture(name="tables", scope="module")
def _tables():
    return iods.load_iod_tables()


def _types(iod, tag, path=()):
    return {
        (definition.module, definition.type) for definition in iod.lookup(tag, path)
    }


def test_the_first_supported_release_iods_are_generated(tables):
    assert tables.edition == "2026d"
    assert tables.acknowledgement == "DICOM PS3.3 2026d, © NEMA"
    assert {name: iod.label for name, iod in tables.iods.items()} == {
        "CT Image": "Table A.3-1",
        "RT Dose": "Table A.18.3-1",
        "RT Structure Set": "Table A.19.3-1",
        "RT Plan": "Table A.20.3-1",
    }
    assert [len(iod.modules) for iod in tables.iods.values()] == [26, 18, 16, 20]
    assert len(tables.attribute_tables) == 97


def test_modules_keep_their_usage_and_condition(tables):
    ct_modules = {module.module: module for module in tables.iods["CT Image"].modules}
    plan_modules = {module.module: module for module in tables.iods["RT Plan"].modules}
    structure_set_modules = {
        module.module: module for module in tables.iods["RT Structure Set"].modules
    }

    assert ct_modules["Patient"] == iods.ModuleUsage(
        "Patient", "Patient", "C.7.1.1", "M", "", "Table C.7-1"
    )
    assert ct_modules["Contrast/Bolus"].usage == "C"
    assert ct_modules["Contrast/Bolus"].condition == (
        "Required if contrast media was used in this image"
    )
    assert plan_modules["RT Beams"].table == "Table C.8-50"
    assert plan_modules["RT Beams"].condition.startswith(
        "Required if RT Fraction Scheme Module exists"
    )
    assert structure_set_modules["Frame of Reference"].usage == "U"


def test_an_attribute_can_have_a_different_type_in_each_module(tables):
    # Image Type is Type 3 in the General Image Module and Type 1 in the CT
    # Image Module, which specialises it.
    assert _types(tables.iods["CT Image"], "(0008,0008)") == {
        ("General Image", "3"),
        ("CT Image", "1"),
    }


def test_types_depend_on_the_enclosing_sequence(tables):
    ct = tables.iods["CT Image"]

    assert _types(ct, "(0010,0020)") == {("Patient", "2")}
    # Patient ID within Other Patient IDs Sequence (0010,1002) is Type 1.
    assert _types(ct, "(0010,0020)", ("(0010,1002)",)) == {("Patient", "1")}


@pytest.mark.parametrize(
    "iod, tag, path, expected",
    [
        ("RT Plan", "(300A,0002)", (), {("RT General Plan", "1")}),  # RT Plan Label
        ("RT Plan", "(300A,0003)", (), {("RT General Plan", "3")}),  # RT Plan Name
        # Beam Name and Treatment Machine Name within Beam Sequence.
        ("RT Plan", "(300A,00C2)", ("(300A,00B0)",), {("RT Beams", "3")}),
        ("RT Plan", "(300A,00B2)", ("(300A,00B0)",), {("RT Beams", "2")}),
        # Structure Set Label and Date, and ROI Name in Structure Set ROI Sequence.
        ("RT Structure Set", "(3006,0002)", (), {("Structure Set", "1")}),
        ("RT Structure Set", "(3006,0008)", (), {("Structure Set", "2")}),
        (
            "RT Structure Set",
            "(3006,0026)",
            ("(3006,0020)",),
            {("Structure Set", "2")},
        ),
        ("RT Dose", "(3004,000A)", (), {("RT Dose", "1")}),  # Dose Summation Type
        ("CT Image", "(0010,0010)", (), {("Patient", "2")}),  # Patient's Name
    ],
)
def test_spot_types(tables, iod, tag, path, expected):
    assert _types(tables.iods[iod], tag, path) == expected


def test_macros_are_expanded_where_they_are_included(tables):
    ct = tables.iods["CT Image"]

    # Issuer of Patient ID comes from the Issuer of Patient ID Macro, included
    # within Other Patient IDs Sequence.
    (issuer,) = ct.lookup("(0010,0021)", ("(0010,1002)",))
    assert issuer.tables == ("Table C.7-1", "Table 10-18")
    assert issuer.type == "3"

    # Referenced SOP Instance UID within Referenced Image Sequence comes from
    # the SOP Instance Reference Macro, through the Image SOP Instance
    # Reference Macro.
    (reference,) = ct.lookup("(0008,1155)", ("(0008,1140)",))
    assert reference.tables == ("Table C.12-10", "Table 10-3", "Table 10-11")
    assert reference.type == "1"


def test_every_definition_is_reachable_through_its_path(tables):
    for iod in tables.iods.values():
        sequences = {(d.path, d.tag) for d in iod.definitions}
        for definition in iod.definitions:
            if definition.path:
                assert (definition.path[:-1], definition.path[-1]) in sequences


def test_an_attribute_of_a_repeating_group_matches_its_group(tables):
    ct = tables.iods["CT Image"]

    # Overlay Data (60xx,3000), in the Overlay Plane Module.
    assert _types(ct, "(6002,3000)") == {("Overlay Plane", "1")}
    assert ct.lookup("(6002,3000)") == ct.lookup("(60xx,3000)")
    # 6020 is outside the repeating range, and 6001 is a private group.
    assert ct.lookup("(6020,3000)") == ()
    assert ct.lookup("(6001,3000)") == ()


def test_an_attribute_the_iod_does_not_define_has_no_definition(tables):
    # Beam Name is not part of the CT Image IOD, anywhere.
    assert tables.iods["CT Image"].lookup("(300A,00C2)") == ()
    # Nor is Patient ID within Referenced Image Sequence.
    assert tables.iods["CT Image"].lookup("(0010,0020)", ("(0008,1140)",)) == ()


def test_rows_that_describe_attributes_in_words_have_no_tag(tables):
    original_attributes = tables.attribute_tables["Table C.12.1.1.9-1"]
    described = [row for row in original_attributes.rows if row.type and not row.tag]

    assert [row.name for row in described] == [
        "Any Attribute from the top level Data Set that was modified or removed."
    ]


def test_the_loader_caches_by_resolved_path(tables):
    assert iods.load_iod_tables(MODULES_FILE, ATTRIBUTES_FILE) is tables


def _documents():
    return (
        json.loads(MODULES_FILE.read_text(encoding="utf-8")),
        json.loads(ATTRIBUTES_FILE.read_text(encoding="utf-8")),
    )


def _load(tmp_path, modules, attributes, refresh=True):
    for document in (modules, attributes):
        if refresh:
            document["content_sha256"] = standard.content_sha256(document["rows"])
    modules_path = tmp_path / "iod_modules.json"
    attributes_path = tmp_path / "module_attributes.json"
    modules_path.write_text(json.dumps(modules), encoding="utf-8")
    attributes_path.write_text(json.dumps(attributes), encoding="utf-8")
    return iods.load_iod_tables(modules_path, attributes_path)


def _table(attributes, label):
    return next(table for table in attributes["rows"] if table["label"] == label)


def test_a_table_whose_rows_differ_from_their_digest_is_rejected(tmp_path):
    modules, attributes = _documents()
    _table(attributes, "Table C.7-1")["rows"][0]["type"] = "3"

    with pytest.raises(standard.StandardTableError, match="recorded digest"):
        _load(tmp_path, modules, attributes, refresh=False)


def test_files_from_different_editions_are_rejected(tmp_path):
    modules, attributes = _documents()
    modules["edition"] = "2026c"
    modules["acknowledgement"] = "DICOM PS3.3 2026c, © NEMA"

    with pytest.raises(standard.StandardTableError, match="different editions"):
        _load(tmp_path, modules, attributes)


def _patient_rows(attributes):
    return _table(attributes, "Table C.7-1")["rows"]


def _include(attributes):
    rows = _patient_rows(attributes)
    return next(row for row in rows if row["include"] == "Table 10-18")


def _below_include(attributes):
    """Return the row after the Patient Module's top-level Include row."""
    rows = _patient_rows(attributes)
    return rows[rows.index(_include(attributes)) + 1]


@pytest.mark.parametrize(
    "change, message",
    [
        (lambda a: _patient_rows(a)[0].update(type="4"), "Type other than 1, 1C"),
        (lambda a: _patient_rows(a)[0].update(type=""), "Type other than 1, 1C"),
        (lambda a: _patient_rows(a)[0].update(name=""), "has no name"),
        (lambda a: _patient_rows(a)[0].update(tag="0010,0010"), "not of the form"),
        (lambda a: _patient_rows(a)[0].update(depth=True), "non-negative integer"),
        (lambda a: _patient_rows(a)[0].update(depth=-1), "non-negative integer"),
        (lambda a: _patient_rows(a)[0].update(depth=1), "row 1 is nested more deeply"),
        # Nothing can be nested below an Include row.
        (lambda a: _below_include(a).update(depth=1), "is nested more deeply"),
        (lambda a: _patient_rows(a)[0].update(name=["Patient's Name"]), "not text"),
        (lambda a: _patient_rows(a)[0].pop("include"), "without exactly the fields"),
        (
            lambda a: _include(a).update(include="Table 99-99"),
            "which is not in the file",
        ),
        (lambda a: _include(a).update(include="Patient"), "not a table label"),
        (
            lambda a: _include(a).update(type="1"),
            "Include row with a name, tag, or Type",
        ),
        (lambda a: _table(a, "Table C.7-1").update(title=""), "has no title"),
        (lambda a: _table(a, "Table C.7-1").update(rows=[]), "has no rows"),
        (lambda a: _table(a, "Table C.7-1").update(label="C.7-1"), "without a label"),
        (lambda a: a["rows"].append(copy.deepcopy(a["rows"][0])), "more than once"),
    ],
)
def test_malformed_attribute_tables_are_rejected(tmp_path, change, message):
    modules, attributes = _documents()
    change(attributes)

    with pytest.raises(standard.StandardTableError, match=message):
        _load(tmp_path, modules, attributes)


def test_a_table_that_includes_itself_is_rejected(tmp_path):
    modules, attributes = _documents()
    macro = _table(attributes, "Table 10-18")
    macro["rows"].append(
        {"depth": 0, "name": "", "tag": "", "type": "", "include": "Table C.7-1"}
    )

    with pytest.raises(
        standard.StandardTableError,
        match="Table 10-18 includes itself: Table 10-18 > Table C.7-1 > Table 10-18",
    ):
        _load(tmp_path, modules, attributes)


def _ct_modules(modules):
    return modules["rows"][0]["modules"]


@pytest.mark.parametrize(
    "change, message",
    [
        (lambda m: _ct_modules(m)[0].update(usage="R"), "usage other than M, C, or U"),
        (
            lambda m: _ct_modules(m)[0].update(table="Table 99-99"),
            "not in the attribute",
        ),
        (lambda m: _ct_modules(m)[0].update(module=""), "is empty"),
        (lambda m: _ct_modules(m)[0].update(condition=None), "not text"),
        (lambda m: _ct_modules(m)[0].pop("section"), "without exactly the fields"),
        (lambda m: _ct_modules(m).append(_ct_modules(m)[0]), "a module more than once"),
        (lambda m: m["rows"][0].update(modules=[]), "has no modules"),
        (lambda m: m["rows"][0].update(iod=""), "has no IOD name"),
        (lambda m: m["rows"][0].update(label=3), "without a table label"),
        (lambda m: m["rows"][0].pop("iod"), "without exactly the fields"),
        (lambda m: m["rows"].append(copy.deepcopy(m["rows"][0])), "CT Image more than"),
    ],
)
def test_malformed_iod_modules_are_rejected(tmp_path, change, message):
    modules, attributes = _documents()
    change(modules)

    with pytest.raises(standard.StandardTableError, match=message):
        _load(tmp_path, modules, attributes)
