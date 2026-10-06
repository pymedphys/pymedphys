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

"""The release report's reason codes, of each stage that sequesters or holds."""

import dataclasses

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import (
    descriptor_cleaning,
    policy,
    preservation,
    preserving_writer,
    qc_pack,
    reasons,
    reference_graph,
    release_gate,
    release_report,
    residuals,
    reviewed_roi_names,
    roi_names,
    scope,
    source,
    walker,
)
from pymedphys._dicom.deidentify.file_layout import ElementPath


@pytest.fixture(name="basic", scope="module")
def _basic():
    return policy.compose_policy("basic")


class _Text(str):
    pass


def _with(report, **changes):
    return dataclasses.replace(report, **changes)


def _instance(*causes, label="S-0001"):
    return release_report.SequesteredInstance(label, causes)


# The run refuses these inputs rather than sequestering them.
_REFUSING = (
    reasons.RunReason.SYMBOLIC_LINK,
    reasons.RunReason.NOT_A_REGULAR_FILE,
    reasons.RunReason.DICOMDIR,
    reasons.RunReason.UNREADABLE_FILE,
    reasons.RunReason.NOT_READABLE_AS_DICOM,
)

_SEQUESTERING = [
    *(
        (each, "scope")
        for each in scope.Disposition
        if each is not scope.Disposition.SUPPORTED
    ),
    *((each, "admission") for each in source.SourceReason),
    (reference_graph.FindingKind.MISSING_IDENTIFIER, "references"),
    (reference_graph.FindingKind.CONFLICTING_INSTANCE, "references"),
    (reference_graph.FindingKind.SERIES_IN_SEVERAL_STUDIES, "references"),
    *((each, "run") for each in reasons.RunReason if each not in _REFUSING),
    *((each, "transform") for each in reasons.TransformReason),
    *((each, "transform") for each in descriptor_cleaning.DescriptorReason),
    *((each, "writer") for each in preserving_writer.WriteReason),
    *((each, "verifier") for each in preservation.PreservationReason),
]


@pytest.mark.deid_requirement("MIDI-BP-18")
@pytest.mark.parametrize(
    "cause, stage", _SEQUESTERING, ids=[str(each) for each, _ in _SEQUESTERING]
)
def test_each_stage_that_sequesters_gives_its_reason_code(basic, cause, stage):
    reason = release_report.sequestration_reason(cause)

    assert (reason.stage, reason.code) == (stage, cause.value)
    assert (reason.attribute, reason.action, reason.vr) == (None, None, None)
    report = release_report.release_report(
        basic,
        vocabulary=None,
        reviewed_roi_names=None,
        sequestered=(release_report.SequesteredInstance("S-0001", (reason,)),),
    )
    assert release_report.report_document(report)["sequestered"][0]["reasons"] == [
        {"stage": stage, "code": cause.value}
    ]


@pytest.mark.parametrize("reason", list(walker.SequesterReason))
def test_each_walker_reason_is_written(basic, reason):
    cause = walker.Sequestration(ElementPath((), "(0010,0020)"), "X", None, reason)
    report = release_report.release_report(
        basic,
        vocabulary=None,
        reviewed_roi_names=None,
        sequestered=(
            release_report.SequesteredInstance(
                "S-0001", (release_report.sequestration_reason(cause),)
            ),
        ),
    )

    assert release_report.report_document(report)["sequestered"][0]["reasons"] == [
        {
            "stage": "walker",
            "code": reason.value,
            "attribute": "(0010,0020)",
            "action": "X",
            "vr": None,
        }
    ]


@pytest.mark.parametrize(
    "cause",
    [
        scope.Disposition.SUPPORTED,
        reference_graph.FindingKind.DANGLING_REFERENCE,
        reference_graph.FindingKind.DUPLICATE_INSTANCE,
        reference_graph.FindingKind.STUDY_WITH_SEVERAL_PATIENTS,
        *_REFUSING,
        descriptor_cleaning.HeldRoiName(
            ElementPath((), "(3006,0026)"), roi_names.Reason.UNMATCHED
        ),
        "SENTINEL",
    ],
)
def test_what_does_not_sequester_an_instance_is_not_a_reason(cause):
    # A study with several patients stops the run instead.
    with pytest.raises((TypeError, ValueError)) as raised:
        release_report.sequestration_reason(cause)

    assert "SENTINEL" not in str(raised.value)


