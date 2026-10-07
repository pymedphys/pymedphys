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

"""The values that the Z and D actions write."""

import datetime
import io

from pymedphys._imports import hypothesis, pydicom, pytest

from pymedphys._dicom.deidentify import (
    dummy_values,
    icc_profiles,
    keys,
    standard,
    uid_registry,
    uids,
    values,
)

st = hypothesis.strategies

KEY = keys.DeidKey(bytes(range(32)))
TEXT_VRS = ["LO", "SH", "LT", "ST", "UC", "UT", "PN"]
# Each VR's constant, as the design document lists them, and the second
# constant that replaces a source value equal to the first.
CONSTANTS = {
    **{vr: ("DEIDENTIFIED", "DE-IDENTIFIED") for vr in TEXT_VRS},
    "DA": ("19000101", "19000102"),
    "TM": ("000000", "000001"),
    "DT": ("19000101000000", "19000101000001"),
    "DS": ("0", "1"),
    "IS": ("0", "1"),
    "FL": (0.0, 1.0),
    "FD": (0.0, 1.0),
    **{vr: (0, 1) for vr in ["SL", "SS", "SV", "UL", "US", "UV"]},
}
# Invented source values that differ from each VR's constant.
SOURCES = {
    **{vr: ["Fixture value", "deidentified copy", "DE-IDENTIFIED"] for vr in TEXT_VRS},
    "PN": ["Fixture^Patient", "DEIDENTIFIED^CODE", "^DEIDENTIFIED"],
    "DA": ["20240229", "19000102", "1900.01.02"],
    "TM": ["093000", "000000.5", "000001"],
    "DT": ["20240229093000+1000", "19000101000000.000001", "190001010001"],
    "DS": ["2.5", "0.001", "-1e-9"],
    "IS": ["7", "-1", "1"],
    "FL": [2.5, -1.0, 1e-30],
    "FD": [2.5, -1.0, 5e-324],
    **{vr: [7, 1] for vr in ["SL", "SS", "SV", "UL", "US", "UV"]},
}
# The attributes of Table E.1-1 in 2026d that can take D but have a VR without
# a generic dummy value, so each needs a reviewed rule.
WITHOUT_GENERIC_DUMMY_VALUES = {
    "CertificateOfSigner",
    "ContentSequence",
    "DestinationAE",
    "EncapsulatedDocument",
    "FlowIdentifier",
    "FlowIdentifierSequence",
    "FrameOriginTimestamp",
    "GraphicAnnotationSequence",
    "InstitutionCodeSequence",
    "OperatorIdentificationSequence",
    "PersonIdentificationCodeSequence",
    "ReasonForTheAttributeModification",
    "ReferencedPerformedProcedureStepSequence",
    "SelectorAEValue",
    "SelectorASValue",
    "SelectorOBValue",
    "SelectorUNValue",
    "SelectorURValue",
    "SourceIdentifier",
    "VerifyingObserverSequence",
    "WaveformAnnotationSequence",
}


def _attributes_that_can_take_d():
    """Return the dictionary entry of each attribute that Table E.1-1 can give D."""
    dictionary = {row.tag: row for row in standard.load_data_dictionary().attributes}
    return [
        dictionary[row.tag]
        for row in standard.load_table_e1_1().attributes
        if any(
            "D" in action.split("/")
            for action in [row.basic_profile, *row.options.values()]
        )
    ]


def _source_for(vr):
    if vr == "UI":
        return ["1.2.840.99999.4.5"]
    return SOURCES.get(vr, ["FIXTURE"])[:1]


@pytest.mark.deid_requirement("PS3.15-E.1.1-01")
@pytest.mark.usefixtures("pydicom_behaviour")
@pytest.mark.parametrize("vr", sorted(standard.VRS))
def test_z_writes_a_zero_length_value(vr):
    written = dummy_values.values_for_z(vr)

    assert isinstance(written, tuple)
    assert not written
    if vr != "SQ":
        assert values.values_problem(vr, "1", written) is None
    dataset = pydicom.Dataset()
    dataset.add_new(0x00091010, vr, list(written))
    buffer = io.BytesIO()
    pydicom.dcmwrite(buffer, dataset, implicit_vr=False, little_endian=True)
    # The element's explicit VR header is 8 or 12 bytes, so no value follows.
    assert len(buffer.getvalue()) <= 12
    buffer.seek(0)
    assert pydicom.dcmread(buffer, force=True)[0x00091010].is_empty


