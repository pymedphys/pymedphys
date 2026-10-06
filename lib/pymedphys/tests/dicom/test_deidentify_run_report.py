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
import subprocess
import sys
import types

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import (
    conformance,
    conformance_markdown,
    output_names,
    qc_pack,
    release_gate,
    release_report,
    run,
    run_qc,
    run_report,
)
from pymedphys._dicom.deidentify.descriptor_cleaning import HeldRoiName
from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.iod_conformance import SourceGap
from pymedphys._dicom.deidentify.instance_transform import (
    InstanceTransform,
    ReleaseGate,
)
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.policy import compose_policy
from pymedphys._dicom.deidentify.reasons import RunReason, TransformReason
from pymedphys._dicom.deidentify.reviewed_roi_names import Outcome, RoiNameCounts
from pymedphys._dicom.deidentify.roi_names import Reason
from pymedphys._dicom.deidentify.reference_graph import Finding, FindingKind
from pymedphys._dicom.deidentify.residuals import (
    Form,
    NotSearched,
    Omission,
    ResidualSearch,
    Unsearched,
    UnsearchedReason,
)
from pymedphys._dicom.deidentify.release_report_markdown import (
    ReleaseReportMarkdownError,
    to_markdown,
)
from pymedphys._dicom.deidentify.run_report import (
    CONFORMANCE_STATEMENT,
    HELD_FOR_REVIEW,
    RELEASE_REPORT,
    RELEASE_REPORT_MARKDOWN,
    SEQUESTERED,
    ReleaseReporter,
    coverage_records,
    held_instances,
    release_files,
    roi_name_counts,
)
from pymedphys._dicom.deidentify.walker import SequesterReason, Sequestration
from pymedphys._dicom.deidentify.written_references import (
    WrittenFinding,
    WrittenFindingKind,
)

from . import _synthetic_references as synthetic
from .test_deidentify_run import PLAN, Gate, GateReason, Transform, _listing, _write

# The run module's fixture, for a base directory short enough for Windows.
from .test_deidentify_run import (  # noqa: F401  # pylint: disable = unused-import
    _short_tmp_path,
)

KEY = DeidKey(bytes(range(32)))


def _reporter():
    return ReleaseReporter(
        compose_policy("basic"), vocabulary=None, reviewed_roi_names=None
    )


def _run(tmp_path, transform, gate, reporter):
    return run.run(
        run.discover(tmp_path / "source"),
        tmp_path / "release",
        transform,
        gate,
        qc_destination=tmp_path / "qc",
        reporter=reporter,
    )


@pytest.mark.deid_requirement("MIDI-BP-18")
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


@pytest.mark.deid_requirement("MIDI-BP-18")
@pytest.mark.pydicom
def test_a_run_publishes_the_reports_human_readable_form_beside_it(tmp_path):
    _write(tmp_path / "source", synthetic.collection())
    transform = InstanceTransform(compose_policy("basic"), KEY, unvalidated_policy=True)

    _run(tmp_path, transform, ReleaseGate(), transform.reporter)

    text = (tmp_path / "release" / RELEASE_REPORT).read_text(encoding="utf-8")
    markdown = (tmp_path / "release" / RELEASE_REPORT_MARKDOWN).read_text(
        encoding="utf-8"
    )
    assert markdown == to_markdown(text)
    assert RELEASE_REPORT in markdown
    for value in (synthetic.PATIENT_ID, synthetic.PATIENTS_NAME, str(tmp_path)):
        assert value not in markdown


def test_the_release_files_are_the_report_and_its_form_from_it_alone():
    text = release_report.to_json(
        release_report.release_report(
            compose_policy("basic"), vocabulary=None, reviewed_roi_names=None
        )
    )
    assert release_files(text) == {
        RELEASE_REPORT: text.encode("utf-8"),
        RELEASE_REPORT_MARKDOWN: to_markdown(text).encode("utf-8"),
    }
    assert release_files(text, statement="# Statement\n") == {
        RELEASE_REPORT: text.encode("utf-8"),
        RELEASE_REPORT_MARKDOWN: to_markdown(text).encode("utf-8"),
        CONFORMANCE_STATEMENT: b"# Statement\n",
    }


