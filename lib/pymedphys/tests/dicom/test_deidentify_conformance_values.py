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

"""The values, dates, residual search, and release report that the statement describes."""

import collections
import functools

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import (
    conformance,
    conformance_markdown,
    conformance_values,
    dummy_values,
    edits,
    policy,
    pseudonyms,
    release_report,
    residuals,
    reviewed_roi_names,
    standard,
    supplementary_actions,
    temporal_roles,
    uids,
    walker,
)
from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.keys import DeidKey

TEMPORAL_VRS = frozenset({"DA", "DT", "TM"})
TIMEZONE_OFFSET = "(0008,0201)"


@pytest.fixture(name="preset", scope="module", params=list(policy.PRESETS))
def _preset(request):
    return request.param


@functools.cache
def _statement(preset):
    """Return a preset's statement, built once: no test here patches its inputs."""
    return conformance.conformance_statement(
        policy.compose_policy(preset), vocabulary=None
    )


def _section(preset, heading):
    """Return one second-level section of a preset's rendered statement."""
    lines = conformance_markdown.render_markdown(_statement(preset)).splitlines()
    start = lines.index(f"## {heading}") + 1
    end = next(
        (i for i in range(start, len(lines)) if lines[i].startswith("## ")),
        len(lines),
    )
    return " ".join(lines[start:end])


def _named(tag):
    return f"{standard.dictionary_attribute(tag).name} {tag}"


@pytest.mark.deid_requirement("MIDI-BP-05")
def test_kept_local_codes_are_said_to_be_listed_in_the_qc_pack(preset):
    rules = supplementary_actions.load_supplementary_actions().rules
    codes = ("(0008,0100)", "(0008,0102)", "(0008,0104)")
    assert {rules[tag].action for tag in codes} == {"K"}

    section = _section(preset, "Codes of local coding schemes")

    for tag in codes:
        assert _named(tag) in section
    assert 'begins with "99" or is "L"' in section
    assert "the institution's name or abbreviation" in section
    assert "retained strings of the run's confidential QC pack" in section


@pytest.mark.deid_requirement("MIDI-BP-05")
def test_the_removed_private_creators_description_is_described(preset):
    statement = _statement(preset)
    private = next(
        e
        for e in statement.attributes
        if e.tag == conformance_markdown.PRIVATE_ATTRIBUTES_TAG
    )
    sentence = (
        "Private Data Element Characteristics Sequence (0008,0300), which "
        "describes the private blocks by their private creators, is removed by "
        "its supplementary rule"
    )

    assert (sentence in _section(preset, "Actions")) == (private.action == "X")


@pytest.mark.deid_requirement("PS3.15-E.1.3-01")
def test_the_reviewed_dummy_item_is_described():
    section = _section("basic", "Values written")
    assert walker.REVIEWED_DUMMY_SEQUENCES
    for tag, compared in walker.REVIEWED_DUMMY_SEQUENCES.items():
        assert f"D on {_named(tag)} writes one item" in section
        (first,) = dummy_values.items_for_d(tag, [])
        for element in first:
            assert f"{_named(element.tag)} `{element.value}`" in section
        # A source item that holds the first item's values takes the second.
        source = {e.tag: e.value for e in first if e.tag in compared}
        (second,) = dummy_values.items_for_d(tag, [source])
        changed = [e for e, f in zip(second, first) if e.value != f.value]
        assert changed
        for element in changed:
            assert f"`{element.value}`" in section
        for compared_tag in compared:
            assert _named(compared_tag) in section


@pytest.mark.deid_requirement("PS3.15-E.1.3-01")
def test_only_the_reviewed_items_coding_scheme_names_pymedphys():
    section = _section("basic", "Values written")
    named = [
        element
        for tag in walker.REVIEWED_DUMMY_SEQUENCES
        for item in dummy_values.items_for_d(tag, [])
        for element in item
        if "PYMEDPHYS" in element.value.upper()
    ]
    assert [e.tag for e in named] == ["(0008,0102)"]
    assert (
        "No value that Z, D, or U writes names PyMedPhys, except the "
        f"{_named('(0008,0102)')} `{named[0].value}`"
    ) in section
    assert not any(
        "PYMEDPHYS" in str(value).upper()
        for pair in dummy_values.CONSTANTS.values()
        for value in pair
    )