@pytest.mark.deid_requirement("PS3.15-E.1.1-01")
@pytest.mark.parametrize("vr", sorted(CONSTANTS))
def test_d_writes_its_vrs_constant(vr):
    first, _ = CONSTANTS[vr]

    for source in SOURCES[vr]:
        assert dummy_values.values_for_d(vr, "1", [source], KEY) == (first,)
    assert dummy_values.values_for_d(vr, "1", [], KEY) == (first,)


@pytest.mark.deid_requirement("PS3.15-E.1.1-01")
@pytest.mark.parametrize(
    "vr, source",
    [
        ("LO", "DEIDENTIFIED"),
        ("LO", " deidentified "),
        ("SH", "DEIDENTIFIED\x00"),
        ("UT", "Deidentified"),
        ("PN", "DEIDENTIFIED"),
        ("PN", "DEIDENTIFIED^^^^"),
        ("PN", "deidentified^=^ "),
        ("DA", "19000101"),
        ("DA", "19000101 "),
        ("DA", "1900.01.01"),
        ("TM", "000000"),
        ("TM", "00"),
        ("TM", "0000 "),
        ("TM", "000000.000000"),
        ("TM", "00:00:00"),
        ("DT", "19000101000000"),
        ("DT", "1900"),
        ("DT", "19000101"),
        ("DT", "19000101000000.0+1000"),
        ("DT", "190001-0500"),
        ("DS", "0"),
        ("DS", "0.0"),
        ("DS", " -0 "),
        ("DS", "0e5"),
        ("IS", "+0"),
        ("IS", "000"),
        ("FL", 0.0),
        ("FD", -0.0),
        ("FD", 0),
        ("US", 0),
        ("SV", 0),
    ],
)
def test_d_writes_the_second_constant_where_the_source_equals_the_first(vr, source):
    _, second = CONSTANTS[vr]

    assert dummy_values.values_for_d(vr, "1", [source], KEY) == (second,)


def test_any_source_value_equal_to_the_constant_gives_the_second_constant():
    # The value written differs from the source's.
    assert dummy_values.values_for_d("LO", "1-n", ["Other", "DEIDENTIFIED"], KEY) == (
        "DE-IDENTIFIED",
    )
    assert dummy_values.values_for_d("DS", "1-n", ["2.5", "0.00"], KEY) == ("1",)


@pytest.mark.parametrize("vr", sorted(CONSTANTS))
def test_the_constants_are_valid_conspicuous_and_different(vr):
    first, second = CONSTANTS[vr]

    assert values.value_problem(vr, first) is None
    assert values.value_problem(vr, second) is None
    assert dummy_values.values_for_d(vr, "1", [second], KEY) == (first,)
    assert dummy_values.values_for_d(vr, "1", [first], KEY) == (second,)
    # The de-identification markers name PyMedPhys; dummy values never do.
    assert "pymedphys" not in f"{first}{second}".casefold()


def test_the_vrs_with_a_generic_dummy_value_are_those_the_design_lists():
    assert dummy_values.DUMMY_VRS == {*CONSTANTS, "UI"}
    assert dict(dummy_values.CONSTANTS) == CONSTANTS


@pytest.mark.deid_requirement("PS3.15-E.1.1-01")
@hypothesis.given(
    st.sampled_from(TEXT_VRS),
    st.lists(
        st.text().filter(lambda value: "deidentified" not in value.casefold()),
        min_size=2,
        max_size=2,
        unique=True,
    ),
)
def test_different_source_values_give_the_same_dummy_value(vr, sources):
    first, second = sources

    assert (
        dummy_values.values_for_d(vr, "1", [first], KEY)
        == dummy_values.values_for_d(vr, "1", [second], KEY)
        == ("DEIDENTIFIED",)
    )


@pytest.mark.deid_requirement("MIDI-BP-03")
def test_every_dummy_value_is_valid_for_its_vr_and_the_attributes_vm():
    problems = {}
    for attribute in _attributes_that_can_take_d():
        for vr in attribute.vrs:
            if vr not in dummy_values.DUMMY_VRS:
                continue
            # A source value that differs from the constant, and one equal to it.
            sources = [_source_for(vr)]
            if vr in CONSTANTS:
                sources.append([CONSTANTS[vr][0]])
            for source in sources:
                written = dummy_values.values_for_d(vr, attribute.vm, source, KEY)
                problem = values.values_problem(vr, attribute.vm, written)
                if problem:
                    problems[attribute.keyword] = problem

    assert not problems