@pytest.mark.deid_requirement("MIDI-BP-18")
@pytest.mark.pydicom
def test_the_report_lists_released_inputs_and_its_qc_pack_not_yet_attested(tmp_path):
    datasets = synthetic.collection()
    _write(tmp_path / "source", [*datasets, datasets[0]])

    result = _run(tmp_path, Transform(), Gate(), _reporter())

    statuses = [outcome.status for outcome in result.outcomes]
    assert statuses == [run.Status.RELEASED] * 6 + [run.Status.DUPLICATE]
    document = json.loads((tmp_path / "release" / RELEASE_REPORT).read_text())
    assert document["released"] == sorted(
        str(outcome.output) for outcome in result.outcomes[:6]
    )
    pack = json.loads(result.qc_pack.read_text(encoding="utf-8"))
    assert document["qc_review"] == {
        "reference": pack["reference"],
        "outcome": "not-attested",
        "intended_use_checked": None,
        "residual_risk_accepted": None,
    }


@pytest.mark.deid_requirement("MIDI-BP-18")
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

    def __call__(self, outcomes, material, _qc_pack):
        raise ValueError("no report")


@pytest.mark.deid_requirement("MIDI-BP-18")
@pytest.mark.pydicom
def test_a_report_that_cannot_be_written_publishes_nothing(tmp_path):
    _write(tmp_path / "source", synthetic.collection()[:1])

    with pytest.raises(ValueError, match="no report"):
        _run(tmp_path, Transform(), Gate(), _FailingReporter())

    assert _listing(tmp_path) == ["source"]


class _UnreadableReporter:
    def admits(self, status, reasons):  # pylint: disable = unused-argument
        return True

    def __call__(self, outcomes, material, _qc_pack):
        return "{}"

    def conformance_statement(self):
        return "# Statement\n"


@pytest.mark.deid_requirement("MIDI-BP-18")
@pytest.mark.pydicom
def test_a_report_whose_form_cannot_be_generated_publishes_nothing(tmp_path):
    _write(tmp_path / "source", synthetic.collection()[:1])

    with pytest.raises(ReleaseReportMarkdownError):
        _run(tmp_path, Transform(), Gate(), _UnreadableReporter())

    assert _listing(tmp_path) == ["source"]


_WITHHOLD = release_gate.ReleaseReason(
    release_gate.Decision.WITHHOLD, release_gate.ReasonCode.UNCOLLECTED
)


@pytest.mark.deid_requirement("MIDI-BP-18")
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
    # Its own reasons follow, so that the QC pack keeps them.
    assert [(o.status, o.reasons) for o in withheld] == [
        (run.Status.SEQUESTERED, (RunReason.INVALID_REASON, *verdict.reasons))
    ]
    pack = json.loads(result.qc_pack.read_text(encoding="utf-8"))
    (entry,) = [each for each in pack["instances"] if each["position"] == 0]
    assert len(entry["reasons"]) == 2
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
    # Reasons of a known type whose fields are not as it says, which the
    # report could not write, are refused here rather than failing the run.
    walker = Sequestration(
        ElementPath((), "(0010,0010)"),
        "Q",
        "ZZ",
        SequesterReason.UNSUPPORTED_CHARACTER_SET,
    )
    assert not reporter.admits(SEQUESTERED, (walker,))
    assert not reporter.admits(
        SEQUESTERED, (Sequestration(None, "X", "PN", "not-a-reason"),)
    )
    assert not reporter.admits(HELD_FOR_REVIEW, (HeldRoiName(None, "unmatched"),))


