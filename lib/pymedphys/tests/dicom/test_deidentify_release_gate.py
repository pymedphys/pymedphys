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

"""The release condition: residual coverage and the residual search together."""

import struct

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify.file_layout import ElementPath, Region
from pymedphys._dicom.deidentify.release_gate import (
    CollectionOutcome,
    Coverage,
    Decision,
    ReasonCode,
    Uncollected,
    direct_identifiers,
    release_condition,
)
from pymedphys._dicom.deidentify.residuals import Omission, SourceValue

# Invented values, distinctive enough that nothing else in a file matches them.
PERSON = "ZEBEDEE^QUILLON"
LATIN_NAME = "MÜLLERSOHN^ZEBEDEE"
DESCRIPTION = "ZARQUON STUDY"
LATIN_DESCRIPTION = "ZARQUON ÄRZTE STUDIE"
PATIENT_ID = "ZQ7741093"
UID = "1.2.999.4417.1.20240517.1"
BIRTH_DATE = "19710203"
DATETIME = "20240517093000"
UNDECODABLE = "could not be decoded as VR PN"

NAME_PATH = ElementPath((), "(0010,0010)")
DESCRIPTION_PATH = ElementPath((), "(0008,1030)")
ID_PATH = ElementPath((), "(0010,0020)")
OTHER_ID_PATH = ElementPath((("(0010,1002)", 0),), "(0010,0020)")
PRIVATE_PATH = ElementPath((), "(0019,1001)")

# The direct identifiers that the design document lists for 2026d.
LISTED = {
    "(0010,0020)": "Patient ID",
    "(0010,0021)": "Issuer of Patient ID",
    "(0010,2154)": "Patient's Telephone Numbers",
    "(0008,0050)": "Accession Number",
    "(0008,0094)": "Referring Physician's Telephone Numbers",
    "(0020,0010)": "Study ID",
    "(0038,0010)": "Admission ID",
    "(0038,0060)": "Service Episode ID",
    "(0040,0009)": "Scheduled Procedure Step ID",
    "(0040,0253)": "Performed Procedure Step ID",
    "(0040,1001)": "Requested Procedure ID",
    "(0040,1103)": "Person's Telephone Numbers",
    "(0040,2010)": "Order Callback Phone Number",
    "(0040,2016)": "Placer Order Number / Imaging Service Request",
    "(0040,2017)": "Filler Order Number / Imaging Service Request",
    "(0010,1000)": "Other Patient IDs",
    "(0010,1090)": "Medical Record Locator",
    "(0032,0012)": "Study ID Issuer",
    "(0038,0011)": "Issuer of Admission ID",
    "(0038,0061)": "Issuer of Service Episode ID",
    "(0040,050A)": "Specimen Accession Number",
    "(0040,A354)": "Telephone Number (Trial)",
}


def _element(tag, vr, value):
    """An explicit VR element with the header of PS3.5 Table 7.1-1 or 7.1-2."""
    group, element = divmod(tag, 0x10000)
    value = value.encode() if isinstance(value, str) else value
    value += b" " * (len(value) % 2)
    if vr in ("OB", "UT"):
        return (
            struct.pack("<HH2sHI", group, element, vr.encode(), 0, len(value)) + value
        )
    return struct.pack("<HH2sH", group, element, vr.encode(), len(value)) + value


def _written(carried="", where=Region.DATA_SET):
    """A file as de-identification writes it, with Study Description emptied.

    ``carried`` is left in a private element, the preamble, the File Meta
    Information, Data Set Trailing Padding, or bytes after the data set.
    """
    preamble = (
        carried.encode().ljust(128, b"\x00") if where is Region.PREAMBLE else bytes(128)
    )
    meta = _element(0x00020010, "UI", "1.2.840.10008.1.2.1\x00")
    if where is Region.FILE_META:
        meta += _element(0x00020016, "AE", carried)
    data_set = _element(0x00081030, "LO", b"")
    if where is Region.DATA_SET and carried:
        data_set += _element(0x00190010, "LO", "PRIVATE")
        data_set += _element(0x00191000, "UT", carried)
    if where is Region.TRAILING_PADDING:
        data_set += _element(0xFFFCFFFC, "OB", carried)
    if where is Region.TRAILING:
        data_set += b"\xff\xff\xff\xff" + carried.encode()
    return preamble + b"DICM" + meta + data_set