@pytest.mark.deid_requirement("MIDI-BP-18")
def test_the_codes_of_each_stage_are_distinct():
    # A code names one reason of its stage, so no two enums that give a stage
    # its codes share a value.
    sources = {
        "run": (reasons.RunReason,),
        "transform": (reasons.TransformReason, descriptor_cleaning.DescriptorReason),
        "writer": (preserving_writer.WriteReason,),
        "verifier": (preservation.PreservationReason,),
        "release": (release_gate.ReasonCode,),
    }
    for stage, enums in sources.items():
        values = [each.value for enum in enums for each in enum]
        assert len(values) == len(set(values)), stage
        codes = release_report._SEQUESTERING  # pylint: disable = protected-access
        # Every member gives a code, except the run's that refuse an input.
        if stage == "run":
            assert codes[stage] == set(values) - {each.value for each in _REFUSING}
        else:
            assert codes[stage] == set(values), stage


def test_each_drop_reason_is_a_reason_that_coverage_counts():
    assert {each.value for each in qc_pack.DropReason} <= {
        each.value for each in residuals.UnsearchedReason
    }


@pytest.mark.deid_requirement("MIDI-BP-18")
@pytest.mark.parametrize(
    "path, place",
    [
        (None, None),
        (
            ElementPath((("(300A,00B0)", 0),), "(300A,00C2)"),
            "(300A,00B0) > (300A,00C2)",
        ),
    ],
)
def test_a_release_gate_reason_names_its_attribute_at_most(basic, path, place):
    cause = release_gate.ReleaseReason(
        release_gate.Decision.WITHHOLD,
        release_gate.ReasonCode.RESIDUAL_PERSON_NAME,
        path,
    )
    report = release_report.release_report(
        basic,
        vocabulary=None,
        reviewed_roi_names=None,
        sequestered=(_instance(release_report.sequestration_reason(cause)),),
    )

    expected = {"stage": "release", "code": "residual-person-name"}
    if place is not None:
        expected["attribute"] = place
    assert release_report.report_document(report)["sequestered"][0]["reasons"] == [
        expected
    ]


def test_a_release_reason_with_an_action_is_refused(basic):
    reason = dataclasses.replace(
        release_report.sequestration_reason(
            release_gate.ReleaseReason(
                release_gate.Decision.WITHHOLD, release_gate.ReasonCode.UNCOLLECTED
            )
        ),
        action="X",
    )
    report = release_report.release_report(
        basic,
        vocabulary=None,
        reviewed_roi_names=None,
        sequestered=(_instance(reason),),
    )

    with pytest.raises(release_report.ReleaseReportError, match="action"):
        release_report.report_document(report)


def _held_name(reason=roi_names.Reason.UNMATCHED, item=0):
    return descriptor_cleaning.HeldRoiName(
        ElementPath((("(3006,0020)", item),), "(3006,0026)"), reason
    )


def _qc_review(code=release_gate.ReasonCode.UNCOLLECTED):
    return release_gate.ReleaseReason(release_gate.Decision.QC_REVIEW, code)


@pytest.mark.deid_requirement("MIDI-BP-18")
def test_held_instances_are_counted_by_stage_and_reason_each_once(basic):
    held = release_report.held_for_review(
        [
            (_held_name(item=0), _held_name(item=1), _qc_review()),
            (_held_name(roi_names.Reason.AMBIGUOUS),),
            (_held_name(item=2),),
        ]
    )
    report = release_report.release_report(
        basic, vocabulary=None, reviewed_roi_names=None, held=held
    )

    assert release_report.report_document(report)["held_for_review"] == [
        {"stage": "release", "code": "uncollected", "count": 1},
        {"stage": "roi-names", "code": "ambiguous", "count": 1},
        {"stage": "roi-names", "code": "unmatched", "count": 2},
    ]


@pytest.mark.parametrize(
    "instances",
    [
        [_held_name()],
        [("SENTINEL",)],
        [
            (
                release_gate.ReleaseReason(
                    release_gate.Decision.WITHHOLD, release_gate.ReasonCode.UNCOLLECTED
                ),
            )
        ],
    ],
    ids=["not-by-instance", "unknown", "withheld"],
)
def test_held_reasons_must_be_given_by_instance_and_known(instances):
    with pytest.raises(TypeError) as raised:
        release_report.held_for_review(instances)

    assert "SENTINEL" not in str(raised.value)