@pytest.mark.deid_requirement("MIDI-BP-18")
def test_an_input_sequestered_for_its_reasons_keeps_whose_copy_it_is():
    held = run.Outcome(0, run.Status.HELD_FOR_REVIEW, (GateReason.TEXT_FINDING,))
    copy = run.Outcome(
        1, run.Status.HELD_FOR_REVIEW, (GateReason.TEXT_FINDING,), duplicate_of=0
    )

    # pylint: disable = protected-access
    admitted = run._admitted((held, copy), _reporter())

    assert [(o.status, o.duplicate_of) for o in admitted] == [
        (run.Status.SEQUESTERED, None),
        (run.Status.SEQUESTERED, 0),
    ]


@pytest.mark.pydicom
def test_without_a_reporter_no_report_is_written(tmp_path):
    _write(tmp_path / "source", synthetic.collection()[:1])

    _run(tmp_path, Transform(), Gate(), None)

    assert not os.path.lexists(tmp_path / "release" / RELEASE_REPORT)
    assert not os.path.lexists(tmp_path / "release" / CONFORMANCE_STATEMENT)


@pytest.mark.deid_requirement("PS3.15-E.1.3-01", "MIDI-BP-18")
@pytest.mark.pydicom
def test_a_run_publishes_the_conformance_statement_of_its_policy(tmp_path):
    _write(tmp_path / "source", synthetic.collection())
    policy = compose_policy("basic")
    transform = InstanceTransform(policy, KEY, unvalidated_policy=True)

    _run(tmp_path, transform, ReleaseGate(), transform.reporter)

    text = (tmp_path / "release" / CONFORMANCE_STATEMENT).read_text(encoding="utf-8")
    expected = conformance.conformance_statement(policy, vocabulary=None)
    assert text == conformance_markdown.render_markdown(expected)
    assert text == transform.reporter.conformance_statement()
    for value in (synthetic.PATIENT_ID, synthetic.PATIENTS_NAME, str(tmp_path)):
        assert value not in text
    document = json.loads((tmp_path / "release" / RELEASE_REPORT).read_text())
    # The statement describes the policy whose digest the report records.
    assert expected.method_digest == document["method"]["method_digest"]


class _StatementlessReporter:
    def __init__(self):
        self._reporter = _reporter()

    def admits(self, status, reasons):
        return self._reporter.admits(status, reasons)

    def __call__(self, outcomes, material, reference):
        return self._reporter(outcomes, material, reference)

    def conformance_statement(self):
        raise ValueError("no statement")


@pytest.mark.deid_requirement("PS3.15-E.1.3-01", "MIDI-BP-18")
@pytest.mark.pydicom
def test_a_statement_that_cannot_be_written_publishes_nothing(tmp_path):
    _write(tmp_path / "source", synthetic.collection()[:1])

    with pytest.raises(ValueError, match="no statement"):
        _run(tmp_path, Transform(), Gate(), _StatementlessReporter())

    assert _listing(tmp_path) == ["source"]


def test_coverage_records_follow_the_drops_and_the_search():
    place = ElementPath((), "(0010,0010)")
    omission = NotSearched(place, "PN", Form.VALUE, Omission.TOO_SHORT)
    search = ResidualSearch((), (omission,), True)

    own = NotSearched(place, "PN", Form.VALUE, Omission.BINARY)

    records = coverage_records(
        (
            run_qc.Dropped(place, qc_pack.DropReason.WRITTEN_CONSTANT),
            own,
            run_qc.SearchMaterial(search, b""),
        )
    )

    assert records == [
        Unsearched(place, UnsearchedReason.WRITTEN_CONSTANT),
        own,
        omission,
    ]


def _roi_name(item, source, outcome, held_because=None):
    return run_qc.RoiNameMaterial(
        ElementPath((("(3006,0020)", item),), "(3006,0026)"),
        source,
        outcome,
        held_because,
        None if outcome is Outcome.HELD else source,
    )


