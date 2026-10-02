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

"""Plain actions of Table E.1-1a, resolved from the strictest PS3.3 Type."""

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import compound_actions, iods, standard

from .test_deidentify_compound_actions import (
    FIRST_RELEASE_IODS,
    INSTITUTION_NAME,
    PATIENT_ID,
    _synthetic_iod,
)

resolve_in_iod = compound_actions.resolve_in_iod
resolve_plain_in_iod = compound_actions.resolve_plain_in_iod
resolve_plain_x_in_iod = compound_actions.resolve_plain_x_in_iod
strictest_type = compound_actions.strictest_type

VERIFYING_OBSERVER_SEQUENCE = "(0040,A073)"
PERSON_IDENTIFICATION_CODE_SEQUENCE = "(0040,1101)"
RT_ACCESSORY_HOLDER_SLOT_ID = "(300A,0611)"
SERIES_DESCRIPTION = "(0008,103E)"
RESPONSIBLE_PERSON = "(0010,2297)"
RESPONSIBLE_ORGANIZATION = "(0010,2299)"
SOURCE_SERIES_INFORMATION = "(3006,004C)"
ROI_INTERPRETER_SEQUENCE = "(3006,004E)"
RT_ROI_OBSERVATIONS = "(3006,0080)"
PATIENT_SETUP = "(300A,0180)"
REFERENCED_PATIENT_SETUP_PHOTO = "(300A,078C)"
PROCEDURE_PARAMETER_DESCRIPTION = "(300A,078E)"
PATIENT_TREATMENT_PREPARATION_PROCEDURE = "(300A,0790)"
PATIENT_SETUP_PHOTO_DESCRIPTION = "(300A,0794)"
PATIENT_TREATMENT_PREPARATION = "(300A,079F)"


@pytest.fixture(name="tables", scope="module")
def _tables():
    return iods.load_iod_tables()


def test_the_plain_actions_are_those_of_table_e1_1a():
    assert compound_actions.PLAIN_ACTIONS == {"C", "D", "K", "U", "X", "Z"}
    assert (
        compound_actions.PLAIN_ACTIONS
        == standard.ACTION_CODES - compound_actions.COMPOUND_ACTIONS
    )


def test_a_plain_d_on_an_attribute_the_iod_does_not_define_there_removes_it(tables):
    ct = tables.iods["CT Image"]
    rt_plan = tables.iods["RT Plan"]

    # Note 13 after Table E.1-1a: Verifying Observer Sequence "is only
    # defined in structured report IODs and hence is described in Table
    # E.1-1 as D since it is Type 1C; if encountered in an image instance, it
    # should simply be removed (treated as X)".
    assert ct.lookup(VERIFYING_OBSERVER_SEQUENCE) == ()
    assert resolve_plain_in_iod(ct, VERIFYING_OBSERVER_SEQUENCE, (), "D") == "X"
    # Person Identification Code Sequence is not defined at the top level of
    # the RT Plan IOD, nor within Referenced Image Sequence of a CT image.
    assert rt_plan.lookup(PERSON_IDENTIFICATION_CODE_SEQUENCE) == ()
    assert (
        resolve_plain_in_iod(rt_plan, PERSON_IDENTIFICATION_CODE_SEQUENCE, (), "D")
        == "X"
    )
    assert resolve_plain_in_iod(ct, PATIENT_ID, ("(0008,1140)",), "D") == "X"


@pytest.mark.parametrize(
    "iod, tag, path, attribute_type",
    [
        # Verifying Observer Sequence is Type 1C in the SR Document General
        # Module.
        ("Comprehensive SR", VERIFYING_OBSERVER_SEQUENCE, (), "1"),
        # Person Identification Code Sequence is Type 1 in Referring
        # Physician Identification Sequence, and Type 2C in Asserter
        # Identification Sequence within RT Assertions Sequence.
        ("RT Plan", PERSON_IDENTIFICATION_CODE_SEQUENCE, ("(0008,0096)",), "1"),
        (
            "RT Plan",
            PERSON_IDENTIFICATION_CODE_SEQUENCE,
            ("(0044,0110)", "(0044,0103)"),
            "2",
        ),
    ],
)
def test_a_plain_d_on_an_attribute_the_iod_defines_there_stays_d(
    tables, iod, tag, path, attribute_type
):
    assert strictest_type(tables.iods[iod], tag, path) == attribute_type
    assert resolve_plain_in_iod(tables.iods[iod], tag, path, "D") == "D"


