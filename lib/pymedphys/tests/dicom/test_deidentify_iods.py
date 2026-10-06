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

# The tests of modules and of Functional Group Macros alter the same generated
# files with the same helpers, so they stay in one module.
# pylint: disable = too-many-lines

import copy
import json
import re

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


@pytest.mark.deid_requirement("MIDI-BP-03")
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


def test_every_composite_iod_but_the_real_time_ones_is_generated(tables):
    # Counted from the published 2026d PS3.3: 174 IOD Modules tables in Annex
    # A, three of them for real-time IODs whose module gives an attribute that
    # PS3.6 defines in Table 9-1, outside the data dictionary.
    assert len(tables.iods) == 171
    assert len(tables.attribute_tables) == 664
    assert all(iod.label.startswith("Table A.") for iod in tables.iods.values())
    assert "Real-Time Audio Waveform" not in tables.iods
    # Including the IODs whose modules include Functional Group Macros.
    assert sum(bool(iod.functional_group_macros) for iod in tables.iods.values()) == 30
    assert tables.iods["Segmentation"].label == "Table A.51-1"
    assert tables.iods["Enhanced CT Image"].label == "Table A.38-1"


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


@pytest.mark.deid_requirement("MIDI-BP-03")
def test_an_attribute_can_have_a_different_type_in_each_module(tables):
    # Image Type is Type 3 in the General Image Module and Type 1 in the CT
    # Image Module, which specialises it.
    assert _types(tables.iods["CT Image"], "(0008,0008)") == {
        ("General Image", "3"),
        ("CT Image", "1"),
    }


@pytest.mark.deid_requirement("MIDI-BP-03")
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


@pytest.mark.deid_requirement("MIDI-BP-03")
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
    definitions = ct.definitions
    assert ct.definitions is definitions


def test_an_iods_attribute_tables_cannot_be_changed(tables):
    ct = tables.iods["CT Image"]
    macro = ct.attribute_tables["Table 10-18"]

    # They are shared by every IOD of the cached tables.
    with pytest.raises(TypeError):
        ct.attribute_tables["Table C.7-1"] = macro  # type: ignore[index]
    assert ct.attribute_tables is tables.attribute_tables


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


# The Shared and Per-Frame Functional Groups Sequences (5200,9229) and
# (5200,9230) of the Multi-frame Functional Groups Module, whose items each
# include the IOD's Functional Group Macros (PS3.3 C.7.6.16).
SHARED = ("(5200,9229)",)
PER_FRAME = ("(5200,9230)",)


def _group_types(iod, tag, path):
    return {
        (definition.functional_group, definition.type)
        for definition in iod.lookup(tag, path)
    }


@pytest.mark.deid_requirement("MIDI-BP-03")
@pytest.mark.parametrize("groups", [SHARED, PER_FRAME])
@pytest.mark.parametrize(
    "iod, tag, path, expected",
    [
        # Pixel Measures Sequence, and Pixel Spacing within it (Table
        # C.7.6.16-2); Frame Content Sequence (Table C.7.6.16-3); Plane
        # Position Sequence, and Image Position (Patient) within it (Table
        # C.7.6.16-4).
        ("Enhanced CT Image", "(0028,9110)", (), {("Pixel Measures", "1")}),
        (
            "Enhanced CT Image",
            "(0028,0030)",
            ("(0028,9110)",),
            {("Pixel Measures", "1C")},
        ),
        ("Enhanced CT Image", "(0020,9111)", (), {("Frame Content", "1")}),
        (
            "Enhanced CT Image",
            "(0020,9113)",
            (),
            {("Plane Position (Patient)", "1")},
        ),
        (
            "Enhanced CT Image",
            "(0020,0032)",
            ("(0020,9113)",),
            {("Plane Position (Patient)", "1C")},
        ),
        # Frame Type within CT Image Frame Type Sequence (Table C.8-114).
        (
            "Enhanced CT Image",
            "(0008,9007)",
            ("(0018,9329)",),
            {("CT Image Frame Type", "1")},
        ),
        ("Segmentation", "(0028,9110)", (), {("Pixel Measures", "1")}),
        (
            "Segmentation",
            "(0028,0030)",
            ("(0028,9110)",),
            {("Pixel Measures", "1C")},
        ),
        ("Segmentation", "(0020,9113)", (), {("Plane Position (Patient)", "1")}),
        # Referenced Segment Number within Segment Identification Sequence
        # (Table C.8.20-3).
        (
            "Segmentation",
            "(0062,000B)",
            ("(0062,000A)",),
            {("Segmentation", "1")},
        ),
        # The source images within Derivation Image Sequence (Table
        # C.7.6.16-7), whose references come from the Image SOP Instance
        # Reference Macro.
        ("Segmentation", "(0008,9124)", (), {("Derivation Image", "2")}),
        (
            "Segmentation",
            "(0008,1155)",
            ("(0008,9124)", "(0008,2112)"),
            {("Derivation Image", "1")},
        ),
    ],
)
def test_functional_group_macros_are_expanded_in_each_functional_group_sequence(
    tables, groups, iod, tag, path, expected
):
    found = tables.iods[iod].lookup(tag, (*groups, *path))

    assert {(d.functional_group, d.type) for d in found} == expected
    assert {d.module for d in found} == {"Multi-frame Functional Groups"}
    assert all(d.tables[0] == "Table C.7.6.16-1" for d in found)