@pytest.mark.parametrize(
    "vr, vm, written",
    [
        ("DS", "3", ("0", "0", "0")),
        ("FD", "2-2n", (0.0, 0.0)),
        ("US", "2-n", (0, 0)),
        ("IS", "4-5", ("0",) * 4),
        ("FL", "16", (0.0,) * 16),
        ("LO", "1-n or 1", ("DEIDENTIFIED",)),
        ("LO", "1-n", ("DEIDENTIFIED",)),
    ],
)
def test_d_writes_the_fewest_values_the_vm_allows(vr, vm, written):
    source = ["7"] if isinstance(written[0], str) else [7]
    assert dummy_values.values_for_d(vr, vm, source, KEY) == written
    assert values.values_problem(vr, vm, written) is None


@pytest.mark.deid_requirement("PS3.15-E.1.1-01")
def test_ui_takes_the_keyed_replacement():
    source = ["1.2.840.99999.4.5", "1.2.840.99999.4.6\x00"]

    assert dummy_values.values_for_d("UI", "1-n", source, KEY) == tuple(
        uids.replacement_uid(KEY, uid) for uid in source
    )
    other_key = keys.DeidKey(bytes(32))
    assert dummy_values.values_for_d(
        "UI", "1", source[:1], other_key
    ) != dummy_values.values_for_d("UI", "1", source[:1], KEY)


@pytest.mark.parametrize("source", [[], [""], ["\x00"], ["1.2.3", " "]])
def test_ui_without_a_source_uid_has_no_dummy_value(source):
    with pytest.raises(dummy_values.NoDummyValueError) as raised:
        dummy_values.values_for_d("UI", "1-n", source, KEY)

    assert raised.value.vr == "UI"


@pytest.mark.deid_requirement("PS3.15-E.1.1-01")
@pytest.mark.parametrize("vr", sorted(standard.VRS - set(CONSTANTS) - {"UI"}))
def test_a_vr_without_a_generic_dummy_value_is_refused(vr):
    with pytest.raises(dummy_values.NoDummyValueError) as raised:
        dummy_values.values_for_d(vr, "1", ["SECRET"], KEY)

    assert raised.value.vr == vr
    assert f"VR {vr}" in str(raised.value)
    assert "SECRET" not in str(raised.value)


def test_a_refusal_is_not_an_invalid_argument():
    # A handler for invalid arguments must not catch a refusal by accident.
    assert not issubclass(dummy_values.NoDummyValueError, ValueError)
    assert not issubclass(dummy_values.NoDummyValueError, TypeError)


@pytest.mark.deid_requirement("MIDI-BP-03")
def test_table_e1_1_attributes_without_a_generic_dummy_value_are_refused():
    refused = set()
    for attribute in _attributes_that_can_take_d():
        try:
            dummy_values.values_for_d(
                attribute.vr, attribute.vm, _source_for(attribute.vr), KEY
            )
        except dummy_values.NoDummyValueError:
            refused.add(attribute.keyword)

    assert refused == WITHOUT_GENERIC_DUMMY_VALUES


@pytest.mark.parametrize("vr", ["XX", "US or SS", "", "lo"])
def test_a_vr_that_is_not_one_of_ps3_5_is_rejected(vr):
    with pytest.raises(ValueError, match="VR"):
        dummy_values.values_for_z(vr)
    with pytest.raises(ValueError, match="VR"):
        dummy_values.values_for_d(vr, "1", [], KEY)


@pytest.mark.parametrize("vm", ["", "n", "2-3n", "0"])
def test_a_malformed_vm_is_rejected(vm):
    with pytest.raises(ValueError, match="VM"):
        dummy_values.values_for_d("LO", vm, [], KEY)


@pytest.mark.parametrize(
    "vr, value",
    [
        # Bytes would be compared and replaced as their repr, so a UID given as
        # bytes would get another replacement than the same UID given as text.
        ("UI", b"1.2.3"),
        ("LO", b"DEIDENTIFIED"),
        # A date object's text is not the DA form, so it would not be found
        # equal to the constant.
        ("DA", datetime.date(1900, 1, 1)),
        ("PN", pydicom.valuerep.PersonName("DEIDENTIFIED")),
        ("DS", 0.0),
        ("FD", "0"),
        ("US", True),
    ],
)
def test_a_source_value_of_another_type_than_values_problem_takes_is_refused(vr, value):
    with pytest.raises(TypeError, match=f"VR {vr}"):
        dummy_values.values_for_d(vr, "1", [value], KEY)