def test_a_plain_d_on_a_type_3_attribute_stays_d(tmp_path):
    # Only an attribute that the IOD does not define there is removed; one
    # that it defines as Type 3 keeps the table's D.
    iod = _synthetic_iod(tmp_path, ("M", "3"))

    assert resolve_plain_in_iod(iod, INSTITUTION_NAME, (), "D") == "D"


def test_a_plain_z_on_an_attribute_the_iod_does_not_define_there_empties_it(tables):
    ct = tables.iods["CT Image"]

    assert resolve_plain_in_iod(ct, VERIFYING_OBSERVER_SEQUENCE, (), "Z") == "Z"
    assert ct.lookup(RT_ACCESSORY_HOLDER_SLOT_ID) == ()
    assert resolve_plain_in_iod(ct, RT_ACCESSORY_HOLDER_SLOT_ID, (), "Z") == "Z"


@pytest.mark.parametrize("attribute_type", ["1", "1C"])
def test_a_plain_z_on_a_type_1_attribute_writes_the_dummy_value(
    tmp_path, attribute_type
):
    # Table E.1-1a lets Z write "a non-zero length value that may be a dummy
    # value and consistent with the VR", which D writes.
    iod = _synthetic_iod(tmp_path, ("M", "3"), ("C", attribute_type))
    path = ("(3006,0020)", "(3006,004D)")
    (tmp_path / "nested").mkdir()
    nested = _synthetic_iod(tmp_path / "nested", ("U", attribute_type), path=path)

    assert resolve_plain_in_iod(iod, INSTITUTION_NAME, (), "Z") == "D"
    assert resolve_plain_in_iod(nested, INSTITUTION_NAME, path, "Z") == "D"


@pytest.mark.parametrize(
    "iod, tag, path, attribute_type",
    [
        # Patient's Name is Type 2, and Consulting Physician's Name Type 3,
        # at the top level of a CT image; RT Accessory Holder Slot ID is
        # Type 2C in Patient Treatment Preparation Sequence > Patient
        # Treatment Preparation Procedure Sequence > Patient Treatment
        # Preparation Device Sequence.
        ("CT Image", "(0010,0010)", (), "2"),
        ("CT Image", "(0008,009C)", (), "3"),
        (
            "CT Image",
            RT_ACCESSORY_HOLDER_SLOT_ID,
            ("(300A,079F)", "(300A,0790)", "(300A,078F)"),
            "2",
        ),
    ],
)
def test_a_plain_z_on_a_type_2_or_3_attribute_stays_z(
    tables, iod, tag, path, attribute_type
):
    assert strictest_type(tables.iods[iod], tag, path) == attribute_type
    assert resolve_plain_in_iod(tables.iods[iod], tag, path, "Z") == "Z"


def test_a_plain_z_gives_d_only_to_rt_accessory_holder_slot_id_in_five_generated_iods(
    tables,
):
    # Table E.1-1 gives RT Accessory Holder Slot ID Z, and it is Type 1 in RT
    # Accessory Holder Slot Sequence within RT Accessory Holder Definition
    # Sequence of these IODs. No IOD of the first supported release has such
    # a place. A new edition that changes where this happens fails here.
    z = {
        attribute.tag
        for attribute in standard.load_table_e1_1().attributes
        if "Z" in (attribute.basic_profile, *attribute.options.values())
    }
    dummy = {
        (name, definition.path, definition.tag)
        for name, iod in tables.iods.items()
        for definition in iod.definitions
        if definition.tag in z
        and resolve_plain_in_iod(iod, definition.tag, definition.path, "Z") == "D"
    }

    path = ("(300A,0614)", "(300A,0610)")
    assert dummy == {
        (name, path, RT_ACCESSORY_HOLDER_SLOT_ID)
        for name in (
            "C-Arm Photon-Electron Radiation",
            "C-Arm Photon-Electron Radiation Record",
            "Robotic-Arm Radiation",
            "Robotic-Arm Radiation Record",
            "RT Patient Position Acquisition Instruction",
        )
    }
    assert not set(FIRST_RELEASE_IODS) & {name for name, _, _ in dummy}


