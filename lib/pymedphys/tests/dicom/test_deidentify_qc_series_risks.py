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

"""Tests of how a run assesses each series' indicators of risk for its QC pack.

Every data set is synthetic.
"""

import json
import shutil
import tempfile
from pathlib import Path, PurePosixPath

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import pixel_risk, qc_pack, run, run_qc
from pymedphys._dicom.deidentify import synthetic_corpus as corpus_module
from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.instance_transform import (
    InstanceTransform,
    ReleaseGate,
)
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.policy import compose_policy
from pymedphys._dicom.deidentify.qc_pack import (
    Disposition,
    QcPack,
    QcPackError,
    SeriesRiskEntry,
)

from . import _synthetic_references as synthetic
from .test_deidentify_instance_transform import _transformed
from .test_deidentify_pixel_risk import (
    EXPLICIT_LE,
    IMPLICIT_LE,
    MULTI_FRAME_CT,
    RT_DOSE,
    SENTINEL,
    _frame_anatomy,
    _multi_frame,
    _read_back,
    _region,
    _slice,
    _with_raw,
)
from .test_deidentify_qc_preview_pack import _instances, _outcome

pytestmark = pytest.mark.pydicom

Indicator = pixel_risk.Indicator
REFERENCE = "A-" + "0" * 32
BODY_PART = ElementPath((), "(0018,0015)")


def _volume(*instances):
    return pixel_risk.SeriesFinding(Indicator.CT_VOLUME, instances)


def _head(*instances):
    return pixel_risk.SeriesFinding(Indicator.HEAD_OR_NECK, instances, BODY_PART)


# The part of an instance that its series' assessment reads.


def _series_with_every_kind_of_evidence():
    """Instances that between them hold every element the assessment reads."""
    head = _slice(0, BodyPartExamined="HEAD")
    head.AnatomicRegionSequence = [_region("69536005", "SCT")]
    localizer = _slice(1, ImageType=["ORIGINAL", "PRIMARY", "LOCALIZER"])
    enhanced = _multi_frame(2, MULTI_FRAME_CT[0], NumberOfFrames=2)
    enhanced.SharedFunctionalGroupsSequence = [
        _frame_anatomy(_region("51185008", "SCT"))
    ]
    enhanced.PerFrameFunctionalGroupsSequence = [
        _frame_anatomy(_region("45048000", "SCT")),
        _frame_anatomy(_region("t-d1600", "srt")),
    ]
    dose = _slice(3)
    dose.SOPClassUID = RT_DOSE
    return [head, localizer, enhanced, dose]


@pytest.mark.deid_requirement("MIDI-BP-15")
@pytest.mark.parametrize(
    "transfer_syntax", [None, IMPLICIT_LE, EXPLICIT_LE], ids=["memory", "ivr", "evr"]
)
def test_the_series_evidence_is_assessed_as_the_instances_are(transfer_syntax):
    series = _series_with_every_kind_of_evidence()
    if transfer_syntax is not None:
        series = [_read_back(each, transfer_syntax) for each in series]

    evidence = [pixel_risk.series_evidence(each) for each in series]

    found = pixel_risk.assess_ct_series(evidence)
    assert found == pixel_risk.assess_ct_series(series)
    assert {finding.indicator for finding in found} == {
        Indicator.CT_VOLUME,
        Indicator.HEAD_OR_NECK,
    }


def test_unreadable_series_evidence_is_assessed_as_the_instance_is():
    series = [
        _multi_frame(0, MULTI_FRAME_CT[0]),
        _slice(1),
        _slice(2),
        _multi_frame(3, MULTI_FRAME_CT[1], NumberOfFrames=2),
    ]
    # A value that is not its VR's, one shorter than its length, one held
    # with another VR, and a functional group whose items cannot be read.
    _with_raw(series[0], 0x00280008, "IS", b"many")
    _with_raw(series[1], 0x00180015, "CS", b"HEAD", length=10)
    _with_raw(series[2], 0x00082218, "LO", b"HEAD")
    _with_raw(series[3], 0x52009230, "SQ", b"\x00\x00\x00\x00\x04\x00\x00\x00")

    evidence = [pixel_risk.series_evidence(each) for each in series]

    found = pixel_risk.assess_ct_series(evidence)
    assert found == pixel_risk.assess_ct_series(series)
    assert {
        str(finding.path)
        for finding in found
        if finding.indicator is Indicator.UNREADABLE
    } == {"(0028,0008)", "(0018,0015)", "(0008,2218)", "(5200,9230)"}


def test_the_series_evidence_holds_only_what_is_read_and_leaves_the_instance():
    (instance,) = [_read_back(_slice(0, BodyPartExamined="HEAD"), EXPLICIT_LE)]
    before = {tag: type(instance.get_item(tag)) for tag in instance.keys()}

    evidence = pixel_risk.series_evidence(instance)

    assert sorted(str(tag) for tag in evidence.keys()) == [
        "(0008,0008)",
        "(0008,0016)",
        "(0018,0015)",
    ]
    assert SENTINEL not in str(evidence)
    assert {tag: type(instance.get_item(tag)) for tag in instance.keys()} == before