def _coverage(*collected, uncollected=(), latin_1=(), planned=()):
    """A coverage that planned every path it names, and ``planned`` besides."""
    paths = {value.source for value in collected}
    paths |= {each.path for each in uncollected} | set(latin_1) | set(planned)
    return Coverage(
        planned=frozenset(paths),
        collected=tuple(collected),
        uncollected=tuple(uncollected),
        decoded_as_bytes=frozenset(latin_1),
    )


def _uncollected(tag, *items):
    return _coverage(uncollected=[Uncollected(ElementPath(items, tag), UNDECODABLE)])


def _codes(condition):
    return [reason.code for reason in condition.reasons]


# The direct identifiers.


def test_the_rule_selects_exactly_the_direct_identifiers_the_design_lists():
    assert direct_identifiers() == frozenset(LISTED)


# Collection outcomes.


def test_a_complete_collection_with_a_clean_search_is_released():
    coverage = _coverage(SourceValue(NAME_PATH, "PN", PERSON))
    condition = release_condition(coverage, _written())
    assert coverage.outcome is CollectionOutcome.COMPLETE
    assert condition.decision is Decision.RELEASE
    assert not condition.reasons


def test_nothing_collected_with_values_to_collect_is_withheld():
    # The walker planned to collect Patient's Name, but reported neither the
    # value nor why it could not be collected.
    coverage = Coverage(planned=frozenset({NAME_PATH}), collected=())
    condition = release_condition(coverage, _written())
    assert coverage.outcome is CollectionOutcome.INCOMPLETE
    assert condition.decision is Decision.WITHHOLD
    (reason,) = condition.reasons
    assert (reason.path, reason.code) == (NAME_PATH, ReasonCode.NOT_REPORTED)


def test_a_planned_text_value_not_reported_goes_to_qc_review():
    coverage = _coverage(planned=[DESCRIPTION_PATH])
    condition = release_condition(coverage, _written())
    assert condition.decision is Decision.QC_REVIEW
    assert _codes(condition) == [ReasonCode.NOT_REPORTED]


@pytest.mark.parametrize(
    "tag, items",
    [
        ("(0010,0010)", ()),  # PN
        ("(0020,000D)", ()),  # UI
        ("(0010,0030)", ()),  # DA
        ("(0008,002A)", ()),  # DT
        ("(0010,0020)", (("(0010,1002)", 0),)),  # a direct identifier in an item
        ("(0040,A354)", ()),  # a retired direct identifier
        ("(0032,0012)", ()),  # a retired direct identifier of group 0032
        ("(0010,1002)", ()),  # a sequence whose items could not be read
    ],
)
def test_an_uncollected_value_of_a_required_kind_is_withheld(tag, items):
    condition = release_condition(_uncollected(tag, *items), _written())
    assert condition.decision is Decision.WITHHOLD


@pytest.mark.parametrize(
    "tag",
    [
        "(0008,1030)",  # LO
        "(300A,00C2)",  # LO, a retained RT label under some options
        "(0018,1020)",  # LO, a device identifier that an option retains
        "(0010,1020)",  # DS, which the search never searches
        "(0019,1001)",  # private, so the dictionary gives no VR
        "(0008,0202)",  # a retired placeholder without a VR
    ],
)
def test_other_uncollected_values_go_to_qc_review(tag):
    condition = release_condition(_uncollected(tag), _written())
    assert condition.outcome is CollectionOutcome.INCOMPLETE
    assert condition.decision is Decision.QC_REVIEW


def test_duplicate_gaps_at_one_path_give_one_reason():
    gaps = [Uncollected(NAME_PATH, UNDECODABLE), Uncollected(NAME_PATH, "other")]
    coverage = _coverage(uncollected=gaps, latin_1=[NAME_PATH])
    assert _codes(release_condition(coverage, _written())) == [ReasonCode.UNCOLLECTED]


# The decision of 1 October 2026, clarified on 2 October 2026: removed text
# outside ISO 646 with no Specific Character Set is read as ISO 8859-1, and
# the transformation proceeds, but release is conditional on coverage.


