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

"""The attribute Types of the composite IODs, generated from DICOM PS3.3."""

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


FIRST_RELEASE = {
    "CT Image": "Table A.3-1",
    "RT Dose": "Table A.18.3-1",
    "RT Structure Set": "Table A.19.3-1",
    "RT Plan": "Table A.20.3-1",
}


def test_the_first_supported_release_iods_are_generated(tables):
    assert tables.edition == "2026d"
    assert tables.acknowledgement == "DICOM PS3.3 2026d, © NEMA"
    assert {name: tables.iods[name].label for name in FIRST_RELEASE} == FIRST_RELEASE
    assert [len(tables.iods[name].modules) for name in FIRST_RELEASE] == [
        26,
        18,
        16,
        20,
    ]


def test_every_composite_iod_without_functional_group_macros_is_generated(tables):
    # Counted from the published 2026d PS3.3: 174 IOD Modules tables in Annex
    # A, 33 of whose IODs have Functional Group Macros.
    assert len(tables.iods) == 141
    assert len(tables.attribute_tables) == 471
    assert all(iod.label.startswith("Table A.") for iod in tables.iods.values())
    # Segmentation and Enhanced CT Image are among those left out.
    assert "Segmentation" not in tables.iods
    assert "Enhanced CT Image" not in tables.iods


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


@pytest.mark.parametrize(
    "iod, module, expected",
    [
        # Published with an en dash, or nothing, between usage and condition.
        (
            "RT Beams Treatment Record",
            "RT Beams Salvage Record",
            ("C.8.8.31", "C", "Required if Treatment Record Content Origin"),
        ),
        (
            "RT Ion Beams Treatment Record",
            "RT Ion Beams Salvage Record",
            ("C.8.8.32", "C", "Required if Treatment Record Content Origin"),
        ),
        (
            "Volume Rendering Volumetric Presentation State",
            "Graphic Layer",
            ("C.10.7", "C", "Required if Graphic Layer (0070,0002) is present"),
        ),
        # A section with a letter, and sections the published tables give
        # wrongly or title differently.
        (
            "Ophthalmic Photography 8 Bit Image",
            "Enhanced Contrast/Bolus",
            ("C.7.6.4b", "C", "Required if contrast was administered"),
        ),
        ("Implant Template Group", "Implant Template Group", ("C.29.3.1", "M", "")),
        (
            "Nuclear Medicine Image",
            "NM Multi-gated Acquisition",
            ("C.8.4.13", "C", "Required if Image Type (0008,0008) Value 3 is GATED"),
        ),
        (
            "Positron Emission Tomography Image",
            "PET Multi-gated Acquisition",
            ("C.8.9.3", "C", "Required if Series Type (0054,1000) Value 1 is GATED"),
        ),
        (
            "Waveform Presentation State",
            "Waveform Presentation State Relationship",
            ("C.39.1", "M", ""),
        ),
    ],
)
def test_modules_whose_published_rows_are_corrected(tables, iod, module, expected):
    (found,) = [m for m in tables.iods[iod].modules if m.module == module]
    section, usage, condition = expected

    assert (found.section, found.usage) == (section, usage)
    assert found.condition.startswith(condition)
    assert bool(found.condition) == bool(condition)


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
        # Scanning Sequence, Echo Time, and Magnetic Field Strength.
        ("MR Image", "(0018,0020)", (), {("MR Image", "1")}),
        ("MR Image", "(0018,0081)", (), {("MR Image", "2")}),
        ("MR Image", "(0018,0087)", (), {("MR Image", "3")}),
        # Series Type, and Beat Rejection Flag in the gated acquisition
        # modules, whose tables are titled "Multi-Gated".
        (
            "Positron Emission Tomography Image",
            "(0054,1000)",
            (),
            {("PET Series", "1")},
        ),
        (
            "Positron Emission Tomography Image",
            "(0018,1080)",
            (),
            {("PET Multi-gated Acquisition", "2")},
        ),
        (
            "Nuclear Medicine Image",
            "(0018,1080)",
            (),
            {("NM Multi-gated Acquisition", "3")},
        ),
        # RT Image Label, RT Image Plane, and X-Ray Image Receptor Angle.
        ("RT Image", "(3002,0002)", (), {("RT Image", "1")}),
        ("RT Image", "(3002,000C)", (), {("RT Image", "1")}),
        ("RT Image", "(3002,000E)", (), {("RT Image", "2")}),
        # Beam Name within Treatment Session Beam Sequence of the RT Beams
        # Salvage Record Module.
        (
            "RT Beams Treatment Record",
            "(300A,00C2)",
            ("(3008,0020)",),
            {("RT Beams Session Record", "3"), ("RT Beams Salvage Record", "3")},
        ),
        # Contrast/Bolus Agent Number within Contrast/Bolus Agent Sequence, in
        # the Enhanced Contrast/Bolus Module of section C.7.6.4b.
        (
            "Ophthalmic Photography 8 Bit Image",
            "(0018,9337)",
            ("(0018,0012)",),
            {("Enhanced Contrast/Bolus", "1")},
        ),
        # Implant Template Group Name and Version.
        (
            "Implant Template Group",
            "(0078,0001)",
            (),
            {("Implant Template Group", "1")},
        ),
        (
            "Implant Template Group",
            "(0078,0024)",
            (),
            {("Implant Template Group", "2")},
        ),
        # Referenced Waveform Sequence within Referenced Series Sequence.
        (
            "Waveform Presentation State",
            "(0008,113A)",
            ("(0008,1115)",),
            {("Waveform Presentation State Relationship", "1C")},
        ),
        # Histogram Number of Bins, from the table whose name column is
        # headed "Attribute name".
        (
            "Digital X-Ray Image",
            "(0060,3002)",
            ("(0060,3000)",),
            {("Image Histogram", "1")},
        ),
        # Code Value within View Modifier Code Sequence, from the Include row
        # published with a space after its ">" characters.
        (
            "Planar MPR Volumetric Presentation State",
            "(0008,0100)",
            ("(0054,0220)", "(0054,0222)"),
            {("Presentation View Description", "1C")},
        ),
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