@pytest.mark.deid_requirement("PS3.15-E.1.3-01")
def test_pseudonyms_are_described_where_the_engine_writes_them():
    section = _section("basic", "Values written")
    names = " and ".join(_named(tag) for tag in sorted(edits.PSEUDONYM_TAGS))
    assert f"At the top level of the data set, {names} take" in section
    assert "elsewhere, as in an item of a sequence, Z and D write" in section
    pseudonym = pseudonyms.patient_pseudonym(
        DeidKey(bytes(32)), pseudonyms.SubjectIdentity.curated("SUBJECT-0001")
    )
    code = pseudonym.patient_id.removeprefix(pseudonyms.PATIENT_ID_PREFIX)
    assert f"{len(pseudonym.patient_id)} characters in all" in section
    assert f"the {len(code)} characters of the base32 form" in section
    assert pseudonym.patients_name == f"{pseudonyms.FAMILY_NAME}^{code}"
    assert _named("(0010,0021)") in section


@pytest.mark.deid_requirement("PS3.15-E.1.3-01")
def test_the_longest_replacement_uid_is_described():
    section = _section("basic", "Values written")
    key = DeidKey(bytes(range(32)))
    longest = max(
        len(uids.replacement_uid(key, f"1.2.826.0.1.3680043.2.1125.{i}"))
        for i in range(2000)
    )
    limit = len(uids.UID_ROOT) + len(str(2**128 - 1))
    assert longest <= limit <= 64
    assert f"at most {limit} characters in all" in section


@pytest.mark.deid_requirement("PS3.15-E.1.3-01")
@pytest.mark.parametrize("preset", ["basic", "basic-clean-descriptors"])
def test_dates_take_their_listed_actions_without_a_temporal_option(preset):
    statement = _statement(preset)
    assert statement.temporal.option == ""
    section = _section(preset, "Dates and times")
    assert "no date or time is shifted or otherwise modified" in section
    actions = {e.tag: e.action for e in statement.attributes}
    assert f"{_named(TIMEZONE_OFFSET)} takes `{actions[TIMEZONE_OFFSET]}`" in section
    assert f"`{statement.markers.temporal}`" in section
    for vr in sorted(TEMPORAL_VRS):
        first, second = dummy_values.CONSTANTS[vr]
        assert f"`{first}`" in section and f"`{second}`" in section


@pytest.mark.deid_requirement("PS3.15-E.1.3-01")
@pytest.mark.parametrize("preset", ["tps-import", "public-release"])
def test_dates_under_modified_dates_are_cleaned_and_their_manner_is_pending(preset):
    statement = _statement(preset)
    assert statement.temporal.option == policy.MODIFIED_DATES
    assert conformance.PENDING_CLEANING in statement.pending
    section = _section(preset, "Dates and times")
    assert "Retain Longitudinal Temporal Information with Modified Dates" in section
    assert "is not yet described" in section


@pytest.mark.deid_requirement("PS3.15-E.1.3-01")
def test_the_temporal_attributes_are_counted_by_their_listed_action(preset):
    statement = _statement(preset)
    roles = temporal_roles.load_temporal_roles().rules
    actions = {e.tag: e.action for e in statement.attributes}
    counts = collections.Counter(actions[tag] for tag in roles)
    assert dict(statement.temporal.actions) == dict(counts)
    assert statement.temporal.attributes == len(roles)
    others = sorted(
        tag
        for tag in roles
        if not set(standard.dictionary_attribute(tag).vrs) <= TEMPORAL_VRS
    )
    assert list(statement.temporal.other_attributes) == others
    assert TIMEZONE_OFFSET in others
    section = _section(preset, "Dates and times")
    assert f"The temporal roles cover {len(roles)} attributes" in section
    for action, count in counts.items():
        assert f"`{action}` for {count}" in section
    for tag in others:
        assert _named(tag) in section