def test_attributes_of_functional_group_macros_are_only_in_their_items(tables):
    ct = tables.iods["Enhanced CT Image"]

    # Pixel Spacing is defined only within Pixel Measures Sequence, and the
    # macros' sequences only in the items of the Functional Groups Sequences.
    assert ct.lookup("(0028,0030)") == ()
    assert ct.lookup("(0028,9110)") == ()
    assert ct.lookup("(0028,0030)", SHARED) == ()
    # The module's other attributes are outside any functional group.
    (frames,) = ct.lookup("(0028,0008)")
    assert (frames.module, frames.functional_group, frames.type) == (
        "Multi-frame Functional Groups",
        "",
        "1",
    )
    # Each IOD with Functional Group Macros has the module's two sequences.
    assert _types(ct, "(5200,9229)") == {("Multi-frame Functional Groups", "1")}
    assert _types(ct, "(5200,9230)") == {("Multi-frame Functional Groups", "1C")}


def _macros(iod):
    return {
        macro.macro: (macro.usage, macro.condition)
        for macro in iod.functional_group_macros
    }


def test_each_functional_group_macro_has_its_usage_and_condition(tables):
    # From Tables A.38-2 and A.51-2.
    ct = _macros(tables.iods["Enhanced CT Image"])
    segmentation = _macros(tables.iods["Segmentation"])

    assert len(ct) == 29
    assert ct["Pixel Measures"] == ("M", "")
    assert ct["Frame VOI LUT"] == ("U", "")
    assert ct["Frame Content"] == (
        "M",
        "May not be used as a Shared Functional Group.",
    )
    assert ct["Cardiac Synchronization"][0] == "C"
    assert ct["Cardiac Synchronization"][1].startswith(
        "Required if Cardiac Synchronization Technique (0018,9037)"
    )
    assert list(segmentation) == [
        "Pixel Measures",
        "Plane Position (Patient)",
        "Plane Orientation (Patient)",
        "Plane Position (Slide)",
        "Derivation Image",
        "Frame Content",
        "Segmentation",
    ]
    assert {usage for usage, _ in segmentation.values()} == {"C"}
    assert segmentation["Segmentation"][1] == (
        "Required if Dimension Organization Type (0020,9311) is not TILED_FULL "
        "and Segmentation Type (0062,0001) is not LABELMAP."
    )
    (macro,) = [
        macro
        for macro in tables.iods["Segmentation"].functional_group_macros
        if macro.macro == "Pixel Measures"
    ]
    assert macro == iods.FunctionalGroupMacro(
        "Pixel Measures",
        "C.7.6.16.2.1",
        "C",
        macro.condition,
        "Table C.7.6.16-2",
    )
    assert macro.condition.startswith(
        "Required if Derivation Image Functional Group (C.7.6.16.2.6) is not present"
    )


def test_a_definition_names_its_macro_so_its_usage_can_be_found(tables):
    segmentation = tables.iods["Segmentation"]
    usage = {macro.macro: macro.usage for macro in segmentation.functional_group_macros}

    # Referenced Segment Number is Type 1 wherever its conditional macro is.
    (number,) = segmentation.lookup("(0062,000B)", (*PER_FRAME, "(0062,000A)"))
    assert (number.type, usage[number.functional_group]) == ("1", "C")
    # An attribute outside every macro names none.
    (series,) = segmentation.lookup("(0020,000E)")
    assert series.functional_group == ""