def test_rows_nested_below_an_include_are_in_its_only_sequence(tables):
    sr = tables.iods["Comprehensive SR"]

    # The Image Reference Macro includes the Composite Object Reference Macro,
    # whose only attribute is Referenced SOP Sequence (0008,1199), and nests
    # Referenced Frame Number (0008,1160) in its items.
    (frame,) = sr.lookup("(0008,1160)", ("(0040,A730)", "(0008,1199)"))
    assert frame.type == "1C"
    assert frame.tables[-2:] == ("Table C.17-5", "Table C.18.4-1")
    assert sr.lookup("(0008,1160)", ("(0040,A730)",)) == ()


@pytest.mark.parametrize("depth", [1, 2, 3, 5])
def test_a_table_that_includes_itself_defines_items_at_any_depth(tables, depth):
    sr = tables.iods["Comprehensive SR"]
    content = ("(0040,A730)",) * depth

    # Text Value, from the Document Content Macro, which the Document
    # Relationship Macro includes in each Content Sequence item, as it
    # includes itself.
    (text_value,) = sr.lookup("(0040,A160)", content)
    assert (text_value.path, text_value.type) == (content, "1C")
    assert text_value.tables == ("Table C.17-4", "Table C.17-6", "Table C.17-5")
    assert {d.type for d in sr.lookup("(0040,A010)", content)} == {"1"}
    # No other module's attributes repeat in the items.
    assert sr.lookup("(0010,0020)", content) == ()

    # Relationship Type stays Type 1 in an encapsulated document's tree.
    pdf = tables.iods["Encapsulated PDF"]
    assert {(d.module, d.type) for d in pdf.lookup("(0040,A010)", content)} == {
        ("Encapsulated Document", "1")
    }

    # Referenced SOP Instance UID in a tree of Inventory references.
    incorporated = ("(0008,0422)",) * depth
    found = tables.iods["Inventory"].lookup("(0008,1155)", incorporated)
    assert {(d.module, d.type, d.path) for d in found} == {
        ("Inventory", "1", incorporated)
    }