# Two structure sets' QC material: the second holds the first's held name
# again, with its padding, and a name that the run kept.
_ROI_MATERIAL = {
    0: (
        _roi_name(0, "Lung_L", Outcome.RENAMED),
        _roi_name(1, "SENTINEL", Outcome.HELD, Reason.UNMATCHED),
        run_qc.Dropped(ElementPath((), "(0010,0010)"), qc_pack.DropReason.RETAINED),
    ),
    3: (
        _roi_name(0, "SENTINEL ", Outcome.HELD, Reason.UNMATCHED),
        _roi_name(1, "Heart", Outcome.KEPT),
        run_qc.RetainedText("Heart", ElementPath((), "(3006,0026)")),
    ),
}


@pytest.mark.deid_requirement("PS3.15-E.3.5-01", "MIDI-BP-18")
def test_roi_names_are_counted_from_each_structure_sets_qc_material():
    # Every name counts by its outcome, at the structure set that holds it;
    # a held name counts once for each reason, however many structure sets
    # hold it, as the QC pack lists it once.
    assert roi_name_counts(_ROI_MATERIAL) == RoiNameCounts(
        held={Reason.UNMATCHED: 1},
        outcomes={Outcome.RENAMED: 1, Outcome.HELD: 2, Outcome.KEPT: 1},
    )
    assert roi_name_counts({}) == RoiNameCounts({}, {})


@pytest.mark.deid_requirement("PS3.15-E.3.5-01", "MIDI-BP-18")
def test_the_report_counts_the_runs_roi_names_without_naming_them():
    text = _reporter()((), _ROI_MATERIAL, "A-" + "0" * 32)

    assert json.loads(text)["roi_names"] == {
        "outcomes": [
            {"outcome": "held", "count": 2},
            {"outcome": "kept", "count": 1},
            {"outcome": "renamed", "count": 1},
        ],
        "held": [{"reason": "unmatched", "count": 1}],
    }
    for name in ("SENTINEL", "Heart", "Lung_L"):
        assert name not in text


@pytest.mark.deid_requirement("MIDI-BP-03", "MIDI-BP-18")
@pytest.mark.pydicom
def test_a_dangling_reference_is_counted_in_the_report_and_listed_in_the_pack(
    tmp_path,
):
    datasets = synthetic.collection()
    datasets[PLAN].ReferencedDoseSequence = [
        synthetic.reference(synthetic.RT_DOSE_STORAGE, "2.25.999")
    ]
    _write(tmp_path / "source", datasets)
    transform = InstanceTransform(compose_policy("basic"), KEY, unvalidated_policy=True)

    result = _run(tmp_path, transform, ReleaseGate(), transform.reporter)

    # The instance is written as usual.
    assert [outcome.status for outcome in result.outcomes] == [run.Status.RELEASED] * 6
    text = (tmp_path / "release" / RELEASE_REPORT).read_text(encoding="utf-8")
    assert json.loads(text)["reference_findings"] == [
        {"kind": "dangling-reference", "count": 1}
    ]
    assert "2.25.999" not in text
    checks = json.loads(text)["structural_checks"]
    assert checks[0] == {"check": "references", "sequestered": 0, "reported": 1}
    assert [entry["sequestered"] for entry in checks] == [0, 0, 0]
    pack = json.loads(result.qc_pack.read_text(encoding="utf-8"))
    assert pack["reference_findings"] == [
        {
            "position": PLAN,
            "kind": "dangling-reference",
            "attribute": "(300C,0080) > (0008,1155)",
            "count": 1,
        }
    ]


@pytest.mark.deid_requirement("MIDI-BP-03", "MIDI-BP-18")
@pytest.mark.pydicom
def test_a_dangling_reference_at_an_identical_copy_counts_once(tmp_path):
    datasets = synthetic.collection()
    datasets[PLAN].ReferencedDoseSequence = [
        synthetic.reference(synthetic.RT_DOSE_STORAGE, "2.25.999")
    ]
    _write(tmp_path / "source", [*datasets, datasets[PLAN]])
    transform = InstanceTransform(compose_policy("basic"), KEY, unvalidated_policy=True)

    result = _run(tmp_path, transform, ReleaseGate(), transform.reporter)

    assert result.outcomes[-1].duplicate_of == PLAN
    text = (tmp_path / "release" / RELEASE_REPORT).read_text(encoding="utf-8")
    assert json.loads(text)["reference_findings"] == [
        {"kind": "dangling-reference", "count": 1}
    ]
    pack = json.loads(result.qc_pack.read_text(encoding="utf-8"))
    assert [entry["position"] for entry in pack["reference_findings"]] == [
        PLAN,
        len(datasets),
    ]