@pytest.mark.deid_requirement("MIDI-BP-18")
@pytest.mark.parametrize(
    "held",
    [
        ("SENTINEL",),
        (release_report.HeldForReview("SENTINEL", "unmatched", 1),),
        (release_report.HeldForReview("roi-names", "SENTINEL", 1),),
        (release_report.HeldForReview("roi-names", "unmatched", 0),),
        (release_report.HeldForReview("roi-names", "unmatched", True),),
        (release_report.HeldForReview("roi-names", _Text("unmatched"), 1),),
        (release_report.HeldForReview("release", "unmatched", 1),),
    ],
    ids=[
        "not-a-count",
        "stage",
        "code",
        "zero-count",
        "boolean-count",
        "code-subclass",
        "code-of-another-stage",
    ],
)
def test_a_held_section_that_could_hold_a_value_is_refused(basic, held):
    report = _with(
        release_report.release_report(basic, vocabulary=None, reviewed_roi_names=None),
        held_for_review=held,
    )

    for write in (release_report.report_document, release_report.to_json):
        with pytest.raises(
            release_report.ReleaseReportError, match="held_for_review"
        ) as raised:
            write(report)
        assert "SENTINEL" not in str(raised.value)
        assert raised.value.__cause__ is None


_KEPT = reviewed_roi_names.Outcome.KEPT
_UNMATCHED = roi_names.Reason.UNMATCHED


@pytest.mark.deid_requirement("PS3.15-E.3.5-01", "MIDI-BP-18")
def test_roi_names_are_counted_by_outcome_and_held_names_by_reason(basic):
    counts = reviewed_roi_names.RoiNameCounts(
        held={_UNMATCHED: 2, roi_names.Reason.ECHOES_IDENTIFIER: 1},
        outcomes={
            reviewed_roi_names.Outcome.RENAMED: 5,
            _KEPT: 3,
            reviewed_roi_names.Outcome.HELD: 2,
            reviewed_roi_names.Outcome.EMPTIED_UNREVIEWED: 1,
        },
    )
    report = release_report.release_report(
        basic, vocabulary=None, reviewed_roi_names=None, roi_names=counts
    )

    # Sorted by code, as every other count of the report is, and without a
    # name: only the confidential QC pack lists the names.
    assert release_report.report_document(report)["roi_names"] == {
        "outcomes": [
            {"outcome": "emptied unreviewed", "count": 1},
            {"outcome": "held", "count": 2},
            {"outcome": "kept", "count": 3},
            {"outcome": "renamed", "count": 5},
        ],
        "held": [
            {"reason": "echoes identifier", "count": 1},
            {"reason": "unmatched", "count": 2},
        ],
    }


@pytest.mark.deid_requirement("PS3.15-E.3.5-01", "MIDI-BP-18")
def test_a_run_without_roi_names_counts_none(basic):
    report = release_report.release_report(
        basic, vocabulary=None, reviewed_roi_names=None
    )

    assert report.roi_names == reviewed_roi_names.RoiNameCounts({}, {})
    assert release_report.report_document(report)["roi_names"] == {
        "outcomes": [],
        "held": [],
    }


def _roi_name_counts_with(field, value):
    counts = reviewed_roi_names.RoiNameCounts({}, {})
    object.__setattr__(counts, field, value)
    return counts


@pytest.mark.deid_requirement("PS3.15-E.3.5-01", "MIDI-BP-18")
@pytest.mark.parametrize(
    "counts",
    [
        _roi_name_counts_with("held", 42),
        _roi_name_counts_with("outcomes", ["SENTINEL"]),
        "SENTINEL",
        reviewed_roi_names.RoiNameCounts({}, {"SENTINEL": 1}),
        reviewed_roi_names.RoiNameCounts({"SENTINEL": 1}, {}),
        reviewed_roi_names.RoiNameCounts({}, {_UNMATCHED: 1}),
        reviewed_roi_names.RoiNameCounts({_KEPT: 1}, {}),
        reviewed_roi_names.RoiNameCounts({}, {_KEPT: True}),
        reviewed_roi_names.RoiNameCounts({_UNMATCHED: 1.5}, {}),
    ],
    ids=[
        "held-not-a-mapping",
        "outcomes-not-a-mapping",
        "not-counts",
        "outcome",
        "reason",
        "reason-as-outcome",
        "outcome-as-reason",
        "boolean-count",
        "fractional-count",
    ],
)
def test_roi_name_counts_that_could_hold_a_value_are_refused(basic, counts):
    report = _with(
        release_report.release_report(basic, vocabulary=None, reviewed_roi_names=None),
        roi_names=counts,
    )

    for write in (release_report.report_document, release_report.to_json):
        with pytest.raises(
            release_report.ReleaseReportError, match="roi_names"
        ) as raised:
            write(report)
        assert "SENTINEL" not in str(raised.value)
        assert raised.value.__cause__ is None


