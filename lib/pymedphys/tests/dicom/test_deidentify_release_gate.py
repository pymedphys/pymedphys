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

from pymedphys._dicom.deidentify import release_gate
from pymedphys._dicom.deidentify.file_layout import ElementPath, Location, Region
from pymedphys._dicom.deidentify.release_gate import (
    CollectionOutcome,
    Coverage,
    Decision,
    ReasonCode,
    Uncollected,
    direct_identifiers,
    release_condition,
)
from pymedphys._dicom.deidentify.residuals import (
    Finding,
    Form,
    NotSearched,
    Omission,
    ResidualSearch,
    SourceValue,
    ValueKind,
    find_residuals,
)

# Invented values, distinctive enough that nothing else in a file matches them.
NAME = "MÜLLERSOHN^ZEBEDEE"
DESCRIPTION = "QUILLON ÄRZTE STUDIE"
PATIENT_ID = "ZQ7741093"
UNDECODABLE = "could not be decoded as VR PN"

NAME_PATH = ElementPath((), "(0010,0010)")
DESCRIPTION_PATH = ElementPath((), "(0008,1030)")
ID_PATH = ElementPath((), "(0010,0020)")
BEAM_NAME_PATH = ElementPath((("(300A,00B0)", 0),), "(300A,00C2)")
CLEAN = ResidualSearch((), (), True)

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
    """An explicit VR element with a short header (PS3.5 Table 7.1-2)."""
    group, element = divmod(tag, 0x10000)
    return struct.pack("<HH2sH", group, element, vr.encode(), len(value)) + value


def _written():
    """A file as de-identification writes it: Study Description emptied."""
    syntax = _element(0x00020010, "UI", b"1.2.840.10008.1.2.1\x00")
    return bytes(128) + b"DICM" + syntax + _element(0x00081030, "LO", b"")


def _finding(source, kind, region=Region.DATA_SET, element=DESCRIPTION_PATH):
    location = Location(region, element if region is Region.DATA_SET else None)
    return Finding(source, kind, Form.VALUE, "utf-8", location, 0)


def _search(*findings, readable=True):
    return ResidualSearch(tuple(findings), (), readable)


def _uncollected(tag, *items):
    return Coverage((), (Uncollected(ElementPath(items, tag), UNDECODABLE),))


# The direct identifiers.


def test_the_rule_selects_exactly_the_direct_identifiers_the_design_lists():
    assert direct_identifiers() == frozenset(LISTED)


# Collection outcomes.


def test_a_complete_collection_with_a_clean_search_is_released():
    coverage = Coverage((SourceValue(NAME_PATH, "PN", NAME),))
    condition = release_condition(coverage, CLEAN)
    assert coverage.outcome is CollectionOutcome.COMPLETE
    assert condition.decision is Decision.RELEASE
    assert not condition.reasons


def test_nothing_collected_with_values_to_collect_is_withheld():
    coverage = _uncollected("(0010,0010)")
    condition = release_condition(coverage, CLEAN)
    assert not coverage.collected
    assert condition.outcome is CollectionOutcome.INCOMPLETE
    assert condition.decision is Decision.WITHHOLD
    (reason,) = condition.reasons
    assert (reason.path, reason.code) == (NAME_PATH, ReasonCode.UNCOLLECTED)


@pytest.mark.parametrize(
    "tag, items",
    [
        ("(0010,0010)", ()),  # PN
        ("(0020,000D)", ()),  # UI
        ("(0010,0030)", ()),  # DA
        ("(0008,002A)", ()),  # DT
        ("(0010,0020)", (("(0010,1002)", 0),)),  # a direct identifier in an item
        ("(0040,A354)", ()),  # a retired direct identifier
        ("(0019,1001)", ()),  # private, so the dictionary gives no VR
        ("(0010,1002)", ()),  # a sequence whose items could not be read
    ],
)
def test_an_uncollected_value_of_a_required_kind_is_withheld(tag, items):
    condition = release_condition(_uncollected(tag, *items), CLEAN)
    assert condition.decision is Decision.WITHHOLD


@pytest.mark.parametrize("tag", ["(0008,1030)", "(300A,00C2)", "(0018,1020)"])
def test_other_uncollected_text_goes_to_qc_review(tag):
    condition = release_condition(_uncollected(tag), CLEAN)
    assert condition.outcome is CollectionOutcome.INCOMPLETE
    assert condition.decision is Decision.QC_REVIEW


def test_an_uncollected_value_that_the_search_never_searches_goes_to_qc_review():
    # Patient's Size (0010,1020) is DS: its value would have been listed as
    # not searched, but an undecoded value is still a gap in coverage.
    condition = release_condition(_uncollected("(0010,1020)"), CLEAN)
    assert condition.decision is Decision.QC_REVIEW


