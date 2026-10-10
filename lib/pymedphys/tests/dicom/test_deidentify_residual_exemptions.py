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

"""Residual text findings that a kept standard term or equipment name explains."""

import struct

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import residual_exemptions
from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.release_gate import (
    Coverage,
    Decision,
    ReasonCode,
    release_condition,
)
from pymedphys._dicom.deidentify.residual_exemptions import (
    Exemption,
    KeptValues,
    defined_terms,
    load_defined_terms,
)
from pymedphys._dicom.deidentify.residuals import SourceValue
from pymedphys._dicom.deidentify.standard import load_table_e1_1

# Invented values, distinctive enough that nothing else in a file matches them.
SCANNER = "ZARQUON SCANNERS"
HOSPITAL = "ZARQUON HOSPITAL"
TRACER = "ZARQUONIDE F18"


def _element(tag, vr, value):
    """An explicit VR little endian element with a 16-bit length."""
    group, element = divmod(tag, 0x10000)
    value = value.encode("latin-1") if isinstance(value, str) else value
    value += b" " * (len(value) % 2)
    return struct.pack("<HH2sH", group, element, vr.encode(), len(value)) + value


def _sequence(tag, *items):
    """A sequence of undefined length, with items of undefined length."""
    group, element = divmod(tag, 0x10000)
    header = struct.pack("<HH2sHI", group, element, b"SQ", 0, 0xFFFFFFFF)
    body = b"".join(
        struct.pack("<HHI", 0xFFFE, 0xE000, 0xFFFFFFFF)
        + b"".join(item)
        + struct.pack("<HHI", 0xFFFE, 0xE00D, 0)
        for item in items
    )
    return header + body + struct.pack("<HHI", 0xFFFE, 0xE0DD, 0)


def _written(*elements):
    """A written file holding ``elements``, given in the order of their tags."""
    meta = _element(0x00020010, "UI", "1.2.840.10008.1.2.1\x00")
    return bytes(128) + b"DICM" + meta + b"".join(elements)


def _code(designator, meaning, value="ZQ0001"):
    """The elements of a code item, in the order of their tags."""
    item = [_element(0x00080100, "SH", value)]
    if designator is not None:
        item.append(_element(0x00080102, "SH", designator))
    return [*item, _element(0x00080104, "LO", meaning)]


def _condition(written, *removed):
    """The release condition of ``written`` for the removed values given."""
    values = [
        SourceValue(ElementPath((), tag), vr, value) for tag, vr, value in removed
    ]
    coverage = Coverage(
        planned=frozenset(value.source for value in values), collected=tuple(values)
    )
    return release_condition(coverage, written)


def _exempted(condition):
    return [(f.location.element.tag, why) for f, why in condition.exempted]


# The pinned terms.


def test_the_terms_table_is_generated_from_the_pinned_ps3_3():
    table = load_defined_terms()

    assert table.edition == "2026d"
    assert table.acknowledgement == "DICOM PS3.3 2026d, © NEMA"


@pytest.mark.parametrize(
    "tag, terms",
    [
        # Enumerated Values in the attribute's row of the NM/PET Detector
        # Module and the PET Series Module, in 2026d.
        ("(0054,0202)", {"STEP AND SHOOT", "CONTINUOUS", "STATIONARY", "WOBBLE"}),
        ("(0018,1181)", {"PARA", "FANB", "NONE", "RING", "UNKN"}),
        # Image Type's Value 1 and Value 2, in Section C.7.6.1.1.2, which its
        # row refers to.
        ("(0008,0008)", {"ORIGINAL", "DERIVED", "PRIMARY", "SECONDARY"}),
        # A list titled with the attribute's tag, in the text of a section.
        ("(0028,2114)", {"ISO_10918_1", "ISO_15444_1"}),
    ],
)
def test_terms_come_from_rows_and_the_sections_they_refer_to(tag, terms):
    assert terms <= defined_terms()[tag]


def test_terms_outside_ps3_3_are_not_in_the_table():
    # Body Part Examined's Defined Terms are in PS3.16 Annex L, which is not
    # read; PS3.3 lists only an ophthalmic module's EYE.
    assert "CHEST" not in defined_terms()["(0018,0015)"]


def test_only_cs_attributes_have_terms():
    # Pixel Representation's Enumerated Values are numbers, of VR US.
    assert "(0028,0103)" not in defined_terms()
    assert all(tag.count("x") == 0 for tag in defined_terms())


# Standard terms.


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_a_removed_value_found_in_a_cs_term_is_released():
    written = _written(_element(0x00181181, "CS", "NONE"))
    condition = _condition(written, ("(0054,1105)", "LO", "NONE"))

    assert condition.decision is Decision.RELEASE
    assert not condition.reasons
    assert _exempted(condition) == [("(0018,1181)", Exemption.STANDARD_TERM)]
    # The finding stays in the search, for the confidential QC material.
    assert len(condition.search.findings) == 1