@pytest.mark.parametrize(
    "iod, sequences",
    [
        ("Enhanced CT Image", {SHARED, PER_FRAME}),
        ("Segmentation", {SHARED, PER_FRAME}),
        # The Sparse Multi-frame Functional Groups Module's Shared Functional
        # Groups Sequence and Selected Frame Functional Groups Sequence.
        ("Enhanced Continuous RT Image", {SHARED, ("(3002,0101)",)}),
    ],
)
def test_each_macro_is_in_every_sequence_that_includes_the_macros(
    tables, iod, sequences
):
    found = tables.iods[iod]

    assert found.functional_group_macros
    for macro in found.functional_group_macros:
        # The macro's only top-level attribute, its Functional Group Sequence,
        # is in the items of each sequence that includes the macros.
        paths = {
            definition.path
            for definition in found.definitions
            if definition.tables[1:] == (macro.table,)
            and definition.functional_group == macro.macro
            and len(definition.path) == 1
        }
        assert paths == sequences, macro.macro


def test_an_iod_can_have_the_functional_group_macros_of_another(tables):
    # Section A.36.4.4 gives the Enhanced MR Color Image IOD the macros of
    # Table A.36-2, the Enhanced MR Image IOD's.
    color = tables.iods["Enhanced MR Color Image"]

    assert color.functional_group_macros == (
        tables.iods["Enhanced MR Image"].functional_group_macros
    )
    assert _group_types(color, "(0028,9110)", PER_FRAME) == {("Pixel Measures", "1")}


@pytest.mark.parametrize(
    "iod, macro, expected",
    [
        # Published with an en dash, a hyphen without a space, or nothing,
        # between usage and condition.
        (
            "Parametric Map",
            "Plane Position (Patient)",
            ("C.7.6.16.2.3", "C", "Required if the Frame of Reference is defined"),
        ),
        (
            "Parametric Map",
            "Plane Orientation (Patient)",
            ("C.7.6.16.2.4", "C", "Required if the Frame of Reference is defined"),
        ),
        (
            "X-Ray 3D Craniofacial Image",
            "Frame Content",
            ("C.7.6.16.2.2", "M", "May not be used as a Shared Functional Group."),
        ),
        (
            "Breast Tomosynthesis Image",
            "Breast Biopsy Target",
            ("C.8.21.5.2", "U", "May not be used as a Shared Functional Group."),
        ),
        (
            "Enhanced RT Image",
            "RT Image Frame General Content",
            ("C.36.2.4.8", "M", "The units for Start Cumulative Meterset"),
        ),
        (
            "Enhanced Continuous RT Image",
            "RT Image Frame General Content",
            ("C.36.2.4.8", "M", "The units for Start Cumulative Meterset"),
        ),
        # Its table is titled "Frame VOI LUT with LUT Macro Attributes".
        (
            "Breast Projection X-Ray Image",
            "Frame VOI LUT With LUT",
            ("C.7.6.16.2.10b", "M", ""),
        ),
    ],
)
def test_functional_group_macros_whose_published_rows_are_corrected(
    tables, iod, macro, expected
):
    (found,) = [m for m in tables.iods[iod].functional_group_macros if m.macro == macro]
    section, usage, condition = expected

    assert (found.section, found.usage) == (section, usage)
    assert found.condition.startswith(condition)
    assert bool(found.condition) == bool(condition)


def test_the_x_ray_grid_description_is_in_its_functional_group_sequence(tables):
    # Table C.8.31.7-1 publishes its Include of the X-Ray Grid Description
    # Macro at the top level, so that the macro would have attributes outside
    # its sequence; the pin nests it in X-Ray Grid Sequence (0018,9555), as
    # the X-Ray Filter Macro nests its description in its sequence.
    breast = tables.iods["Breast Projection X-Ray Image"]

    # Grid Absorbing Material.
    assert _group_types(breast, "(0018,7040)", (*PER_FRAME, "(0018,9555)")) == {
        ("X-Ray Grid", "3")
    }
    assert breast.lookup("(0018,7040)", PER_FRAME) == ()


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


def _iod_entry(modules, name):
    return next(iod for iod in modules["rows"] if iod["iod"] == name)


def _segmentation_macros(modules):
    return _iod_entry(modules, "Segmentation")["functional_group_macros"]


