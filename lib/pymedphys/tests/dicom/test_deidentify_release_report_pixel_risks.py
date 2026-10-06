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

"""Tests of how the release report counts the risks in pixel data (D-015).

Every data set is synthetic.
"""

import collections
import json
import shutil
import tempfile
from pathlib import Path, PurePosixPath

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import pixel_risk, release_report, run, run_qc
from pymedphys._dicom.deidentify import synthetic_corpus as corpus_module
from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.instance_transform import (
    InstanceTransform,
    ReleaseGate,
)
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.policy import compose_policy
from pymedphys._dicom.deidentify.release_report import PixelRiskCount
from pymedphys._dicom.deidentify.run_report import ReleaseReporter, pixel_risks

from . import _synthetic_references as synthetic
from .test_deidentify_pixel_risk import _slice
from .test_deidentify_qc_preview_pack import _outcome

Risk = pixel_risk.Risk
Indicator = pixel_risk.Indicator
TEXT = Risk.BURNED_IN_TEXT
FACE = Risk.RECONSTRUCTABLE_FACE
RELEASED = "released"
HELD = "held-for-review"


def _report(counts):
    return release_report.release_report(
        compose_policy("basic"), vocabulary=None, reviewed_roi_names=None, pixel=counts
    )


def _section(counts):
    return release_report.report_document(_report(counts))["pixel_risks"]


# Counting the instances.


@pytest.mark.deid_requirement("MIDI-BP-10")
def test_each_instance_counts_once_for_each_risk_and_each_indicator():
    counts = release_report.pixel_risks(
        [
            (
                RELEASED,
                [
                    (TEXT, Indicator.SECONDARY_IMAGE),
                    (TEXT, Indicator.CONVERTED_IMAGE),
                    (TEXT, Indicator.SECONDARY_IMAGE),
                ],
            ),
            (
                RELEASED,
                [(TEXT, Indicator.SECONDARY_IMAGE), (FACE, Indicator.CT_VOLUME)],
            ),
            (HELD, [(FACE, Indicator.UNREADABLE), (TEXT, Indicator.UNREADABLE)]),
            (RELEASED, []),
        ]
    )

    assert counts == (
        PixelRiskCount(RELEASED, "burned-in-text", None, 2),
        PixelRiskCount(RELEASED, "burned-in-text", "converted-image", 1),
        PixelRiskCount(RELEASED, "burned-in-text", "secondary-image", 2),
        PixelRiskCount(RELEASED, "reconstructable-face", None, 1),
        PixelRiskCount(RELEASED, "reconstructable-face", "ct-volume", 1),
        PixelRiskCount(HELD, "burned-in-text", None, 1),
        PixelRiskCount(HELD, "burned-in-text", "unreadable", 1),
        PixelRiskCount(HELD, "reconstructable-face", None, 1),
        PixelRiskCount(HELD, "reconstructable-face", "unreadable", 1),
    )


@pytest.mark.parametrize(
    "instance",
    [
        ("sequestered", [(TEXT, Indicator.SECONDARY_IMAGE)]),
        (RELEASED, [("burned-in-text", Indicator.SECONDARY_IMAGE)]),
        (RELEASED, [(TEXT, "secondary-image")]),
        # A secondary image bears on burned-in text, not on a face.
        (RELEASED, [(FACE, Indicator.SECONDARY_IMAGE)]),
    ],
)
def test_counting_refuses_what_is_not_a_released_or_held_instances_risks(instance):
    with pytest.raises(TypeError):
        release_report.pixel_risks([instance])


# The document's section.


@pytest.mark.deid_requirement("MIDI-BP-10", "MIDI-BP-18")
def test_the_section_splits_the_risks_from_their_indicators():
    section = _section(
        release_report.pixel_risks(
            [
                (HELD, [(FACE, Indicator.PATIENT_SURFACE_CONTOUR)]),
                (RELEASED, [(TEXT, Indicator.BURNED_IN_ANNOTATION)]),
            ]
        )
    )

    assert section == {
        "instances": [
            {"disposition": RELEASED, "risk": "burned-in-text", "count": 1},
            {"disposition": HELD, "risk": "reconstructable-face", "count": 1},
        ],
        "indicators": [
            {
                "disposition": RELEASED,
                "risk": "burned-in-text",
                "indicator": "burned-in-annotation",
                "count": 1,
            },
            {
                "disposition": HELD,
                "risk": "reconstructable-face",
                "indicator": "patient-surface-contour",
                "count": 1,
            },
        ],
    }
    assert _section(()) == {"instances": [], "indicators": []}