# The decision of 1 October 2026, clarified on 2 October 2026: removed text
# outside ISO 646 with no Specific Character Set is read as ISO 8859-1, and
# the transformation proceeds, but release is conditional on coverage.


def test_a_removed_name_read_only_as_latin_1_is_withheld_after_a_clean_search():
    value = SourceValue(NAME_PATH, "PN", NAME)
    search = find_residuals(_written(), [value])
    assert not search.findings and search.readable
    coverage = Coverage((value,), (), frozenset({NAME_PATH}))
    condition = release_condition(coverage, search)
    assert condition.outcome is CollectionOutcome.INCOMPLETE
    assert condition.decision is Decision.WITHHOLD
    (reason,) = condition.reasons
    assert (reason.path, reason.code) == (NAME_PATH, ReasonCode.READ_AS_LATIN_1)


def test_a_removed_description_read_only_as_latin_1_goes_to_qc_review():
    value = SourceValue(DESCRIPTION_PATH, "LO", DESCRIPTION)
    search = find_residuals(_written(), [value])
    assert not search.findings
    coverage = Coverage((value,), (), frozenset({DESCRIPTION_PATH}))
    assert release_condition(coverage, search).decision is Decision.QC_REVIEW


def test_a_path_both_uncollected_and_read_as_latin_1_gives_one_reason():
    coverage = Coverage(
        (), (Uncollected(NAME_PATH, UNDECODABLE),), frozenset({NAME_PATH})
    )
    (reason,) = release_condition(coverage, CLEAN).reasons
    assert reason.code is ReasonCode.UNCOLLECTED


# Pooling a subject's coverage across the run's instances.


def test_coverages_merge_in_order_without_repeats():
    name = SourceValue(NAME_PATH, "PN", NAME)
    gap = Uncollected(DESCRIPTION_PATH, UNDECODABLE)
    first = Coverage((name,), (gap,), frozenset({NAME_PATH}))
    second = Coverage((SourceValue(ID_PATH, "LO", PATIENT_ID), name), (gap,))
    merged = Coverage.merge(first, second)
    assert merged.collected == (name, second.collected[0])
    assert merged.uncollected == (gap,)
    assert merged.decoded_as_bytes == frozenset({NAME_PATH})
    assert Coverage.merge() == Coverage(())


def test_a_siblings_uncollected_name_withholds_this_file():
    # This instance's own values were all collected, and its search is clean,
    # but a sibling's Patient's Name could not be collected, so its copies in
    # this file cannot have been searched for.
    own = Coverage((SourceValue(DESCRIPTION_PATH, "LO", "PHANTOM STUDY"),))
    sibling = _uncollected("(0010,0010)")
    assert release_condition(own, CLEAN).decision is Decision.RELEASE
    pooled = Coverage.merge(own, sibling)
    assert release_condition(pooled, CLEAN).decision is Decision.WITHHOLD


def test_merge_takes_only_coverages():
    with pytest.raises(TypeError):
        Coverage.merge(Coverage(()), ())


# Exclusions and the search.


def test_exclusions_are_listed_and_never_count_as_incomplete():
    short = NotSearched(NAME_PATH, "PN", Form.NAME_COMPONENT, Omission.TOO_SHORT)
    binary = NotSearched(DESCRIPTION_PATH, "OB", Form.VALUE, Omission.BINARY)
    search = ResidualSearch((), (short, binary), True)
    condition = release_condition(Coverage(()), search)
    assert condition.outcome is CollectionOutcome.COMPLETE
    assert condition.decision is Decision.RELEASE
    assert condition.exclusions == (short, binary)


def test_an_unreadable_file_is_withheld():
    condition = release_condition(Coverage(()), _search(readable=False))
    assert condition.decision is Decision.WITHHOLD
    (reason,) = condition.reasons
    assert (reason.path, reason.code) == (None, ReasonCode.UNREADABLE_FILE)


@pytest.mark.parametrize(
    "kind, code",
    [
        (ValueKind.PERSON_NAME, ReasonCode.RESIDUAL_PERSON_NAME),
        (ValueKind.UID, ReasonCode.RESIDUAL_UID),
        (ValueKind.DATE, ReasonCode.RESIDUAL_DATE),
        (ValueKind.DATETIME, ReasonCode.RESIDUAL_DATETIME),
    ],
)
def test_a_finding_of_a_required_kind_is_withheld(kind, code):
    condition = release_condition(Coverage(()), _search(_finding(NAME_PATH, kind)))
    assert condition.decision is Decision.WITHHOLD
    assert [reason.code for reason in condition.reasons] == [code]