@pytest.mark.parametrize("single", ["DEIDENTIFIED", b"\x00\x01", 0])
def test_a_single_source_value_is_not_taken_as_a_sequence(single):
    with pytest.raises(TypeError, match="sequence of values"):
        dummy_values.values_for_d("LO", "1", single, KEY)


PERSON_IDENTIFICATION_CODE_SEQUENCE = "(0040,1101)"
CODE_VALUE = "(0008,0100)"
CODING_SCHEME_DESIGNATOR = "(0008,0102)"
CODE_MEANING = "(0008,0104)"
# The item that D writes in Person Identification Code Sequence, as the
# design document gives it, and the item it writes where a source item's
# Code Value or Code Meaning equals the first.
PERSON_IDENTIFICATION_ITEM = (
    (CODE_VALUE, "SH", "DEIDENTIFIED"),
    (CODING_SCHEME_DESIGNATOR, "SH", "99PYMEDPHYS"),
    (CODE_MEANING, "LO", "DEIDENTIFIED^DEIDENTIFIED"),
)
SECOND_PERSON_IDENTIFICATION_ITEM = (
    (CODE_VALUE, "SH", "DE-IDENTIFIED"),
    (CODING_SCHEME_DESIGNATOR, "SH", "99PYMEDPHYS"),
    (CODE_MEANING, "LO", "DE-IDENTIFIED^DE-IDENTIFIED"),
)


@pytest.mark.deid_requirement("PS3.15-E.1.1-01")
@pytest.mark.parametrize(
    "source",
    [
        [],
        [{}],
        [{CODE_VALUE: "Fixture123", CODE_MEANING: "Fixture^Person"}],
        [{CODE_VALUE: "DEIDENTIFIED-1", CODE_MEANING: "DEIDENTIFIED"}],
        [{CODE_VALUE: "A1"}, {CODE_MEANING: "B^C"}],
    ],
)
def test_d_on_person_identification_code_sequence_writes_one_item(source):
    assert dummy_values.items_for_d(PERSON_IDENTIFICATION_CODE_SEQUENCE, source) == (
        PERSON_IDENTIFICATION_ITEM,
    )


@pytest.mark.deid_requirement("PS3.15-E.1.1-01")
@pytest.mark.parametrize(
    "source",
    [
        [{CODE_VALUE: "DEIDENTIFIED"}],
        [{CODE_VALUE: " deidentified "}],
        [{CODE_MEANING: "DEIDENTIFIED^DEIDENTIFIED"}],
        [{CODE_MEANING: "deidentified^Deidentified^^"}],
        [{CODE_VALUE: "Fixture123"}, {CODE_VALUE: "DEIDENTIFIED\x00"}],
    ],
)
def test_d_on_person_identification_code_sequence_takes_the_second_constants(source):
    assert dummy_values.items_for_d(PERSON_IDENTIFICATION_CODE_SEQUENCE, source) == (
        SECOND_PERSON_IDENTIFICATION_ITEM,
    )
    # A source item equal to the second constants takes the first.
    second = {CODE_VALUE: "DE-IDENTIFIED", CODE_MEANING: "DE-IDENTIFIED^DE-IDENTIFIED"}
    assert dummy_values.items_for_d(PERSON_IDENTIFICATION_CODE_SEQUENCE, [second]) == (
        PERSON_IDENTIFICATION_ITEM,
    )


@pytest.mark.deid_requirement("MIDI-BP-03")
@pytest.mark.parametrize(
    "item", [PERSON_IDENTIFICATION_ITEM, SECOND_PERSON_IDENTIFICATION_ITEM]
)
def test_the_person_identification_item_is_valid_for_each_vr_and_vm(item):
    dictionary = {row.tag: row for row in standard.load_data_dictionary().attributes}

    for tag, vr, value in item:
        assert dictionary[tag].vrs == (vr,)
        assert values.values_problem(vr, dictionary[tag].vm, (value,)) is None
    meaning = item[-1][-1]
    # The Person Identification Macro (PS3.3 Table 10-1) lets Code Meaning
    # follow the rules of PN, but not as a single component.
    assert values.value_problem("PN", meaning) is None
    assert meaning.count("^") == 1
    # The designator names who defines the code; the other values never name
    # PyMedPhys.
    assert item[1][-1].startswith("99")
    assert "pymedphys" not in f"{item[0][-1]}{item[2][-1]}".casefold()