def test_each_iod_is_expanded_when_its_types_are_first_needed(tmp_path):
    loaded = _load(tmp_path, *_documents())
    ct = loaded.iods["CT Image"]

    assert not any("_expansion" in vars(iod) for iod in loaded.iods.values())
    assert ct.lookup("(0010,0020)")
    assert [name for name, iod in loaded.iods.items() if "_expansion" in vars(iod)] == [
        "CT Image"
    ]
    assert ct.definitions is ct.definitions


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
        # Rows can be nested only below an Include of a table with a single
        # top-level attribute, as Table 10-18 is not, and only one level.
        (
            lambda a: _below_include(a).update(depth=1),
            "is nested below an Include of Table 10-18, which has no single "
            "top-level attribute",
        ),
        (lambda a: _below_include(a).update(depth=2), "is nested more deeply"),
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


def _include_at_end_of_table_10_18(attributes, *includes):
    """Add Include rows, each a label and depth, to the Issuer of Patient ID Macro.

    The row above them is within Issuer of Patient ID Qualifiers Sequence
    (0010,0024), the macro's last top-level attribute.
    """
    _table(attributes, "Table 10-18")["rows"].extend(
        {"depth": depth, "name": "", "tag": "", "type": "", "include": include}
        for include, depth in includes
    )


@pytest.mark.parametrize(
    "includes, message",
    [
        (
            [("Table C.7-1", 0)],
            "Table 10-18 includes itself: Table 10-18 > Table C.7-1 > Table 10-18",
        ),
        # Through another table, even below a sequence.
        (
            [("Table C.7-1", 1)],
            "Table 10-18 includes itself: Table 10-18 > Table C.7-1 > Table 10-18",
        ),
        # At the top level, it would repeat forever.
        (
            [("Table 10-18", 0)],
            "Table 10-18 includes itself: Table 10-18 > Table 10-18",
        ),
        # Below the only sequence of a macro it includes, not one of its own.
        (
            [("Table 10-8", 0), ("Table 10-18", 1)],
            "Table 10-18 includes itself: Table 10-18 > Table 10-18",
        ),
    ],
)
def test_a_cycle_of_includes_is_rejected(tmp_path, includes, message):
    modules, attributes = _documents()
    _include_at_end_of_table_10_18(attributes, *includes)

    with pytest.raises(standard.StandardTableError, match=message):
        _load(tmp_path, modules, attributes)


def test_a_table_can_include_itself_below_its_own_sequence(tmp_path):
    modules, attributes = _documents()
    _include_at_end_of_table_10_18(attributes, ("Table 10-18", 1))
    ct = _load(tmp_path, modules, attributes).iods["CT Image"]
    qualifiers = ("(0010,0024)",)

    # Issuer of Patient ID, at the top level of the macro, in the items.
    for path in (qualifiers, qualifiers * 3, ("(0010,1002)", *qualifiers * 2)):
        (issuer,) = ct.lookup("(0010,0021)", path)
        assert (issuer.module, issuer.type, issuer.path) == ("Patient", "3", path)
    # Universal Entity ID, in the macro's own sequence, one level deeper.
    assert _types(ct, "(0040,0032)", qualifiers * 2) == {("Patient", "3")}
    # Patient ID is in the Patient Module, not the macro.
    assert ct.lookup("(0010,0020)", qualifiers) == ()


def _ct(modules):
    return next(iod for iod in modules["rows"] if iod["iod"] == "CT Image")


def _ct_modules(modules):
    return _ct(modules)["modules"]


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
        (lambda m: _ct(m).update(modules=[]), "has no modules"),
        (lambda m: _ct(m).update(iod=""), "has no IOD name"),
        (lambda m: _ct(m).update(label=3), "without a table label"),
        (lambda m: _ct(m).pop("iod"), "without exactly the fields"),
        (lambda m: m["rows"].append(copy.deepcopy(_ct(m))), "CT Image more than"),
    ],
)
def test_malformed_iod_modules_are_rejected(tmp_path, change, message):
    modules, attributes = _documents()
    change(modules)

    with pytest.raises(standard.StandardTableError, match=message):
        _load(tmp_path, modules, attributes)