@pytest.mark.deid_requirement("MIDI-BP-01")
@pytest.mark.parametrize(
    "kept, removed",
    [
        # The search records the first match in an element, so one value
        # that is no term keeps the element from being exempt.
        ("NONE\\ZARQUON NONE", "NONE"),
        ("ZARQUON NONE", "NONE"),  # a CS value that is no term
        ("UNKN", "UNKN"),  # a term of Collimator Type, not of this attribute
    ],
)
def test_a_cs_value_with_a_value_that_is_no_term_goes_to_review(kept, removed):
    written = _written(_element(0x00540202, "CS", kept))
    condition = _condition(written, ("(0054,1105)", "LO", removed))

    assert condition.decision is Decision.QC_REVIEW
    assert [r.code for r in condition.reasons] == [ReasonCode.RESIDUAL_TEXT]
    assert not condition.exempted


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_a_body_part_that_holds_a_removed_description_goes_to_review():
    # D-027's example: CHEST is not one of the terms that PS3.3 lists.
    written = _written(_element(0x00180015, "CS", "CHESTABDOMEN"))
    condition = _condition(written, ("(0008,1030)", "LO", "CHEST"))

    assert condition.decision is Decision.QC_REVIEW


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_an_exemption_never_releases_a_person_name():
    written = _written(_element(0x00540202, "CS", "STEP AND SHOOT"))
    condition = _condition(written, ("(0010,0010)", "PN", "SHOOT^STEPHANIE"))

    assert condition.decision is Decision.WITHHOLD
    assert condition.reasons[0].code is ReasonCode.RESIDUAL_PERSON_NAME


# Codes of standard schemes.


@pytest.mark.deid_requirement("MIDI-BP-01")
@pytest.mark.parametrize("designator", ["SCT", "DCM", "SRT", "99SDM"])
def test_a_removed_value_in_a_code_of_a_scheme_of_table_8_1_is_released(designator):
    written = _written(
        _sequence(0x00540016, [_sequence(0x00540304, _code(designator, TRACER))])
    )
    condition = _condition(written, ("(0018,0031)", "LO", TRACER))

    assert condition.decision is Decision.RELEASE
    assert _exempted(condition) == [("(0008,0104)", Exemption.STANDARD_CODE)]


@pytest.mark.deid_requirement("MIDI-BP-01")
@pytest.mark.parametrize("designator", ["99ZARQUON", "L", "sct", None])
def test_a_removed_value_in_a_local_code_goes_to_review(designator):
    # A local procedure code's meaning can hold free text.
    written = _written(_sequence(0x00081032, _code(designator, TRACER)))
    condition = _condition(written, ("(0008,1030)", "LO", TRACER))

    assert condition.decision is Decision.QC_REVIEW
    assert not condition.exempted


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_a_removed_designator_found_in_a_kept_designator_is_released_if_standard():
    standard = _written(_sequence(0x00081032, _code("SNM3", "Fixture")))
    local = _written(_sequence(0x00081032, _code("99ZQ", "Fixture")))

    assert _exempted(_condition(standard, ("(0019,1001)", "SH", "SNM3"))) == [
        ("(0008,0102)", Exemption.STANDARD_CODE)
    ]
    assert _condition(local, ("(0019,1001)", "SH", "99ZQ")).decision is (
        Decision.QC_REVIEW
    )


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_a_code_element_outside_an_item_goes_to_review():
    written = _written(
        _element(0x00080102, "SH", "SCT"), _element(0x00080104, "LO", TRACER)
    )
    condition = _condition(written, ("(0018,0031)", "LO", TRACER))

    assert condition.decision is Decision.QC_REVIEW


# Equipment names.


@pytest.mark.deid_requirement("MIDI-BP-01")
@pytest.mark.parametrize(
    "source", ["(0009,1012)", "(0018,1016)", "(0018,1018)", "(0018,1019)"]
)
@pytest.mark.parametrize("kept", [0x00080070, 0x00081090, 0x00181020])
def test_an_equipment_name_from_equipment_or_a_private_value_is_released(source, kept):
    written = _written(_element(kept, "LO", SCANNER))
    condition = _condition(written, (source, "LO", SCANNER))

    assert condition.decision is Decision.RELEASE
    assert [why for _, why in condition.exempted] == [Exemption.EQUIPMENT]


@pytest.mark.deid_requirement("MIDI-BP-01")
@pytest.mark.parametrize(
    "source",
    [
        "(0008,0080)",  # Institution Name, as an in-house device can name it
        "(0008,1010)",  # Station Name
        "(0009,0010)",  # a private creator, which can name the institution
    ],
)
def test_an_equipment_name_holding_an_identifying_value_goes_to_review(source):
    written = _written(_element(0x00080070, "LO", f"{HOSPITAL} PHYSICS"))
    condition = _condition(written, (source, "LO", HOSPITAL))

    assert condition.decision is Decision.QC_REVIEW
    assert not condition.exempted


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_other_kept_text_still_goes_to_review():
    written = _written(_element(0x0008103E, "LO", SCANNER))
    condition = _condition(written, ("(0009,1012)", "LO", SCANNER))

    assert condition.decision is Decision.QC_REVIEW


# Reading kept values.


def test_kept_values_are_read_as_iso_646_text_without_padding():
    kept = KeptValues(
        _written(
            _element(0x00080008, "CS", "ORIGINAL\\PRIMARY\\\\ "),
            _element(0x00080070, "LO", "M\xdcLLER"),
        )
    )

    assert kept.values(ElementPath((), "(0008,0008)")) == (
        "ORIGINAL",
        "PRIMARY",
        "",
        "",
    )
    assert kept.values(ElementPath((), "(0008,0070)")) is None
    assert kept.values(ElementPath((), "(0008,0060)")) is None
    assert repr(kept) == "KeptValues(elements=2)"


def test_a_cs_value_outside_iso_646_is_not_exempt():
    written = _written(_element(0x00181181, "CS", "NONE\\\xc4"))
    condition = _condition(written, ("(0054,1105)", "LO", "NONE"))

    assert condition.decision is Decision.QC_REVIEW


def test_the_equipment_names_are_kept_by_the_basic_profile():
    # Table E.1-1 does not list them, so the Basic Profile keeps them.
    listed = {row.tag for row in load_table_e1_1().attributes}

    assert listed.isdisjoint(residual_exemptions.EQUIPMENT_NAMES)
