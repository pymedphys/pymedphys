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

"""Tests of the release report that a run publishes with its release.

Every input is synthetic.
"""

import json
import os

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import (
    output_names,
    qc_pack,
    release_gate,
    release_report,
    run,
    run_qc,
)
from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.instance_transform import (
    InstanceTransform,
    ReleaseGate,
)
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.policy import compose_policy
from pymedphys._dicom.deidentify.reasons import RunReason, TransformReason
from pymedphys._dicom.deidentify.reference_graph import FindingKind
from pymedphys._dicom.deidentify.residuals import (
    Form,
    NotSearched,
    Omission,
    ResidualSearch,
    Unsearched,
    UnsearchedReason,
)
from pymedphys._dicom.deidentify.run_report import (
    HELD_FOR_REVIEW,
    RELEASE_REPORT,
    SEQUESTERED,
    ReleaseReporter,
    coverage_records,
    held_instances,
)

from . import _synthetic_references as synthetic
from .test_deidentify_run import Gate, GateReason, Transform, _listing, _write

# The run module's fixture, for a base directory short enough for Windows.
from .test_deidentify_run import (  # noqa: F401  # pylint: disable = unused-import
    _short_tmp_path,
)

KEY = DeidKey(bytes(range(32)))


def _reporter():
    return ReleaseReporter(compose_policy("basic"), vocabulary=None)


def _run(tmp_path, transform, gate, reporter):
    return run.run(
        run.discover(tmp_path / "source"),
        tmp_path / "release",
        transform,
        gate,
        qc_destination=tmp_path / "qc",
        reporter=reporter,
    )


@pytest.mark.pydicom
def test_a_run_publishes_its_release_report_naming_no_value(tmp_path):
    _write(tmp_path / "source", synthetic.collection())
    transform = InstanceTransform(compose_policy("basic"), KEY, unvalidated_policy=True)

    result = _run(tmp_path, transform, ReleaseGate(), transform.reporter)

    assert [outcome.status for outcome in result.outcomes] == [run.Status.RELEASED] * 6
    text = (tmp_path / "release" / RELEASE_REPORT).read_text(encoding="utf-8")
    document = json.loads(text)
    assert document["format"] == release_report.FORMAT
    assert document["policy"]["preset"] == "basic"
    assert document["sequestered"] == []
    reasons = {entry["reason"] for entry in document["search_coverage"]}
    assert {"retained", "registered-uid"} <= reasons
    for value in (synthetic.PATIENT_ID, synthetic.PATIENTS_NAME, str(tmp_path)):
        assert value not in text


@pytest.mark.pydicom
def test_the_report_names_each_sequestered_input_by_its_label(tmp_path):
    datasets = synthetic.collection()
    conflicting = synthetic.ct_slice(0)
    conflicting.SliceThickness = "2.5"
    _write(tmp_path / "source", [*datasets, conflicting])

    result = _run(tmp_path, Transform(), Gate(), _reporter())

    labels = sorted(o.label for o in result.outcomes if o.label is not None)
    document = json.loads((tmp_path / "release" / RELEASE_REPORT).read_text())
    assert [entry["label"] for entry in document["sequestered"]] == labels
    assert labels == ["S-0001", "S-0002"]
    assert all(
        entry["reasons"]
        == [{"stage": "references", "code": FindingKind.CONFLICTING_INSTANCE.value}]
        for entry in document["sequestered"]
    )


class _FailingReporter:
    def admits(self, status, reasons):  # pylint: disable = unused-argument
        return True

    def __call__(self, outcomes, material):
        raise ValueError("no report")


@pytest.mark.pydicom
def test_a_report_that_cannot_be_written_publishes_nothing(tmp_path):
    _write(tmp_path / "source", synthetic.collection()[:1])

    with pytest.raises(ValueError, match="no report"):
        _run(tmp_path, Transform(), Gate(), _FailingReporter())

    assert _listing(tmp_path) == ["source"]


_WITHHOLD = release_gate.ReleaseReason(
    release_gate.Decision.WITHHOLD, release_gate.ReasonCode.UNCOLLECTED
)


@pytest.mark.pydicom
@pytest.mark.parametrize(
    "verdict",
    [
        # No stage of the report gives the stand-in gate's reason.
        run.Sequestered((GateReason.TEXT_FINDING,)),
        run.HoldForReview((GateReason.TEXT_FINDING,)),
        # A held instance's gate reasons require QC review, never withholding.
        run.HoldForReview((_WITHHOLD,)),
        run.HoldForReview((TransformReason.UNMARKABLE,)),
    ],
    ids=["sequestered", "held", "held-withheld", "held-for-a-transform-reason"],
)
def test_an_input_whose_reasons_cannot_be_reported_is_sequestered_alone(
    tmp_path, verdict
):
    datasets = synthetic.collection()[:2]
    _write(tmp_path / "source", datasets)
    gate = Gate({b"OUTPUT " + datasets[0].SOPInstanceUID.encode(): verdict})

    result = _run(tmp_path, Transform(), gate, _reporter())

    withheld = [o for o in result.outcomes if o.status is not run.Status.RELEASED]
    assert [(o.status, o.reasons) for o in withheld] == [
        (run.Status.SEQUESTERED, (RunReason.INVALID_REASON,))
    ]
    document = json.loads((tmp_path / "release" / RELEASE_REPORT).read_text())
    assert document["sequestered"] == [
        {
            "label": "S-0001",
            "reasons": [{"stage": "run", "code": "invalid-reason"}],
        }
    ]
    assert document["held_for_review"] == []