def test_a_text_finding_of_a_direct_identifier_is_withheld():
    source = ElementPath((("(0010,1002)", 0),), "(0010,0020)")
    finding = _finding(source, ValueKind.TEXT)
    condition = release_condition(Coverage(()), _search(finding))
    assert condition.decision is Decision.WITHHOLD
    (reason,) = condition.reasons
    assert reason.code is ReasonCode.RESIDUAL_DIRECT_IDENTIFIER
    assert reason.location == finding.location


@pytest.mark.parametrize(
    "region",
    [Region.PREAMBLE, Region.FILE_META, Region.TRAILING_PADDING, Region.TRAILING],
)
def test_a_text_finding_outside_the_data_set_is_withheld(region):
    finding = _finding(DESCRIPTION_PATH, ValueKind.TEXT, region)
    condition = release_condition(Coverage(()), _search(finding))
    assert condition.decision is Decision.WITHHOLD
    assert condition.reasons[0].code is ReasonCode.RESIDUAL_OUTSIDE_DATA_SET


def test_a_text_finding_inside_the_data_set_goes_to_qc_review():
    finding = _finding(DESCRIPTION_PATH, ValueKind.TEXT)
    condition = release_condition(Coverage(()), _search(finding))
    assert condition.decision is Decision.QC_REVIEW
    assert condition.reasons[0].code is ReasonCode.RESIDUAL_TEXT


def test_a_person_name_found_in_a_retained_rt_label_is_withheld():
    # The design leaves open whether such findings go to QC review instead; until
    # it is decided, they fail the file.
    finding = _finding(NAME_PATH, ValueKind.PERSON_NAME, element=BEAM_NAME_PATH)
    condition = release_condition(Coverage(()), _search(finding))
    assert condition.decision is Decision.WITHHOLD


def test_the_most_severe_decision_wins():
    text = _finding(DESCRIPTION_PATH, ValueKind.TEXT)
    coverage = _uncollected("(0008,1030)")
    assert release_condition(coverage, _search(text)).decision is Decision.QC_REVIEW
    name = _finding(NAME_PATH, ValueKind.PERSON_NAME)
    condition = release_condition(coverage, _search(text, name))
    assert condition.decision is Decision.WITHHOLD
    assert len(condition.reasons) == 3


# Hygiene and validation.


def test_reasons_and_reprs_hold_no_values():
    values = (
        SourceValue(NAME_PATH, "PN", NAME),
        SourceValue(ID_PATH, "LO", PATIENT_ID),
    )
    coverage = Coverage(
        values,
        (Uncollected(DESCRIPTION_PATH, UNDECODABLE),),
        frozenset({NAME_PATH}),
    )
    condition = release_condition(
        coverage, _search(_finding(ID_PATH, ValueKind.TEXT), readable=False)
    )
    shown = [repr(coverage), repr(condition), str(condition)]
    shown += [
        text for reason in condition.reasons for text in (repr(reason), str(reason))
    ]
    for text in shown:
        for secret in (NAME, PATIENT_ID, "MÜLLERSOHN", "ZEBEDEE"):
            assert secret not in text
    assert repr(condition) == (
        "ReleaseCondition(decision='withhold', outcome='incomplete', reasons=4, "
        "exclusions=0)"
    )
    assert str(condition.reasons[0]) == ("qc-review: (0008,1030): uncollected")


@pytest.mark.parametrize(
    "arguments",
    [
        ([SourceValue(NAME_PATH, "PN", NAME)],),
        (("not a source value",),),
        ((), [Uncollected(NAME_PATH, UNDECODABLE)]),
        ((), (NAME_PATH,)),
        ((), (), {NAME_PATH}),
        ((), (), frozenset({"(0010,0010)"})),
    ],
)
def test_coverage_rejects_malformed_input(arguments):
    with pytest.raises(TypeError):
        Coverage(*arguments)


@pytest.mark.parametrize("reason", ["", None])
def test_an_uncollected_value_needs_a_path_and_a_reason(reason):
    with pytest.raises(ValueError):
        Uncollected(NAME_PATH, reason)
    with pytest.raises(ValueError):
        Uncollected("(0010,0010)", UNDECODABLE)


def test_the_gate_takes_only_a_coverage_and_a_search():
    with pytest.raises(TypeError):
        release_condition((), CLEAN)
    with pytest.raises(TypeError):
        release_condition(Coverage(()), ((), (), True))


def test_the_module_offers_no_configuration():
    assert set(release_gate.release_condition.__code__.co_varnames[:2]) == {
        "coverage",
        "search",
    }
    assert release_gate.release_condition.__code__.co_argcount == 2