@pytest.mark.parametrize("action", ["X", "K", "C", "U"])
@pytest.mark.parametrize(
    "iod, tag, path",
    [
        # Responsible Person is Type 2C in the Patient Module, and Series
        # Description Type 1 in Source Series Information Sequence of the RT
        # Structure Set IOD.
        ("CT Image", "(0010,2297)", ()),
        ("RT Structure Set", "(0008,103E)", ("(3006,004C)",)),
        ("CT Image", "(0008,009C)", ()),
        ("CT Image", VERIFYING_OBSERVER_SEQUENCE, ()),
    ],
)
def test_the_other_plain_actions_are_unchanged(tables, action, iod, tag, path):
    # A plain X stays X even where the attribute is Type 1 or 2C: it always
    # removes the attribute, and resolve_plain_x_in_iod says what else goes
    # with it.
    assert resolve_plain_in_iod(tables.iods[iod], tag, path, action) == action


def _removal(extent, sequence=None):
    """Return the removal of this extent, by the name of its member."""
    return compound_actions.PlainRemoval(
        compound_actions.RemovalExtent[extent], sequence
    )


# Expected removals as the arguments of _removal, so that they are built when
# a test runs.
ALONE = ("ATTRIBUTE",)
SEQUESTER = ("SEQUESTER",)
OVERLAY_GROUP = ("OVERLAY_GROUP",)


@pytest.mark.parametrize(
    "iod, tag, path",
    [
        # Consulting Physician's Name is Type 3 at the top level of a CT
        # image, and Institution Name Type 3 at the top level of an RT
        # Structure Set.
        ("CT Image", "(0008,009C)", ()),
        ("RT Structure Set", INSTITUTION_NAME, ()),
        # Verifying Observer Sequence is not defined in a CT image, nor Patient
        # ID within Referenced Image Sequence, so they count as Type 3.
        ("CT Image", VERIFYING_OBSERVER_SEQUENCE, ()),
        ("CT Image", PATIENT_ID, ("(0008,1140)",)),
    ],
)
def test_a_plain_x_on_an_optional_attribute_removes_it_alone(tables, iod, tag, path):
    assert strictest_type(tables.iods[iod], tag, path) == "3"
    assert resolve_plain_x_in_iod(tables.iods[iod], tag, path) == _removal(*ALONE)