def test_a_removed_name_read_only_as_latin_1_is_withheld_after_a_clean_search():
    coverage = _coverage(SourceValue(NAME_PATH, "PN", LATIN_NAME), latin_1=[NAME_PATH])
    condition = release_condition(coverage, _written())
    assert not condition.search.findings and condition.search.readable
    assert condition.outcome is CollectionOutcome.INCOMPLETE
    assert condition.decision is Decision.WITHHOLD
    (reason,) = condition.reasons
    assert (reason.path, reason.code) == (NAME_PATH, ReasonCode.READ_AS_LATIN_1)


def test_a_removed_description_read_only_as_latin_1_goes_to_qc_review():
    value = SourceValue(DESCRIPTION_PATH, "LO", LATIN_DESCRIPTION)
    coverage = _coverage(value, latin_1=[DESCRIPTION_PATH])
    condition = release_condition(coverage, _written())
    assert not condition.search.findings
    assert condition.decision is Decision.QC_REVIEW


# Values collected under a VR that the pinned dictionary does not give.


def test_a_name_collected_as_lo_and_found_is_withheld_as_a_name():
    coverage = _coverage(SourceValue(NAME_PATH, "LO", PERSON))
    condition = release_condition(coverage, _written(PERSON))
    assert condition.decision is Decision.WITHHOLD
    assert ReasonCode.RESIDUAL_PERSON_NAME in _codes(condition)
    assert ReasonCode.COLLECTED_AS_OTHER_VR in _codes(condition)


@pytest.mark.parametrize(
    "vr, value, omission",
    [
        ("CS", PERSON, Omission.NOT_DISTINCTIVE),
        ("OB", PERSON.encode(), Omission.BINARY),
    ],
)
def test_a_name_collected_under_a_vr_the_search_excludes_is_withheld(
    vr, value, omission
):
    coverage = _coverage(SourceValue(NAME_PATH, vr, value))
    condition = release_condition(coverage, _written())
    assert [each.reason for each in condition.exclusions] == [omission]
    assert condition.outcome is CollectionOutcome.INCOMPLETE
    assert condition.decision is Decision.WITHHOLD
    assert _codes(condition) == [ReasonCode.COLLECTED_AS_OTHER_VR]


# Pooling a subject's coverage across the run's instances.


def test_coverages_merge_in_order_without_repeats():
    name = SourceValue(NAME_PATH, "PN", PERSON)
    gap = Uncollected(DESCRIPTION_PATH, UNDECODABLE)
    first = _coverage(name, uncollected=[gap], latin_1=[NAME_PATH])
    second = _coverage(SourceValue(ID_PATH, "LO", PATIENT_ID), name, uncollected=[gap])
    merged = Coverage.merge(first, second)
    assert merged.planned == {NAME_PATH, DESCRIPTION_PATH, ID_PATH}
    assert merged.collected == (name, second.collected[0])
    assert merged.uncollected == (gap,)
    assert merged.decoded_as_bytes == frozenset({NAME_PATH})
    assert Coverage.merge() == Coverage(planned=frozenset(), collected=())


def test_a_siblings_uncollected_name_withholds_this_file():
    # This instance's own values were all collected, and its search is clean,
    # but a sibling's Patient's Name could not be collected, so its copies in
    # this file cannot have been searched for.
    own = _coverage(SourceValue(DESCRIPTION_PATH, "LO", DESCRIPTION))
    sibling = _uncollected("(0010,0010)")
    assert release_condition(own, _written()).decision is Decision.RELEASE
    pooled = Coverage.merge(own, sibling)
    assert release_condition(pooled, _written()).decision is Decision.WITHHOLD


def test_a_siblings_name_read_only_as_latin_1_withholds_this_file():
    own = _coverage(SourceValue(DESCRIPTION_PATH, "LO", DESCRIPTION))
    value = SourceValue(NAME_PATH, "PN", LATIN_NAME)
    sibling = _coverage(value, latin_1=[NAME_PATH])
    pooled = Coverage.merge(own, sibling)
    assert release_condition(pooled, _written()).decision is Decision.WITHHOLD


def test_only_the_middle_of_three_coverages_has_the_gap():
    own = _coverage(SourceValue(DESCRIPTION_PATH, "LO", DESCRIPTION))
    last = _coverage(SourceValue(ID_PATH, "LO", PATIENT_ID))
    middle = _uncollected("(0010,0010)")
    pooled = Coverage.merge(own, middle, last)
    assert pooled.uncollected == middle.uncollected  # its reason is kept
    condition = release_condition(pooled, _written())
    assert condition.decision is Decision.WITHHOLD
    assert _codes(condition) == [ReasonCode.UNCOLLECTED]


