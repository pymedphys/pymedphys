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

"""The release report's summary of the engine's structural checks."""

import json

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import policy, release_report
from pymedphys._dicom.deidentify.reasons import RunReason, TransformReason
from pymedphys._dicom.deidentify.reference_graph import FindingKind
from pymedphys._dicom.deidentify.release_report import (
    STRUCTURAL_CHECKS,
    SequesteredInstance,
    StructuralCheck,
    sequestration_reason,
)
from pymedphys._dicom.deidentify.release_report_markdown import (
    ReleaseReportMarkdownError,
    to_markdown,
)


@pytest.fixture(name="basic", scope="module")
def _basic():
    return policy.compose_policy("basic")


class _Text(str):
    pass


def _report(basic, **run):
    return release_report.release_report(
        basic, vocabulary=None, reviewed_roi_names=None, **run
    )


def _checks(report):
    return {
        entry["check"]: (entry["sequestered"], entry["reported"])
        for entry in release_report.report_document(report)["structural_checks"]
    }


def _sequestered(*reasons, label="S-0001"):
    return SequesteredInstance(
        label, tuple(sequestration_reason(reason) for reason in reasons)
    )


def _reported(references=0, iod=0, written=0):
    return (
        StructuralCheck("references", references),
        StructuralCheck("iod-requirements", iod),
        StructuralCheck("written-references", written),
    )


def test_the_checks_are_those_of_references_iods_and_what_was_written():
    assert STRUCTURAL_CHECKS == (
        "references",
        "iod-requirements",
        "written-references",
    )


@pytest.mark.deid_requirement("MIDI-BP-17", "MIDI-BP-18")
def test_a_run_without_instances_shows_each_check_with_none(basic):
    document = release_report.report_document(_report(basic))

    assert document["structural_checks"] == [
        {"check": check, "sequestered": 0, "reported": 0} for check in STRUCTURAL_CHECKS
    ]
    assert list(document)[-1] == "structural_checks"


@pytest.mark.deid_requirement("MIDI-BP-03", "MIDI-BP-17")
def test_each_check_counts_the_instances_it_sequestered_from_their_reasons(basic):
    sequestered = (
        _sequestered(
            FindingKind.CONFLICTING_INSTANCE,
            FindingKind.MISSING_IDENTIFIER,
            label="S-0001",
        ),
        _sequestered(TransformReason.REQUIRED_ATTRIBUTE_LOST, label="S-0002"),
        _sequestered(RunReason.INCONSISTENT_REFERENCES, label="S-0003"),
        _sequestered(
            RunReason.INCONSISTENT_REFERENCES,
            TransformReason.REQUIRED_ATTRIBUTE_LOST,
            label="S-0004",
        ),
        _sequestered(RunReason.STAGED_FILE_CHANGED, label="S-0005"),
    )

    report = _report(basic, sequestered=sequestered, checks=_reported(2, 1, 3))

    # Each instance is counted once for each check that sequestered it,
    # however many of its reasons that check gave.
    assert _checks(report) == {
        "references": (1, 2),
        "iod-requirements": (2, 1),
        "written-references": (2, 3),
    }


@pytest.mark.deid_requirement("MIDI-BP-17", "MIDI-BP-18")
@pytest.mark.parametrize(
    "checks, field",
    [
        (("SENTINEL", *_reported()[1:]), "structural_checks"),
        (
            (StructuralCheck("SENTINEL", 0), *_reported()[1:]),
            "structural_checks check",
        ),
        (
            (StructuralCheck(_Text("references"), 0), *_reported()[1:]),
            "structural_checks check",
        ),
        ((StructuralCheck("references", True), *_reported()[1:]), "structural_checks"),
        ((StructuralCheck("references", -1), *_reported()[1:]), "structural_checks"),
        ((StructuralCheck("references", "1"), *_reported()[1:]), "structural_checks"),
        (_reported()[:2], "structural_checks"),
        ((*_reported(), StructuralCheck("references", 0)), "structural_checks"),
        (tuple(reversed(_reported())), "structural_checks"),
    ],
    ids=[
        "not-a-check",
        "unknown-check",
        "check-subclass",
        "boolean",
        "negative",
        "text",
        "one-missing",
        "one-twice",
        "out-of-order",
    ],
)
def test_a_summary_that_could_hold_a_value_is_refused(basic, checks, field):
    report = _report(basic, checks=checks)

    for write in (release_report.report_document, release_report.to_json):
        with pytest.raises(release_report.ReleaseReportError, match=field) as raised:
            write(report)
        assert "SENTINEL" not in str(raised.value)
        assert raised.value.__cause__ is None


def _markdown(basic, **run):
    return to_markdown(release_report.to_json(_report(basic, **run)))


@pytest.mark.deid_requirement("MIDI-BP-17", "MIDI-BP-18")
def test_the_summary_is_a_table_of_each_check(basic):
    markdown = _markdown(
        basic,
        sequestered=(_sequestered(TransformReason.REQUIRED_ATTRIBUTE_LOST),),
        checks=_reported(references=2),
    )

    section = markdown.split("## Structural checks", 1)[1]
    assert "| Check | Sequestered | Reported |" in section
    assert "| `references` | `0` | `2` |" in section
    assert "| `iod-requirements` | `1` | `0` |" in section
    assert "| `written-references` | `0` | `0` |" in section


def _changed(basic, change):
    document = json.loads(release_report.to_json(_report(basic)))
    change(document["structural_checks"])
    return json.dumps(document)


@pytest.mark.deid_requirement("MIDI-BP-18")
@pytest.mark.parametrize(
    "change",
    [
        lambda c: c.pop(),
        lambda c: c.reverse(),
        lambda c: c[0].update(sequestered=-1),
        lambda c: c[0].update(reported=True),
        lambda c: c[0].update(reported=1.0),
        lambda c: c[0].update(extra="x"),
        lambda c: c[1].update(check="`SENTINEL`"),
        lambda c: c.append(dict(c[0])),
    ],
)
def test_a_summary_not_in_the_reports_form_is_refused(basic, change):
    with pytest.raises(ReleaseReportMarkdownError) as raised:
        to_markdown(_changed(basic, change))
    assert "SENTINEL" not in str(raised.value)