@pytest.mark.deid_requirement("PS3.15-E.1.3-01")
def test_the_residual_search_coverage_is_described(preset):
    section = _section(preset, "Residual search")
    assert f"fewer than {residuals.MIN_CHARACTERS} characters" in section
    assert f"at least {residuals.MIN_BYTES_IN_NUMBERS} bytes" in section
    assert f"first {residuals.MAX_CHARACTERS} characters" in section
    for codec in residuals.CODECS:
        assert conformance_values.CODEC_NAMES[codec] in section
    searched = sorted(residuals._KINDS)  # pylint: disable = protected-access
    assert f"Values of VR {conformance_values.join(searched)} are searched" in section
    pixel_data = residuals._PIXEL_DATA  # pylint: disable = protected-access
    assert conformance_values.join(_named(tag) for tag in sorted(pixel_data)) in section
    numbers = residuals._NUMBERS  # pylint: disable = protected-access
    assert f"values of VR {conformance_values.join(sorted(numbers), 'or')}," in section


@pytest.mark.deid_requirement("PS3.15-E.1.3-01")
def test_every_reason_a_value_is_not_searched_is_described():
    assert set(conformance_values.OMISSIONS) == set(residuals.Omission)
    assert set(conformance_values.CODEC_NAMES) == set(residuals.CODECS)
    section = _section("basic", "Residual search")
    for reason in residuals.Omission:
        assert conformance_values.OMISSIONS[reason] in section


def test_a_value_equal_to_a_written_constant_as_d_compares_is_not_searched():
    # D compares an LO value without regard to case or padding, and the
    # search drops only the values of a multi-valued attribute that match.
    source = ElementPath((), "(0008,1040)")
    assert ("LO", "DEIDENTIFIED") in residuals.written_constants()
    whole = residuals.SourceValue(source, "LO", "deidentified ")
    result = residuals.find_residuals(b"deidentified", [whole])
    assert not result.findings
    (unsearched,) = result.unsearched
    assert unsearched.reason is residuals.UnsearchedReason.WRITTEN_CONSTANT
    part = residuals.SourceValue(source, "LO", "QUILLON\\deidentified")
    result = residuals.find_residuals(b"QUILLON", [part])
    assert result.findings
    (unsearched,) = result.unsearched
    assert unsearched.reason is residuals.UnsearchedReason.WRITTEN_CONSTANT
    name = ElementPath((), "(0010,1001)")
    form = residuals.SourceValue(name, "PN", "DEIDENTIFIED^ZEBEDEE")
    result = residuals.find_residuals(b"ZEBEDEE", [form])
    assert result.findings
    (unsearched,) = result.unsearched
    assert unsearched.reason is residuals.UnsearchedReason.WRITTEN_CONSTANT
    described = conformance_values.UNSEARCHED_REASONS[unsearched.reason]
    assert "one of its values, or a form of a value" in described
    assert "as D compares values" in described
    assert "other values and forms are still searched" in described


@pytest.mark.deid_requirement("PS3.15-E.1.3-01")
def test_each_vr_described_as_not_searched_is_not_searched():
    described = conformance_values.unsearched_vrs()
    assert described[residuals.Omission.BINARY]
    assert described[residuals.Omission.NOT_DISTINCTIVE]
    source = ElementPath((), "(0009,1001)")
    for reason, vrs in described.items():
        for vr in vrs:
            value = residuals.SourceValue(source, vr, "SEARCHABLE VALUE 12345")
            (omitted,) = residuals.find_residuals(b"", [value]).not_searched
            assert omitted.reason is reason, vr
    searched = set(residuals._KINDS)  # pylint: disable = protected-access
    unsearched = set().union(*described.values())
    assert searched.isdisjoint(unsearched)
    assert searched | unsearched == set(standard.VRS) - {"SQ"}