@pytest.mark.parametrize(
    "iod, tag, path, sequence",
    [
        # Series Description is Type 1 in Source Series Information Sequence,
        # which is Type 3.
        ("RT Structure Set", SERIES_DESCRIPTION, (SOURCE_SERIES_INFORMATION,), 0),
        # Patient Setup Photo Description is Type 2 in Referenced Patient
        # Setup Photo Sequence, Type 3 within Patient Treatment Preparation
        # Sequence, so the innermost of the two Type 3 sequences goes.
        (
            "CT Image",
            PATIENT_SETUP_PHOTO_DESCRIPTION,
            (PATIENT_TREATMENT_PREPARATION, REFERENCED_PATIENT_SETUP_PHOTO),
            1,
        ),
        (
            "RT Plan",
            PATIENT_SETUP_PHOTO_DESCRIPTION,
            (
                PATIENT_SETUP,
                PATIENT_TREATMENT_PREPARATION,
                REFERENCED_PATIENT_SETUP_PHOTO,
            ),
            2,
        ),
        # Patient Treatment Preparation Procedure Parameter Description is
        # Type 2 in Patient Treatment Preparation Procedure Sequence, itself
        # Type 2, so Patient Treatment Preparation Sequence, Type 3 at the top
        # level of a CT image and within Patient Setup Sequence of an RT
        # Plan, goes; Patient Setup Sequence is Type 1.
        (
            "CT Image",
            PROCEDURE_PARAMETER_DESCRIPTION,
            (PATIENT_TREATMENT_PREPARATION, PATIENT_TREATMENT_PREPARATION_PROCEDURE),
            0,
        ),
        (
            "RT Plan",
            PROCEDURE_PARAMETER_DESCRIPTION,
            (
                PATIENT_SETUP,
                PATIENT_TREATMENT_PREPARATION,
                PATIENT_TREATMENT_PREPARATION_PROCEDURE,
            ),
            1,
        ),
    ],
)
def test_a_plain_x_on_a_required_attribute_removes_the_innermost_type_3_sequence(
    tables, iod, tag, path, sequence
):
    iod = tables.iods[iod]

    assert strictest_type(iod, tag, path) in {"1", "2"}
    assert strictest_type(iod, path[sequence], path[:sequence]) == "3"
    assert all(
        strictest_type(iod, path[inner], path[:inner]) != "3"
        for inner in range(sequence + 1, len(path))
    )
    assert resolve_plain_x_in_iod(iod, tag, path) == _removal("SEQUENCE", sequence)


@pytest.mark.parametrize(
    "sequence_types, attribute_type, expected",
    [
        # The sequences outermost first, then the attribute within them.
        (("3", "3", "3"), "1", ("SEQUENCE", 2)),
        (("3", "3", "1"), "1C", ("SEQUENCE", 1)),
        (("3", "2", "1C"), "2", ("SEQUENCE", 0)),
        (("1", "3", "2C"), "2C", ("SEQUENCE", 1)),
        (("1", "2", "1C"), "1", SEQUESTER),
        (("2C", "1", "2"), "2C", SEQUESTER),
        (("1", "1", "1"), "3", ALONE),
    ],
)
def test_a_plain_x_skips_each_enclosing_sequence_that_is_required(
    tmp_path, sequence_types, attribute_type, expected
):
    path = ("(0008,1111)", "(0008,1115)", "(0008,1140)")
    iod = _synthetic_iod(
        tmp_path, ("U", attribute_type), path=path, sequence_types=sequence_types
    )

    assert resolve_plain_x_in_iod(iod, INSTITUTION_NAME, path) == _removal(*expected)


@pytest.mark.parametrize("iod", FIRST_RELEASE_IODS)
@pytest.mark.parametrize("tag", [RESPONSIBLE_PERSON, RESPONSIBLE_ORGANIZATION])
def test_a_plain_x_on_a_required_attribute_outside_a_type_3_sequence_sequesters(
    tables, iod, tag
):
    # Responsible Person and Responsible Organization are Type 2C in the
    # Patient Module, "Required if the Patient is a non-human organism. May
    # be present otherwise.", and no sequence encloses them.
    assert strictest_type(tables.iods[iod], tag) == "2"
    assert resolve_plain_x_in_iod(tables.iods[iod], tag, ()) == _removal(*SEQUESTER)


@pytest.mark.parametrize("iod", FIRST_RELEASE_IODS)
@pytest.mark.parametrize("tag", ["(6000,3000)", "(6002,3000)", "(601E,3000)"])
def test_a_plain_x_on_overlay_data_removes_its_repeating_group(tables, iod, tag):
    # Overlay Data is Type 1 in the Overlay Plane Module, which the CT Image
    # IOD includes as user-optional, so removing the whole group leaves a
    # valid instance. The other IODs do not define it.
    expected_type = "1" if iod == "CT Image" else "3"

    assert strictest_type(tables.iods[iod], tag) == expected_type
    assert resolve_plain_x_in_iod(tables.iods[iod], tag, ()) == _removal(*OVERLAY_GROUP)