@pytest.mark.usefixtures("pydicom_behaviour")
def test_the_person_identification_item_is_written_as_dicom():
    (item,) = dummy_values.items_for_d(PERSON_IDENTIFICATION_CODE_SEQUENCE, [])
    dataset = pydicom.Dataset()
    code = pydicom.Dataset()
    for tag, vr, value in item:
        code.add_new(int(tag[1:5] + tag[6:10], 16), vr, value)
    dataset.PersonIdentificationCodeSequence = [code]
    buffer = io.BytesIO()
    pydicom.dcmwrite(buffer, dataset, implicit_vr=False, little_endian=True)
    buffer.seek(0)
    read = pydicom.dcmread(buffer, force=True).PersonIdentificationCodeSequence

    assert len(read) == 1
    assert read[0].CodeValue == "DEIDENTIFIED"
    assert read[0].CodingSchemeDesignator == "99PYMEDPHYS"
    assert read[0].CodeMeaning == "DEIDENTIFIED^DEIDENTIFIED"


@pytest.mark.deid_requirement("PS3.15-E.1.1-01")
def test_d_on_any_other_sequence_is_refused():
    sequences = [
        attribute
        for attribute in _attributes_that_can_take_d()
        if attribute.vr == "SQ"
        and attribute.tag
        not in {
            PERSON_IDENTIFICATION_CODE_SEQUENCE,
            dummy_values.REFERENCED_PERFORMED_PROCEDURE_STEP_SEQUENCE,
        }
    ]

    assert {attribute.keyword for attribute in sequences} >= {
        "ContentSequence",
        "VerifyingObserverSequence",
        "OperatorIdentificationSequence",
    }
    for attribute in sequences:
        with pytest.raises(dummy_values.NoDummyValueError) as raised:
            dummy_values.items_for_d(attribute.tag, [{CODE_VALUE: "SECRET"}], KEY)
        assert raised.value.vr == "SQ"
        assert "SECRET" not in str(raised.value)
    # D's generic dummy values still refuse SQ, the two sequences with reviewed
    # items among them.
    with pytest.raises(dummy_values.NoDummyValueError):
        dummy_values.values_for_d("SQ", "1", [], KEY)


@pytest.mark.parametrize(
    "tag", ["(0040,1101", "(0040,a073)", "", None, 0x00401101, ("(0040,1101)",)]
)
def test_a_malformed_sequence_tag_is_rejected(tag):
    with pytest.raises(ValueError, match="tag"):
        dummy_values.items_for_d(tag, [])


@pytest.mark.parametrize(
    "source",
    [
        {CODE_VALUE: "A1"},
        "DEIDENTIFIED",
        [{CODE_VALUE: b"DEIDENTIFIED"}],
        [{CODE_MEANING: pydicom.valuerep.PersonName("DEIDENTIFIED^DEIDENTIFIED")}],
        ["DEIDENTIFIED"],
    ],
)
def test_a_source_item_of_another_form_is_refused(source):
    with pytest.raises(TypeError, match="source"):
        dummy_values.items_for_d(PERSON_IDENTIFICATION_CODE_SEQUENCE, source)


PROCEDURE_STEP_SEQUENCE = dummy_values.REFERENCED_PERFORMED_PROCEDURE_STEP_SEQUENCE
REFERENCED_SOP_CLASS_UID = "(0008,1150)"
REFERENCED_SOP_INSTANCE_UID = "(0008,1155)"
# Invented UIDs of performed procedure steps.
PROCEDURE_STEPS = ["1.2.826.0.1.3680043.10.1.1", "1.2.826.0.1.3680043.10.1.2"]