@pytest.mark.deid_requirement("MIDI-BP-03", "MIDI-BP-17")
@pytest.mark.pydicom
def test_an_identical_copy_of_a_sequestered_input_is_counted_once(tmp_path):
    datasets = synthetic.collection()
    del datasets[PLAN].SeriesInstanceUID
    _write(tmp_path / "source", [*datasets, datasets[PLAN]])
    transform = InstanceTransform(compose_policy("basic"), KEY, unvalidated_policy=True)

    result = _run(tmp_path, transform, ReleaseGate(), transform.reporter)

    assert result.outcomes[-1].duplicate_of == PLAN
    document = json.loads(
        (tmp_path / "release" / RELEASE_REPORT).read_text(encoding="utf-8")
    )
    # The copy has a label of its own, but it is the same instance.
    assert len(document["sequestered"]) == 2
    assert document["structural_checks"][0] == {
        "check": "references",
        "sequestered": 1,
        "reported": 0,
    }


@pytest.mark.deid_requirement("MIDI-BP-03")
def test_the_run_acts_on_every_finding_that_it_does_not_report_only():
    acted_on = {
        *run._SEQUESTERING_FINDINGS,  # pylint: disable = protected-access
        FindingKind.STUDY_WITH_SEVERAL_PATIENTS,
        FindingKind.DUPLICATE_INSTANCE,
    }
    assert release_report.REPORTED_FINDINGS == frozenset(FindingKind) - acted_on


@pytest.mark.deid_requirement("MIDI-BP-03")
def test_each_reported_finding_is_added_once_to_each_input_it_names():
    kept = object()
    findings = (
        Finding(
            FindingKind.DANGLING_REFERENCE, ((2,),), ("(300C,0080)", "(0008,1155)"), 1
        ),
        Finding(FindingKind.DANGLING_REFERENCE, ((1, 2), (2, 3)), ("(0020,0052)",)),
        Finding(FindingKind.MISSING_IDENTIFIER, ((0,),), ("(0008,0018)",)),
    )

    added = run_qc.with_reported_findings({2: (kept,), 4: ()}, findings)

    first = run_qc.ReferenceFindingMaterial(
        FindingKind.DANGLING_REFERENCE, ("(300C,0080)", "(0008,1155)"), 1
    )
    second = run_qc.ReferenceFindingMaterial(
        FindingKind.DANGLING_REFERENCE, ("(0020,0052)",)
    )
    assert added == {1: (second,), 2: (kept, first, second), 3: (second,), 4: ()}


@pytest.mark.deid_requirement("MIDI-BP-03", "MIDI-BP-18")
def test_the_report_counts_each_instance_once_for_each_kind_of_finding():
    found = run_qc.ReferenceFindingMaterial(
        FindingKind.DANGLING_REFERENCE, ("(300C,0080)", "(0008,1155)"), 2
    )
    other = run_qc.ReferenceFindingMaterial(
        FindingKind.DANGLING_REFERENCE, ("(300C,0002)", "(0008,1155)"), 1
    )
    material = {0: (found, other), 2: (found,), 3: ()}

    text = _reporter()((), material, "A-" + "0" * 32)

    assert json.loads(text)["reference_findings"] == [
        {"kind": "dangling-reference", "count": 2}
    ]