@pytest.mark.deid_requirement("MIDI-BP-18")
@pytest.mark.parametrize(
    "counts",
    [
        (PixelRiskCount("sequestered", "burned-in-text", None, 1),),
        (PixelRiskCount(RELEASED, "SENTINEL", None, 1),),
        (PixelRiskCount(RELEASED, "burned-in-text", None, 0),),
        (PixelRiskCount(RELEASED, "burned-in-text", None, True),),
        (
            PixelRiskCount(RELEASED, "burned-in-text", None, 1),
            PixelRiskCount(RELEASED, "burned-in-text", "SENTINEL", 1),
        ),
        (
            PixelRiskCount(RELEASED, "burned-in-text", None, 1),
            PixelRiskCount(RELEASED, "burned-in-text", "ct-volume", 1),
        ),
        # An indicator counted without its risk's instances.
        (PixelRiskCount(RELEASED, "burned-in-text", "secondary-image", 1),),
        (
            PixelRiskCount(RELEASED, "burned-in-text", None, 1),
            PixelRiskCount(RELEASED, "burned-in-text", None, 2),
        ),
        ("burned-in-text",),
    ],
)
def test_a_section_not_of_the_engines_codes_is_refused_naming_no_value(counts):
    with pytest.raises(release_report.ReleaseReportError) as raised:
        release_report.to_json(_report(counts))
    assert "pixel_risks" in str(raised.value)
    assert "SENTINEL" not in str(raised.value)


# The run's report.


def _evidence(series, dataset):
    return run_qc.SeriesEvidence(series, pixel_risk.series_evidence(dataset))


def _assessed(*findings):
    return run_qc.PixelRiskMaterial(pixel_risk.PixelRiskAssessment(True, findings))


SECONDARY = pixel_risk.Finding(
    Indicator.SECONDARY_IMAGE, ElementPath((), "(0008,0008)")
)


@pytest.mark.deid_requirement("MIDI-BP-10", "MIDI-BP-15")
@pytest.mark.pydicom
def test_the_report_counts_what_the_qc_pack_lists_of_released_and_held_instances():
    outcomes = (
        _outcome(0, run.Status.RELEASED, PurePosixPath("a/0.dcm")),
        _outcome(1, run.Status.RELEASED, PurePosixPath("a/1.dcm")),
        _outcome(2, run.Status.HELD_FOR_REVIEW, reasons=(run.RunReason.DICOMDIR,)),
        _outcome(
            3, run.Status.SEQUESTERED, label="S-0001", reasons=(run.RunReason.DICOMDIR,)
        ),
        _outcome(4, run.Status.RELEASED, PurePosixPath("a/4.dcm")),
        _outcome(5, run.Status.RELEASED, PurePosixPath("a/5.dcm")),
        # An identical copy of input 1 is the same instance.
        run.Outcome(6, run.Status.DUPLICATE, (), PurePosixPath("a/1.dcm"), 1),
    )
    material = {
        0: (_evidence("2.25.1", _slice(0)),),
        1: (_evidence("2.25.2", synthetic.rt_plan()), _assessed(SECONDARY)),
        2: (_evidence("2.25.1", _slice(2, BodyPartExamined="HEAD")),),
        # Sequestered, so neither its own indicator nor its series counts.
        3: (_evidence("2.25.3", _slice(3)), _assessed(SECONDARY)),
        4: (_evidence("2.25.3", _slice(4)),),
        5: (_evidence("2.25.1", _slice(5)),),
        6: (_evidence("2.25.2", synthetic.rt_plan()), _assessed(SECONDARY)),
    }
    pack = run_qc.qc_pack_of(
        [Path(f"in/{n}.dcm") for n in range(7)], outcomes, material
    )

    counts = pixel_risks(outcomes, material)

    assert [entry.position for entry in pack.pixel_risks] == [1, 3, 6]
    assert [entry.positions for entry in pack.series_risks] == [(0, 2, 5)]
    assert counts == (
        PixelRiskCount(RELEASED, "burned-in-text", None, 1),
        PixelRiskCount(RELEASED, "burned-in-text", "secondary-image", 1),
        PixelRiskCount(RELEASED, "reconstructable-face", None, 2),
        PixelRiskCount(RELEASED, "reconstructable-face", "ct-volume", 2),
        PixelRiskCount(HELD, "reconstructable-face", None, 1),
        PixelRiskCount(HELD, "reconstructable-face", "ct-volume", 1),
        PixelRiskCount(HELD, "reconstructable-face", "head-or-neck", 1),
    )


