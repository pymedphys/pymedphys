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

"""The release report's record of the release gate and of instances held for review."""

import dataclasses

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import (
    descriptor_cleaning,
    policy,
    release_gate,
    release_report,
    roi_names,
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