_DANGLING = reference_graph.FindingKind.DANGLING_REFERENCE
_ACTED_ON = (
    reference_graph.FindingKind.MISSING_IDENTIFIER,
    reference_graph.FindingKind.DUPLICATE_INSTANCE,
    reference_graph.FindingKind.CONFLICTING_INSTANCE,
    reference_graph.FindingKind.SERIES_IN_SEVERAL_STUDIES,
    reference_graph.FindingKind.STUDY_WITH_SEVERAL_PATIENTS,
)


@pytest.mark.deid_requirement("MIDI-BP-03")
def test_every_finding_the_run_does_not_act_on_is_reported():
    assert release_report.REPORTED_FINDINGS == frozenset(
        reference_graph.FindingKind
    ) - frozenset(_ACTED_ON)
    assert _DANGLING in release_report.REPORTED_FINDINGS
    # The findings that sequester an instance are given as its reasons.
    sequestering = release_report._SEQUESTERING  # pylint: disable = protected-access
    reported = {kind.value for kind in release_report.REPORTED_FINDINGS}
    assert not reported & sequestering["references"]


@pytest.mark.deid_requirement("MIDI-BP-03", "MIDI-BP-18")
def test_reference_findings_count_each_instance_once_for_each_kind(basic):
    found = release_report.reference_findings([[_DANGLING, _DANGLING], [], [_DANGLING]])
    report = release_report.release_report(
        basic, vocabulary=None, reviewed_roi_names=None, findings=found
    )

    assert found == (release_report.ReferenceFindings("dangling-reference", 2),)
    assert release_report.report_document(report)["reference_findings"] == [
        {"kind": "dangling-reference", "count": 2}
    ]


def test_a_run_without_reference_findings_counts_none(basic):
    report = release_report.release_report(
        basic, vocabulary=None, reviewed_roi_names=None
    )

    assert release_report.report_document(report)["reference_findings"] == []


@pytest.mark.parametrize(
    "instances",
    [[_DANGLING], *([[kind]] for kind in _ACTED_ON), [["dangling-reference"]]],
    ids=["not-by-instance", *(kind.value for kind in _ACTED_ON), "a-string"],
)
def test_reference_findings_must_be_given_by_instance_and_reported_only(instances):
    with pytest.raises(TypeError):
        release_report.reference_findings(instances)


@pytest.mark.deid_requirement("MIDI-BP-03", "MIDI-BP-18")
@pytest.mark.parametrize(
    "found",
    [
        "SENTINEL",
        ("SENTINEL",),
        (release_report.ReferenceFindings("SENTINEL", 1),),
        (release_report.ReferenceFindings("missing-identifier", 1),),
        (release_report.ReferenceFindings(_DANGLING, 1),),
        (release_report.ReferenceFindings("dangling-reference", 0),),
        (release_report.ReferenceFindings("dangling-reference", True),),
        (release_report.ReferenceFindings("dangling-reference", 1.0),),
        (
            release_report.ReferenceFindings("dangling-reference", 1),
            release_report.ReferenceFindings("dangling-reference", 1),
        ),
    ],
    ids=[
        "not-a-tuple",
        "not-counts",
        "unknown-kind",
        "acted-on-kind",
        "kind-as-enum",
        "zero-count",
        "boolean-count",
        "fractional-count",
        "counted-twice",
    ],
)
def test_reference_finding_counts_that_could_hold_a_value_are_refused(basic, found):
    report = _with(
        release_report.release_report(basic, vocabulary=None, reviewed_roi_names=None),
        reference_findings=found,
    )

    for write in (release_report.report_document, release_report.to_json):
        with pytest.raises(
            release_report.ReleaseReportError, match="reference_findings"
        ) as raised:
            write(report)
        assert "SENTINEL" not in str(raised.value)
        assert raised.value.__cause__ is None