@pytest.mark.deid_requirement("MIDI-BP-03", "MIDI-BP-17")
def test_the_structural_checks_count_each_reported_instance_once():
    found = run_qc.ReferenceFindingMaterial(
        FindingKind.DANGLING_REFERENCE, ("(300C,0080)", "(0008,1155)"), 1
    )
    gap = SourceGap(ElementPath((), "(0008,0060)"), "1")
    unwritten = run_qc.WrittenFindingMaterial(
        WrittenFindingKind.UNWRITTEN_TARGET, ("(300C,0002)", "(0008,1155)"), 1
    )
    material = {
        0: (found, found, gap, gap),
        1: (unwritten, unwritten),
        2: (found, gap, unwritten),
        3: (),
    }
    # Position 2 is an identical copy of position 0, the same instance.
    outcomes = [
        types.SimpleNamespace(position=position, duplicate_of=copy_of, label=None)
        for position, copy_of in ((0, None), (1, None), (2, 0), (3, None))
    ]

    assert run_report.structural_checks(outcomes, material) == (
        release_report.StructuralCheck("references", 0, 1),
        release_report.StructuralCheck("iod-requirements", 0, 1),
        release_report.StructuralCheck("written-references", 0, 1),
    )


@pytest.mark.deid_requirement("MIDI-BP-03")
def test_each_written_finding_reported_only_is_added_once_to_each_input_it_names():
    kept = object()
    unwritten = WrittenFinding(
        WrittenFindingKind.UNWRITTEN_TARGET, ((2,),), ("(300C,0002)", "(0008,1155)"), 1
    )
    acted = WrittenFinding(
        WrittenFindingKind.MISMATCHED_REFERENCE, ((1,),), ("(0008,1155)",), 1
    )

    added = run_qc.with_written_findings({2: (kept,)}, (acted, unwritten, unwritten))

    assert added == {
        2: (
            kept,
            run_qc.WrittenFindingMaterial(
                WrittenFindingKind.UNWRITTEN_TARGET, ("(300C,0002)", "(0008,1155)"), 1
            ),
        )
    }


def test_the_reporter_shows_nothing_and_refuses_a_policy_it_cannot_record():
    assert repr(_reporter()) == "ReleaseReporter()"
    with pytest.raises(TypeError):
        ReleaseReporter("basic", vocabulary=None, reviewed_roi_names=None)


@pytest.mark.deid_requirement("MIDI-BP-18")
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
        # An identical copy of a held input is the same instance (D-009).
        run.Outcome(3, run.Status.HELD_FOR_REVIEW, (review,), duplicate_of=0),
    ]

    assert held_instances(outcomes) == (
        release_report.HeldForReview("release", "uncollected", 1),
    )
    assert run.Status.HELD_FOR_REVIEW.value == HELD_FOR_REVIEW


@pytest.mark.deid_requirement("MIDI-BP-18")
@pytest.mark.parametrize(
    "name",
    [
        RELEASE_REPORT,
        RELEASE_REPORT.upper(),
        RELEASE_REPORT_MARKDOWN,
        RELEASE_REPORT_MARKDOWN.upper(),
        CONFORMANCE_STATEMENT,
        CONFORMANCE_STATEMENT.upper(),
    ],
)
def test_no_output_name_is_the_release_report(name):
    # The first part of every output's path is a pseudonymous Patient ID, so
    # even a file system that ignores case cannot confuse one with the report
    # or the conformance statement.
    pattern = output_names._PATIENT_ID  # pylint: disable = protected-access
    assert pattern.fullmatch(name) is None
    assert pattern.fullmatch(name.casefold()) is None


@pytest.mark.parametrize(
    "module",
    ["release_report", "qc_pack", "run_qc", "descriptor_cleaning", "run", "run_report"],
)
def test_each_module_of_the_report_and_the_qc_pack_imports_first(module):
    # The QC pack and the release report import from each other's
    # neighbours, so each must import cleanly in a fresh interpreter,
    # whichever is imported first.
    subprocess.run(
        [sys.executable, "-c", f"import pymedphys._dicom.deidentify.{module}"],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)},
    )