@pytest.mark.deid_requirement("PS3.15-E.1.3-01", "MIDI-BP-18")
def test_the_release_report_names_sequestered_instances_by_label(preset):
    section = _section(preset, "Release report")
    assert f"`{release_report.FORMAT}`" in section
    (first,) = release_report.sequestration_labels(1)
    assert release_report.LABEL_PATTERN.fullmatch(first)
    assert f"from `{first}` to `S-n`" in section
    assert "order drawn at random" in section
    assert "(D-026)" in section
    stages = release_report._SEQUESTERING  # pylint: disable = protected-access
    assert set(conformance_values.STAGES) == set(stages)
    for stage, codes in stages.items():
        line = section.split(f"- `{stage}`: ", 1)[1].split(" - ", 1)[0]
        assert line.startswith(conformance_values.STAGES[stage])
        for reason in codes:
            assert f"`{reason}`" in line, (stage, reason)


@pytest.mark.deid_requirement("PS3.15-E.1.3-01", "MIDI-BP-18")
def test_the_release_report_counts_held_instances_by_stage(preset):
    section = _section(preset, "Release report")
    held = section.split("counts the instances held for review", 1)[1]
    stages = release_report._HOLDING  # pylint: disable = protected-access
    assert set(conformance_values.HOLDING_STAGES) == set(stages)
    assert "(D-009)" in held
    for stage, codes in stages.items():
        line = held.split(f"- `{stage}`: ", 1)[1].split(" - ", 1)[0]
        assert line.startswith(conformance_values.HOLDING_STAGES[stage])
        for reason in codes:
            assert f"`{reason}`" in line, (stage, reason)


@pytest.mark.deid_requirement("MIDI-BP-18")
def test_the_release_report_counts_roi_names_by_outcome(preset):
    section = _section(preset, "Release report")
    counted = section.split("counts the ROI Names", 1)[1].split("\n\n", 1)[0]
    assert "(D-009)" in counted
    assert "naming none of them" in counted
    for outcome in reviewed_roi_names.Outcome:
        assert f"`{outcome.value}`" in counted, outcome


@pytest.mark.deid_requirement("PS3.15-E.1.3-01", "MIDI-BP-18")
def test_every_reason_that_the_release_report_counts_is_described(preset):
    reasons = [*residuals.Omission, *residuals.UnsearchedReason]
    assert set(conformance_values.UNSEARCHED_REASONS) == set(residuals.UnsearchedReason)
    section = _section(preset, "Release report")
    assert "by attribute" in section
    assert "(D-027)" in section
    for reason in residuals.UnsearchedReason:
        assert (
            f"- `{reason.value}`: {conformance_values.UNSEARCHED_REASONS[reason]}."
            in section
        )
    # Each reason described is one that the release report accepts.
    coverage = release_report.search_coverage(
        [
            [residuals.Unsearched(ElementPath((), "(0010,0020)"), r)]
            for r in residuals.UnsearchedReason
        ]
    )
    counted = release_report.release_report(
        policy.compose_policy(preset),
        vocabulary=None,
        reviewed_roi_names=None,
        coverage=coverage,
    )
    document = release_report.report_document(counted)
    assert {e["reason"] for e in document["search_coverage"]} == {
        r.value for r in residuals.UnsearchedReason
    }
    for reason in reasons:
        assert f"`{reason.value}`" in section


@pytest.mark.deid_requirement("PS3.15-E.1.3-01")
def test_per_instance_detail_is_only_in_the_qc_pack(preset):
    section = _section(preset, "Release report")
    assert "no source value or original path" in section
    assert (
        "Only the confidential QC pack maps labels to source instances and lists "
        "each value not searched by instance and place (D-016)." in section
    )


@pytest.mark.deid_requirement("PS3.15-E.1.3-01")
def test_what_remains_of_the_release_report_is_pending(preset):
    statement = _statement(preset)
    pending = conformance.PENDING_RELEASE_REPORT
    assert pending in statement.pending
    for decision in ("D-016", "D-026", "D-027"):
        assert decision in pending
    assert "QC pack" in pending
    assert "search each written file" in pending
    assert "the run itself sequesters" in pending
    assert "staging area" in pending
    # How the report names a sequestered instance is now described.
    assert "how it names" not in pending
    assert not statement.claims_conformance