# The pack's entries.


@pytest.mark.parametrize(
    "positions, findings",
    [
        ((), (_volume(0),)),
        ([0, 1], (_volume(0, 1),)),
        ((1, 0), (_volume(0, 1),)),
        ((0, 0), (_volume(0, 1),)),
        ((-1,), (_volume(0),)),
        ((True,), (_volume(0),)),
        ((0, 1), ()),
        ((0, 1), (_volume(0, 2),)),
        ((0, 1), (_volume(),)),
        ((0, 1), (pixel_risk.Finding(Indicator.BURNED_IN_ANNOTATION, BODY_PART),)),
        ((0, 1), (_volume(1, 0),)),
        ((0, 1), (_volume(0, 0),)),
    ],
)
def test_a_series_entry_is_checked(positions, findings):
    with pytest.raises(QcPackError):
        SeriesRiskEntry(positions, findings)


def test_a_series_entry_gives_the_run_positions_that_show_each_finding():
    entry = SeriesRiskEntry((2, 5, 7), (_volume(0, 1, 2), _head(1, 2)))
    assert [entry.shown_by(finding) for finding in entry.findings] == [
        (2, 5, 7),
        (5, 7),
    ]


@pytest.mark.parametrize(
    "series_risks, message",
    [
        (
            (
                SeriesRiskEntry((0, 1), (_volume(0, 1),)),
                SeriesRiskEntry((1,), (_volume(0),)),
            ),
            "two series",
        ),
        (
            (
                SeriesRiskEntry((1,), (_volume(0),)),
                SeriesRiskEntry((0,), (_volume(0),)),
            ),
            "order",
        ),
        ((SeriesRiskEntry((2,), (_volume(0),)),), "neither released nor held"),
        ((SeriesRiskEntry((4,), (_volume(0),)),), "neither released nor held"),
        ((SeriesRiskEntry((9,), (_volume(0),)),), "neither released nor held"),
        (("entry",), "SeriesRiskEntry"),
    ],
)
def test_the_pack_checks_its_series(series_risks, message):
    instances = _instances(
        Disposition.RELEASED,
        Disposition.HELD_FOR_REVIEW,
        Disposition.SEQUESTERED,
        Disposition.RELEASED,
    )
    with pytest.raises(QcPackError, match=message):
        QcPack(REFERENCE, instances, series_risks=series_risks)


def test_the_document_lists_each_series_by_run_position():
    instances = _instances(
        Disposition.RELEASED, Disposition.SEQUESTERED, Disposition.HELD_FOR_REVIEW
    )
    pack = QcPack(
        REFERENCE,
        instances,
        series_risks=(SeriesRiskEntry((0, 2), (_volume(0, 1), _head(1))),),
    )

    document = qc_pack.pack_document(pack)

    assert document["series_risks"] == [
        {
            "positions": [0, 2],
            "findings": [
                {
                    "indicator": "ct-volume",
                    "risk": "reconstructable-face",
                    "element": None,
                    "positions": [0, 2],
                },
                {
                    "indicator": "head-or-neck",
                    "risk": "reconstructable-face",
                    "element": "(0018,0015)",
                    "positions": [2],
                },
            ],
        }
    ]
    assert "series_risks=1" in repr(pack)


def test_the_document_lists_unreadable_evidence_of_a_series():
    unreadable = pixel_risk.SeriesFinding(
        Indicator.UNREADABLE,
        (0,),
        BODY_PART,
        pixel_risk.Risk.RECONSTRUCTABLE_FACE,
    )
    pack = QcPack(
        REFERENCE,
        _instances(Disposition.RELEASED),
        series_risks=(SeriesRiskEntry((0,), (unreadable,)),),
    )

    (entry,) = qc_pack.pack_document(pack)["series_risks"]

    assert entry["findings"] == [
        {
            "indicator": "unreadable",
            "risk": "reconstructable-face",
            "element": "(0018,0015)",
            "positions": [0],
        }
    ]


# The run's pack.


def _evidence(series, dataset):
    return run_qc.SeriesEvidence(series, pixel_risk.series_evidence(dataset))


@pytest.mark.deid_requirement("MIDI-BP-15")
def test_the_run_pack_assesses_each_series_of_released_and_held_instances():
    outcomes = (
        _outcome(0, run.Status.RELEASED, PurePosixPath("a/0.dcm")),
        _outcome(1, run.Status.RELEASED, PurePosixPath("a/1.dcm")),
        _outcome(2, run.Status.HELD_FOR_REVIEW, reasons=(run.RunReason.DICOMDIR,)),
        _outcome(
            3, run.Status.SEQUESTERED, label="S-0001", reasons=(run.RunReason.DICOMDIR,)
        ),
        _outcome(4, run.Status.RELEASED, PurePosixPath("a/4.dcm")),
        _outcome(5, run.Status.RELEASED, PurePosixPath("a/5.dcm")),
    )
    material = {
        0: (_evidence("2.25.1", _slice(0)),),
        # An instance of no CT series is assessed with its series, to no effect.
        1: (_evidence("2.25.2", synthetic.rt_plan()),),
        2: (_evidence("2.25.1", _slice(2, BodyPartExamined="HEAD")),),
        # Only one image of this series is released, so it is no volume.
        3: (_evidence("2.25.3", _slice(3)),),
        4: (_evidence("2.25.3", _slice(4)),),
        5: (_evidence("2.25.1", _slice(5)),),
    }
    sources = [Path(f"in/{n}.dcm") for n in range(6)]

    pack = run_qc.qc_pack_of(sources, outcomes, material)

    assert pack.series_risks == (
        SeriesRiskEntry((0, 2, 5), (_volume(0, 1, 2), _head(1))),
    )