def test_overlay_data_is_type_1_only_at_the_top_level_of_a_user_optional_module(
    tables,
):
    ct = tables.iods["CT Image"]
    usage = {module.module: module.usage for module in ct.modules}

    assert {
        (d.path, d.type, d.module) for d in ct.definitions if d.tag == "(60xx,3000)"
    } == {((), "1", "Overlay Plane")}
    assert usage["Overlay Plane"] == "U"


CONDITIONAL_OVERLAY_IODS = {
    "Color Softcopy Presentation State",
    "Digital Intra-Oral X-Ray Image",
    "Digital Mammography X-Ray Image",
    "Digital X-Ray Image",
    "Grayscale Softcopy Presentation State",
    "Pseudo-Color Softcopy Presentation State",
    "Variable Modality LUT Softcopy Presentation State",
    "XA/XRF Grayscale Softcopy Presentation State",
}


def test_the_overlay_plane_module_is_conditional_only_in_the_known_iods(tables):
    # Removing an overlay's group keeps the output valid only where the
    # Overlay Plane Module is user-optional. A new edition that makes it
    # conditional or mandatory elsewhere needs a reviewed decision.
    conditional = set()
    for name, iod in tables.iods.items():
        usage = {module.module: module.usage for module in iod.modules}
        modules = {d.module for d in iod.definitions if d.tag == "(60xx,3000)"}
        if any(usage[module] != "U" for module in modules):
            conditional.add(name)

    assert conditional == CONDITIONAL_OVERLAY_IODS


@pytest.mark.parametrize("name", sorted(CONDITIONAL_OVERLAY_IODS))
def test_a_plain_x_on_overlay_data_in_a_conditional_overlay_module_sequesters(
    tables, name
):
    # Overlay Data is Type 1 at the top level of these IODs' conditional
    # Overlay Plane Module, so removing its group could leave the output
    # invalid, and no sequence encloses it.
    assert resolve_plain_x_in_iod(tables.iods[name], "(6000,3000)", ()) == _removal(
        "SEQUESTER"
    )


@pytest.mark.parametrize("tag", ["(6001,3000)", "(6020,3000)", "(5000,3000)"])
def test_a_plain_x_on_an_attribute_outside_an_overlay_group_removes_it_alone(
    tables, tag
):
    # Group 6001 is private, and groups 6020 and 5000 hold no overlay.
    assert resolve_plain_x_in_iod(tables.iods["CT Image"], tag, ()) == _removal(*ALONE)


def test_a_plain_x_on_roi_interpreter_sequence_removes_it_alone(tables):
    # ROI Interpreter Sequence is Type 1C in RT ROI Observations Sequence,
    # required only if ROI Creator Sequence is present, which Table E.1-1
    # also removes, so the condition never holds in the output.
    structure_set = tables.iods["RT Structure Set"]
    path = (RT_ROI_OBSERVATIONS,)

    assert {d.type for d in structure_set.lookup(ROI_INTERPRETER_SEQUENCE, path)} == {
        "1C"
    }
    assert resolve_plain_x_in_iod(
        structure_set, ROI_INTERPRETER_SEQUENCE, path
    ) == _removal(*ALONE)


def _basic_profile_removes(iod, tag, path, basic):
    """Return whether the Basic Profile removes an attribute at a place."""
    action = basic.get(tag)
    if action in compound_actions.COMPOUND_ACTIONS:
        return resolve_in_iod(iod, tag, path, action) == "X"
    if action in compound_actions.PLAIN_ACTIONS:
        return resolve_plain_in_iod(iod, tag, path, action) == "X"
    return False