@pytest.mark.deid_requirement("MIDI-BP-10")
def test_a_held_copy_is_assessed_with_its_series_but_not_counted_again():
    outcomes = (
        _outcome(0, run.Status.HELD_FOR_REVIEW, reasons=(run.RunReason.DICOMDIR,)),
        run.Outcome(1, run.Status.HELD_FOR_REVIEW, (run.RunReason.DICOMDIR,), None, 0),
    )
    material = {0: (_assessed(SECONDARY),), 1: (_assessed(SECONDARY),)}

    assert pixel_risks(outcomes, material) == (
        PixelRiskCount(HELD, "burned-in-text", None, 1),
        PixelRiskCount(HELD, "burned-in-text", "secondary-image", 1),
    )


def _listed(pack):
    """Count the released and held instances by what the QC pack lists."""
    dispositions = {
        entry["position"]: entry["disposition"]
        for entry in pack["instances"]
        if entry["disposition"] in (RELEASED, HELD)
    }
    found = collections.defaultdict(set)
    for entry in pack["pixel_risks"]:
        for finding in entry["findings"]:
            found[entry["position"]].add((finding["risk"], finding["indicator"]))
    for entry in pack["series_risks"]:
        for finding in entry["findings"]:
            for position in finding["positions"]:
                found[position].add((finding["risk"], finding["indicator"]))
    counts = collections.Counter()
    for position, pairs in found.items():
        if position in dispositions:
            disposition = dispositions[position]
            counts.update({(disposition, risk, None) for risk, _ in pairs})
            counts.update((disposition, *pair) for pair in pairs)
    return counts


@pytest.mark.deid_requirement("MIDI-BP-10", "MIDI-BP-15", "MIDI-BP-18")
@pytest.mark.pydicom
def test_a_run_over_the_synthetic_corpus_reports_what_its_qc_pack_lists(tmp_path):
    corpus = corpus_module.build_corpus()
    # A short directory, since a run refuses output paths that could exceed
    # Windows' 259 characters.
    directory = Path(tempfile.mkdtemp(prefix="d"))
    policy = compose_policy("basic")
    try:
        corpus_module.write_corpus(corpus, directory)
        result = run.run(
            run.discover(directory / corpus_module.INSTANCES_DIRECTORY),
            directory / "release",
            InstanceTransform(
                policy, DeidKey(bytes(range(32))), unvalidated_policy=True
            ),
            ReleaseGate(),
            qc_destination=tmp_path / "qc",
            reporter=ReleaseReporter(policy, vocabulary=None, reviewed_roi_names=None),
        )
        report = json.loads(
            (directory / "release" / "release-report.json").read_text(encoding="utf-8")
        )
    finally:
        shutil.rmtree(directory, ignore_errors=True)

    pack = json.loads(result.qc_pack.read_text(encoding="utf-8"))
    section = report["pixel_risks"]
    reported = collections.Counter(
        {
            (entry["disposition"], entry["risk"], entry.get("indicator")): entry[
                "count"
            ]
            for entry in (*section["instances"], *section["indicators"])
        }
    )
    # The corpus' released CT slices are a volume.
    assert reported[(RELEASED, "reconstructable-face", "ct-volume")] >= 2
    assert reported == _listed(pack)