def test_findings_name_the_run_positions_of_the_instances_that_show_them():
    # The series' first instances show nothing, so a finding's instances
    # must be mapped through the series' positions, not taken as positions.
    localizer = ["ORIGINAL", "PRIMARY", "LOCALIZER"]
    outcomes = tuple(
        _outcome(n, run.Status.RELEASED, PurePosixPath(f"a/{n}.dcm")) for n in range(5)
    )
    material = {
        0: (_evidence("2.25.9", synthetic.rt_plan()),),
        1: (_evidence("2.25.1", _slice(1, ImageType=localizer)),),
        2: (_evidence("2.25.1", synthetic.rt_dose()),),
        3: (_evidence("2.25.1", _slice(3)),),
        4: (_evidence("2.25.1", _slice(4, BodyPartExamined="HEAD")),),
    }
    sources = [Path(f"in/{n}.dcm") for n in range(5)]

    pack = run_qc.qc_pack_of(sources, outcomes, material)

    (entry,) = pack.series_risks
    assert entry.positions == (1, 2, 3, 4)
    assert [entry.shown_by(finding) for finding in entry.findings] == [(3, 4), (4,)]


def test_instances_without_a_series_are_assessed_together():
    outcomes = tuple(
        _outcome(n, run.Status.RELEASED, PurePosixPath(f"a/{n}.dcm")) for n in range(3)
    )
    material = {
        0: (_evidence(None, _slice(0)),),
        1: (_evidence("2.25.1", _slice(1)),),
        2: (_evidence(None, _slice(2)),),
    }
    sources = [Path(f"in/{n}.dcm") for n in range(3)]

    pack = run_qc.qc_pack_of(sources, outcomes, material)

    assert pack.series_risks == (SeriesRiskEntry((0, 2), (_volume(0, 1),)),)


def test_the_series_evidence_shows_no_value():
    evidence = _evidence("2.25.1", _slice(0, BodyPartExamined="HEAD"))
    assert repr(evidence) == "SeriesEvidence()"


def test_the_transform_gives_each_source_series_evidence():
    ct = synthetic.ct_slice(0)
    ct.BodyPartExamined = "HEAD"

    result = _transformed(ct)

    (material,) = [
        item for item in result.qc if isinstance(item, run_qc.SeriesEvidence)
    ]
    assert material.series == synthetic.CT_SERIES
    assert material.evidence.SOPClassUID == synthetic.CT_IMAGE_STORAGE
    assert material.evidence.BodyPartExamined == "HEAD"
    assert "PatientID" not in material.evidence


@pytest.mark.deid_requirement("MIDI-BP-15", "MIDI-BP-17")
def test_a_run_over_the_synthetic_corpus_lists_its_ct_volume(tmp_path):
    corpus = corpus_module.build_corpus()
    # A short directory, since a run refuses output paths that could exceed
    # Windows' 259 characters.
    directory = Path(tempfile.mkdtemp(prefix="d"))
    try:
        corpus_module.write_corpus(corpus, directory)
        instances = directory / corpus_module.INSTANCES_DIRECTORY
        transform = InstanceTransform(
            compose_policy("basic"), DeidKey(bytes(range(32))), unvalidated_policy=True
        )
        result = run.run(
            run.discover(instances),
            directory / "release",
            transform,
            ReleaseGate(),
            qc_destination=tmp_path / "qc",
        )
        # Read as stored, since a marker need not be a valid UID.
        series = {
            pydicom.dcmread(instances / file.manifest.name)
            .get_item(0x0020000E)
            .value.rstrip(b"\x00 ")
            .decode("latin-1")
            for file in corpus.files
        }
    finally:
        shutil.rmtree(directory, ignore_errors=True)

    text = result.qc_pack.read_text(encoding="utf-8")
    pack = json.loads(text)
    iods = {file.manifest.name: file.manifest.iod for file in corpus.files}
    released_ct = [
        entry["position"]
        for entry in pack["instances"]
        if iods[Path(entry["source"]).name] == "CT Image"
        and entry["disposition"] == "released"
    ]
    # The third slice is sequestered, and the other two are a volume.
    assert len(released_ct) == 2
    assert pack["series_risks"] == [
        {
            "positions": released_ct,
            "findings": [
                {
                    "indicator": "ct-volume",
                    "risk": "reconstructable-face",
                    "element": None,
                    "positions": released_ct,
                }
            ],
        }
    ]
    # The pack groups by the source's Series Instance UID but never writes it.
    assert all(uid and uid not in text for uid in series)