def test_the_reporter_admits_only_reasons_it_can_report():
    reporter = _reporter()
    review = release_gate.ReleaseReason(
        release_gate.Decision.QC_REVIEW, release_gate.ReasonCode.UNCOLLECTED
    )

    assert reporter.admits(SEQUESTERED, (_WITHHOLD, FindingKind.CONFLICTING_INSTANCE))
    assert reporter.admits(HELD_FOR_REVIEW, (review,))
    assert not reporter.admits(HELD_FOR_REVIEW, (_WITHHOLD,))
    assert not reporter.admits(SEQUESTERED, (RunReason.SYMBOLIC_LINK,))
    assert not reporter.admits(SEQUESTERED, ())
    assert not reporter.admits(SEQUESTERED, [_WITHHOLD])
    assert not reporter.admits("released", (_WITHHOLD,))
    assert run.Status.SEQUESTERED.value == SEQUESTERED


@pytest.mark.pydicom
def test_without_a_reporter_no_report_is_written(tmp_path):
    _write(tmp_path / "source", synthetic.collection()[:1])

    _run(tmp_path, Transform(), Gate(), None)

    assert not os.path.lexists(tmp_path / "release" / RELEASE_REPORT)


def test_coverage_records_follow_the_drops_and_the_search():
    place = ElementPath((), "(0010,0010)")
    omission = NotSearched(place, "PN", Form.VALUE, Omission.TOO_SHORT)
    search = ResidualSearch((), (omission,), True)

    records = coverage_records(
        (
            run_qc.Dropped(place, qc_pack.DropReason.WRITTEN_CONSTANT),
            run_qc.SearchMaterial(search, b""),
        )
    )

    assert records == [
        Unsearched(place, UnsearchedReason.WRITTEN_CONSTANT),
        omission,
    ]


def test_the_reporter_shows_nothing_and_refuses_a_policy_it_cannot_record():
    assert repr(_reporter()) == "ReleaseReporter()"
    with pytest.raises(TypeError):
        ReleaseReporter("basic", vocabulary=None)


@pytest.mark.pydicom
def test_the_report_counts_held_inputs_by_reason_without_naming_them(tmp_path):
    datasets = synthetic.collection()[:2]
    _write(tmp_path / "source", datasets)
    review = release_gate.ReleaseReason(
        release_gate.Decision.QC_REVIEW,
        release_gate.ReasonCode.READ_AS_LATIN_1,
        ElementPath((), "(0008,103E)"),
    )
    gate = Gate(
        {
            b"OUTPUT " + each.SOPInstanceUID.encode(): run.HoldForReview((review,))
            for each in datasets
        }
    )

    result = _run(tmp_path, Transform(), gate, _reporter())

    assert [o.status for o in result.outcomes] == [run.Status.HELD_FOR_REVIEW] * 2
    document = json.loads((tmp_path / "release" / RELEASE_REPORT).read_text())
    assert document["sequestered"] == []
    assert document["held_for_review"] == [
        {"stage": "release", "code": "read-as-latin-1", "count": 2}
    ]


def test_only_held_outcomes_are_counted():
    review = release_gate.ReleaseReason(
        release_gate.Decision.QC_REVIEW, release_gate.ReasonCode.UNCOLLECTED
    )
    outcomes = [
        run.Outcome(0, run.Status.HELD_FOR_REVIEW, (review,)),
        run.Outcome(1, run.Status.SEQUESTERED, (review,)),
        run.Outcome(2, run.Status.RELEASED),
    ]

    assert held_instances(outcomes) == (
        release_report.HeldForReview("release", "uncollected", 1),
    )
    assert run.Status.HELD_FOR_REVIEW.value == HELD_FOR_REVIEW


@pytest.mark.parametrize("name", [RELEASE_REPORT, RELEASE_REPORT.upper()])
def test_no_output_name_is_the_release_report(name):
    # The first part of every output's path is a pseudonymous Patient ID, so
    # even a file system that ignores case cannot confuse one with the report.
    pattern = output_names._PATIENT_ID  # pylint: disable = protected-access
    assert pattern.fullmatch(name) is None
    assert pattern.fullmatch(name.casefold()) is None