def test_a_siblings_unreported_name_is_not_hidden_by_this_instances_copy():
    # Both instances planned Patient's Name at the same path; this one
    # collected it, and the sibling reported nothing for it.
    own = _coverage(SourceValue(NAME_PATH, "PN", PERSON))
    sibling = Coverage(planned=frozenset({NAME_PATH}), collected=())
    pooled = Coverage.merge(own, sibling)
    condition = release_condition(pooled, _written())
    assert condition.decision is Decision.WITHHOLD
    assert _codes(condition) == [ReasonCode.NOT_REPORTED]


def test_the_search_covers_the_pooled_values():
    sibling = _coverage(SourceValue(ID_PATH, "LO", PATIENT_ID))
    pooled = Coverage.merge(_coverage(), sibling)
    condition = release_condition(pooled, _written(PATIENT_ID))
    assert condition.decision is Decision.WITHHOLD
    assert _codes(condition) == [ReasonCode.RESIDUAL_DIRECT_IDENTIFIER]


def test_merge_takes_only_coverages():
    with pytest.raises(TypeError):
        Coverage.merge(_coverage(), ())


# Exclusions and the search.


def test_exclusions_are_listed_and_never_count_as_incomplete():
    short = SourceValue(NAME_PATH, "PN", "ZEBEDEE^LI")
    binary = SourceValue(PRIVATE_PATH, "OB", b"\x01\x02\x03\x04\x05")
    condition = release_condition(_coverage(short, binary), _written())
    assert condition.outcome is CollectionOutcome.COMPLETE
    assert condition.decision is Decision.RELEASE
    assert [(each.source, each.reason) for each in condition.exclusions] == [
        (NAME_PATH, Omission.TOO_SHORT),
        (PRIVATE_PATH, Omission.BINARY),
    ]


def test_an_unreadable_file_is_withheld():
    condition = release_condition(_coverage(), _written(DESCRIPTION, Region.TRAILING))
    assert condition.decision is Decision.WITHHOLD
    assert ReasonCode.UNREADABLE_FILE in _codes(condition)
    (reason,) = [r for r in condition.reasons if r.path is None]
    assert reason.code is ReasonCode.UNREADABLE_FILE


@pytest.mark.parametrize(
    "path, vr, value, code",
    [
        (NAME_PATH, "PN", PERSON, ReasonCode.RESIDUAL_PERSON_NAME),
        (ElementPath((), "(0020,000D)"), "UI", UID, ReasonCode.RESIDUAL_UID),
        (ElementPath((), "(0010,0030)"), "DA", BIRTH_DATE, ReasonCode.RESIDUAL_DATE),
        (
            ElementPath((), "(0008,002A)"),
            "DT",
            DATETIME,
            ReasonCode.RESIDUAL_DATETIME,
        ),
        (OTHER_ID_PATH, "LO", PATIENT_ID, ReasonCode.RESIDUAL_DIRECT_IDENTIFIER),
    ],
)
def test_a_finding_of_a_required_kind_is_withheld(path, vr, value, code):
    coverage = _coverage(SourceValue(path, vr, value))
    condition = release_condition(coverage, _written(value))
    assert condition.decision is Decision.WITHHOLD
    assert _codes(condition) == [code]
    assert condition.reasons[0].location.region is Region.DATA_SET


@pytest.mark.parametrize(
    "region",
    [Region.PREAMBLE, Region.FILE_META, Region.TRAILING_PADDING, Region.TRAILING],
)
def test_a_text_finding_outside_the_data_set_is_withheld(region):
    coverage = _coverage(SourceValue(DESCRIPTION_PATH, "LO", DESCRIPTION))
    condition = release_condition(coverage, _written(DESCRIPTION, region))
    assert condition.decision is Decision.WITHHOLD
    found = [r for r in condition.reasons if r.location is not None]
    assert [r.code for r in found] == [ReasonCode.RESIDUAL_OUTSIDE_DATA_SET]
    assert found[0].location.region is region


def test_a_text_finding_inside_the_data_set_goes_to_qc_review():
    coverage = _coverage(SourceValue(DESCRIPTION_PATH, "LO", DESCRIPTION))
    condition = release_condition(coverage, _written(DESCRIPTION))
    assert condition.decision is Decision.QC_REVIEW
    assert _codes(condition) == [ReasonCode.RESIDUAL_TEXT]