@pytest.mark.parametrize(
    "change, message",
    [
        # Types would be incomplete without the macros, or the macros unused.
        (
            lambda m: _iod_entry(m, "Segmentation").pop("functional_group_macros"),
            "Table A.51-1 has a module that includes Functional Group Macros, "
            "but lists none",
        ),
        (
            lambda m: _ct(m).update(
                functional_group_macros=copy.deepcopy(_segmentation_macros(m))
            ),
            "Table A.3-1 lists Functional Group Macros, but no module includes them",
        ),
        (
            lambda m: _segmentation_macros(m)[0].update(usage="R"),
            "Table A.51-1 functional group macro 1 has a usage other than M, C, or U",
        ),
        (
            lambda m: _segmentation_macros(m)[0].update(table="Table 99-99"),
            "macro 1 refers to Table 99-99, which is not in the attribute tables",
        ),
        (
            lambda m: _segmentation_macros(m)[0].update(condition=None),
            "macro 1 has a field that is not text, or is empty",
        ),
        (
            lambda m: _segmentation_macros(m)[0].update(macro=""),
            "macro 1 has a field that is not text, or is empty",
        ),
        (
            lambda m: _segmentation_macros(m)[0].pop("section"),
            "functional group macro 1 has a macro without exactly the fields",
        ),
        (
            lambda m: _segmentation_macros(m).append(_segmentation_macros(m)[0]),
            "Table A.51-1 lists a Functional Group Macro more than once",
        ),
        # Each Functional Group is one sequence (PS3.3 C.7.6.16.1.1), and
        # contains no other Functional Groups.
        (
            lambda m: _segmentation_macros(m)[0].update(table="Table 10-18"),
            "macro 1 has Table 10-18, which does not define exactly one "
            "top-level attribute",
        ),
        (
            lambda m: _segmentation_macros(m)[0].update(table="Table C.7.6.16-1"),
            "macro 1 has Table C.7.6.16-1, which includes Functional Group Macros",
        ),
        # Only an IOD with macros lists them.
        (
            lambda m: _segmentation_macros(m).clear(),
            "Table A.51-1 has Functional Group Macros that are not a non-empty list",
        ),
        (
            lambda m: _ct(m).update(functional_group_macros=None),
            "Table A.3-1 has Functional Group Macros that are not a non-empty list",
        ),
        (
            lambda m: _ct(m).update(groups=[]),
            "has an IOD without exactly the fields iod, label, modules, and "
            "optionally functional_group_macros",
        ),
    ],
)
def test_malformed_functional_group_macros_are_rejected(tmp_path, change, message):
    modules, attributes = _documents()
    change(modules)

    with pytest.raises(standard.StandardTableError, match=re.escape(message)):
        _load(tmp_path, modules, attributes)


def _multi_frame_rows(attributes):
    return _table(attributes, "Table C.7.6.16-1")["rows"]


@pytest.mark.parametrize(
    "change, message",
    [
        # Rows cannot extend the items of the IOD's macros.
        (
            lambda a: _multi_frame_rows(a).insert(
                2,
                {
                    "depth": 2,
                    "name": "Pixel Spacing",
                    "tag": "(0028,0030)",
                    "type": "1",
                    "include": "",
                },
            ),
            "Table C.7.6.16-1 row 3 is nested below an Include of Functional Group "
            "Macros",
        ),
        (
            lambda a: _multi_frame_rows(a)[1].update(type="1"),
            "Include row with a name, tag, or Type",
        ),
        (
            lambda a: _multi_frame_rows(a)[1].update(include="Functional Groups"),
            "includes something that is not a table label",
        ),
    ],
)
def test_malformed_includes_of_functional_group_macros_are_rejected(
    tmp_path, change, message
):
    modules, attributes = _documents()
    change(attributes)

    with pytest.raises(standard.StandardTableError, match=re.escape(message)):
        _load(tmp_path, modules, attributes)


def _include_row(depth, include):
    return {"depth": depth, "name": "", "tag": "", "type": "", "include": include}


def test_functional_group_macros_are_expanded_where_any_table_includes_them(
    tmp_path,
):
    # A module can include the macros through a table it includes, rather
    # than in its own rows, as an edition could publish them.
    modules, attributes = _documents()
    shared = _multi_frame_rows(attributes)
    shared[1] = _include_row(1, "Table 99-1")
    attributes["rows"].append(
        {
            "label": "Table 99-1",
            "title": "Fixture Functional Groups Macro Attributes",
            "rows": [_include_row(0, iods.FUNCTIONAL_GROUP_MACROS)],
        }
    )
    ct = _load(tmp_path, modules, attributes).iods["Enhanced CT Image"]

    (measures,) = ct.lookup("(0028,9110)", SHARED)
    assert (measures.functional_group, measures.type) == ("Pixel Measures", "1")
    assert measures.tables == ("Table C.7.6.16-1", "Table 99-1", "Table C.7.6.16-2")


def test_an_iod_that_includes_functional_group_macros_through_a_table_lists_them(
    tmp_path,
):
    modules, attributes = _documents()
    # Every IOD with the Patient Module would then reach the macros.
    _patient_rows(attributes).append(_include_row(0, "Table C.7.6.16-1"))

    with pytest.raises(
        standard.StandardTableError,
        match="has a module that includes Functional Group Macros, but lists none",
    ):
        _load(tmp_path, modules, attributes)