@pytest.mark.deid_requirement("PS3.15-E.1.1-01")
@pytest.mark.parametrize("count", [1, 2])
def test_d_on_referenced_performed_procedure_step_sequence_replaces_each_item(count):
    source = [
        {REFERENCED_SOP_CLASS_UID: "1.2.3", REFERENCED_SOP_INSTANCE_UID: uid}
        for uid in PROCEDURE_STEPS[:count]
    ]

    items = dummy_values.items_for_d(PROCEDURE_STEP_SEQUENCE, source, KEY)

    assert items == tuple(
        (
            dummy_values.DummyElement(
                REFERENCED_SOP_CLASS_UID,
                "UI",
                dummy_values.MODALITY_PERFORMED_PROCEDURE_STEP,
            ),
            dummy_values.DummyElement(
                REFERENCED_SOP_INSTANCE_UID, "UI", uids.replacement_uid(KEY, uid)
            ),
        )
        for uid in PROCEDURE_STEPS[:count]
    )
    # The same source step gets the same replacement as every other reference
    # to it, and no source UID is written.
    assert items == dummy_values.items_for_d(PROCEDURE_STEP_SEQUENCE, source, KEY)
    written = {element.value for item in items for element in item}
    assert not written & set(PROCEDURE_STEPS)


def test_the_procedure_step_item_names_the_modality_performed_procedure_step():
    registry = {row.uid: row for row in uid_registry.load_uid_values().rows}
    row = registry[dummy_values.MODALITY_PERFORMED_PROCEDURE_STEP]

    assert (row.keyword, row.uid_type) == (
        "ModalityPerformedProcedureStep",
        "SOP Class",
    )


@pytest.mark.deid_requirement("PS3.15-E.1.1-01")
@pytest.mark.parametrize(
    "source",
    [
        [],
        [{}],
        [{REFERENCED_SOP_INSTANCE_UID: ""}],
        [{REFERENCED_SOP_INSTANCE_UID: PROCEDURE_STEPS[0]}, {}],
    ],
)
def test_a_procedure_step_sequence_without_a_uid_to_replace_is_refused(source):
    with pytest.raises(dummy_values.NoDummyValueError) as raised:
        dummy_values.items_for_d(PROCEDURE_STEP_SEQUENCE, source, KEY)

    assert raised.value.vr == "SQ"
    assert PROCEDURE_STEPS[0] not in str(raised.value)


def test_a_procedure_step_sequence_needs_the_key():
    source = [{REFERENCED_SOP_INSTANCE_UID: PROCEDURE_STEPS[0]}]

    with pytest.raises(TypeError, match="key"):
        dummy_values.items_for_d(PROCEDURE_STEP_SEQUENCE, source)


def test_a_procedure_step_uid_that_is_not_text_is_rejected():
    with pytest.raises(TypeError, match="text"):
        dummy_values.items_for_d(
            PROCEDURE_STEP_SEQUENCE, [{REFERENCED_SOP_INSTANCE_UID: 1}], KEY
        )


ICC_SOURCES = {
    icc_profiles.RGB: icc_profiles.srgb_profile("A scanner's own profile"),
    icc_profiles.GREY: icc_profiles.grey_profile("A scanner's own profile"),
}


@pytest.mark.deid_requirement("MIDI-BP-14")
@pytest.mark.parametrize(
    "colour_space, build, name",
    [
        (icc_profiles.RGB, icc_profiles.srgb_profile, "sRGB"),
        (icc_profiles.GREY, icc_profiles.grey_profile, "grey"),
    ],
)
def test_d_on_icc_profile_writes_a_fixed_profile_of_the_same_colour_space(
    colour_space, build, name
):
    source = ICC_SOURCES[colour_space]

    written = dummy_values.icc_profile_for_d(source)

    assert written == build(f"DEIDENTIFIED {name}")
    assert icc_profiles.data_colour_space(written) == colour_space
    assert b"scanner" not in written
    # A source equal to the first profile takes the second, so D always
    # changes the value.
    assert dummy_values.icc_profile_for_d(written) == build(f"DE-IDENTIFIED {name}")


@pytest.mark.deid_requirement("MIDI-BP-14")
@pytest.mark.parametrize(
    "source",
    [
        b"",
        b"not an ICC profile",
        bytes(128),
        # A CMYK profile's header.
        ICC_SOURCES[icc_profiles.RGB][:16]
        + b"CMYK"
        + ICC_SOURCES[icc_profiles.RGB][20:],
    ],
)
def test_an_icc_profile_neither_rgb_nor_grey_is_refused(source):
    with pytest.raises(dummy_values.NoDummyValueError) as raised:
        dummy_values.icc_profile_for_d(source)

    assert raised.value.vr == "OB"


@pytest.mark.parametrize("source", ["RGB ", None, [b"RGB "]])
def test_an_icc_profile_that_is_not_bytes_is_rejected(source):
    with pytest.raises(TypeError, match="bytes"):
        dummy_values.icc_profile_for_d(source)