def test_a_plain_x_on_a_required_attribute_in_the_first_release_iods(tables):
    # Each place in the first supported release's IODs where Table E.1-1
    # gives a plain X to an attribute that the IOD requires, and no sequence
    # that the Basic Profile removes encloses it, with what the plain X
    # removes there. A new edition that changes these places fails here.
    attributes = standard.load_table_e1_1().attributes
    basic = {attribute.tag: attribute.basic_profile for attribute in attributes}
    plain_x = {
        attribute.tag
        for attribute in attributes
        if "X" in (attribute.basic_profile, *attribute.options.values())
    }
    found = {}
    for name in FIRST_RELEASE_IODS:
        iod = tables.iods[name]
        for definition in iod.definitions:
            # The IOD tables give a repeating group as 60xx; take its first.
            tag = definition.tag.replace("xx", "00")
            path = definition.path
            if (
                definition.tag in plain_x
                and strictest_type(iod, tag, path) != "3"
                and not any(
                    _basic_profile_removes(iod, path[depth], path[:depth], basic)
                    for depth in range(len(path))
                )
            ):
                found[name, path, definition.tag] = resolve_plain_x_in_iod(
                    iod, tag, path
                )

    patient = {
        (name, (), tag): _removal(*SEQUESTER)
        for name in FIRST_RELEASE_IODS
        for tag in (RESPONSIBLE_PERSON, RESPONSIBLE_ORGANIZATION)
    }
    preparation = {
        (name, (*outer, PATIENT_TREATMENT_PREPARATION, inner), tag): _removal(
            "SEQUENCE", len(outer) + (inner == REFERENCED_PATIENT_SETUP_PHOTO)
        )
        for name, outer in (("CT Image", ()), ("RT Plan", (PATIENT_SETUP,)))
        for inner, tag in (
            (REFERENCED_PATIENT_SETUP_PHOTO, PATIENT_SETUP_PHOTO_DESCRIPTION),
            (PATIENT_TREATMENT_PREPARATION_PROCEDURE, PROCEDURE_PARAMETER_DESCRIPTION),
        )
    }
    assert found == {
        **patient,
        **preparation,
        (
            "RT Structure Set",
            (SOURCE_SERIES_INFORMATION,),
            SERIES_DESCRIPTION,
        ): _removal("SEQUENCE", 0),
        (
            "RT Structure Set",
            (RT_ROI_OBSERVATIONS,),
            ROI_INTERPRETER_SEQUENCE,
        ): _removal(*ALONE),
        ("CT Image", (), "(60xx,3000)"): _removal(*OVERLAY_GROUP),
    }
    # Seven attributes in all.
    assert len({tag for _, _, tag in found}) == 7


@pytest.mark.parametrize(
    "extent, sequence",
    [
        ("SEQUENCE", None),
        ("SEQUENCE", -1),
        ("SEQUENCE", True),
        ("SEQUENCE", 1.0),
        ("SEQUENCE", "0"),
        ("ATTRIBUTE", 0),
        ("OVERLAY_GROUP", 0),
        ("SEQUESTER", 0),
    ],
)
def test_a_removal_names_a_sequence_only_when_it_removes_one(extent, sequence):
    with pytest.raises(ValueError, match="sequence"):
        _removal(extent, sequence)


@pytest.mark.parametrize("extent", ["attribute", None, 0])
def test_a_removal_needs_an_extent(extent):
    with pytest.raises(ValueError, match="extent"):
        compound_actions.PlainRemoval(extent)


@pytest.mark.parametrize("action", sorted(compound_actions.COMPOUND_ACTIONS))
def test_resolve_plain_in_iod_rejects_a_compound_action(tables, action):
    with pytest.raises(ValueError, match="not a plain action"):
        resolve_plain_in_iod(tables.iods["CT Image"], PATIENT_ID, (), action)


@pytest.mark.parametrize("action", ["x", "U*", "", " D", None, ("D",)])
def test_resolve_plain_in_iod_rejects_an_unknown_action(tables, action):
    with pytest.raises(ValueError, match="not a plain action"):
        resolve_plain_in_iod(tables.iods["CT Image"], PATIENT_ID, (), action)