def test_a_person_name_found_in_a_retained_rt_label_is_withheld():
    # The design leaves open whether such findings go to QC review instead;
    # until it is decided, they fail the file. Beam Name is retained here.
    beam_name = struct.pack("<HH2sH", 0x300A, 0x00C2, b"LO", 8) + b"QUILLON "
    coverage = _coverage(SourceValue(NAME_PATH, "PN", PERSON))
    written = _written() + beam_name
    condition = release_condition(coverage, written)
    assert condition.decision is Decision.WITHHOLD
    assert condition.reasons[0].location.element.tag == "(300A,00C2)"


def test_a_withholding_reason_then_a_lesser_one_withholds():
    coverage = _coverage(
        SourceValue(DESCRIPTION_PATH, "LO", DESCRIPTION),
        uncollected=[Uncollected(NAME_PATH, UNDECODABLE)],
    )
    condition = release_condition(coverage, _written(DESCRIPTION))
    assert [r.decision for r in condition.reasons] == [
        Decision.WITHHOLD,
        Decision.QC_REVIEW,
    ]
    assert condition.decision is Decision.WITHHOLD


def test_a_lesser_reason_then_a_withholding_one_withholds():
    coverage = _coverage(
        SourceValue(NAME_PATH, "PN", PERSON),
        uncollected=[Uncollected(DESCRIPTION_PATH, UNDECODABLE)],
    )
    condition = release_condition(coverage, _written(PERSON))
    assert [r.decision for r in condition.reasons] == [
        Decision.QC_REVIEW,
        Decision.WITHHOLD,
    ]
    assert condition.decision is Decision.WITHHOLD


# Hygiene and validation.


def test_reasons_and_reprs_hold_no_values():
    sentinel = "SENTINELVALUE"
    coverage = _coverage(
        SourceValue(NAME_PATH, "PN", PERSON),
        SourceValue(ID_PATH, "LO", PATIENT_ID),
        uncollected=[Uncollected(DESCRIPTION_PATH, sentinel)],
        latin_1=[NAME_PATH],
    )
    condition = release_condition(coverage, _written(PATIENT_ID, Region.TRAILING))
    shown = [repr(coverage), repr(condition), str(condition)]
    shown += [repr(each) for each in coverage.uncollected]
    shown += [repr(condition.search), *map(str, condition.exclusions)]
    shown += [text for r in condition.reasons for text in (repr(r), str(r))]
    for text in shown:
        for secret in (PERSON, PATIENT_ID, "ZEBEDEE", "QUILLON", sentinel):
            assert secret not in text
    assert repr(condition) == (
        "ReleaseCondition(decision='withhold', outcome='incomplete', reasons=4, "
        "exclusions=0)"
    )
    assert str(condition.reasons[0]) == "qc-review: (0008,1030): uncollected"
    assert repr(coverage.uncollected[0]) == "Uncollected(path='(0008,1030)')"


@pytest.mark.parametrize(
    "arguments",
    [
        {"collected": ()},  # planned is required
        {"planned": frozenset(), "collected": [SourceValue(NAME_PATH, "PN", PERSON)]},
        {"planned": frozenset(), "collected": ("not a source value",)},
        {"planned": {NAME_PATH}, "collected": ()},
        {"planned": frozenset({"(0010,0010)"}), "collected": ()},
        {"planned": frozenset(), "collected": (), "uncollected": (NAME_PATH,)},
        {"planned": frozenset(), "collected": (), "decoded_as_bytes": {NAME_PATH}},
    ],
)
def test_coverage_rejects_malformed_input(arguments):
    with pytest.raises(TypeError):
        Coverage(**arguments)


@pytest.mark.parametrize("reason", ["", None])
def test_an_uncollected_value_needs_a_path_and_a_reason(reason):
    with pytest.raises(ValueError):
        Uncollected(NAME_PATH, reason)
    with pytest.raises(ValueError):
        Uncollected("(0010,0010)", UNDECODABLE)


def test_the_gate_takes_only_a_coverage_and_written_bytes():
    with pytest.raises(TypeError):
        release_condition((), _written())
    with pytest.raises(TypeError):
        release_condition(_coverage(), "not bytes")
