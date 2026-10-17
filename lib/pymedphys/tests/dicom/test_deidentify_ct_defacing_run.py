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

"""A run under Clean Recognizable Visual Features that defaces a CT series
of the analytic head, beside the synthetic collection's RT Structure Set and
RT Dose in the same Frame of Reference. Every UID and value here is
invented."""

from __future__ import annotations

import contextlib
import json
import shutil
import tempfile
from pathlib import Path

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import face_blocks, markers, run
from pymedphys._dicom.deidentify import synthetic_corpus as corpus_module
from pymedphys._dicom.deidentify.face_review import read_face_review
from pymedphys._dicom.deidentify.instance_transform import (
    InstanceTransform,
    ReleaseGate,
)
from pymedphys._dicom.deidentify.policy import CLEAN_PIXEL_DATA, compose_policy
from pymedphys._dicom.deidentify.qc_attestation import Face
from pymedphys._dicom.deidentify.reasons import (
    HeldPixelData,
    HeldVisualFeatures,
    PixelDataReason,
    VisualFeaturesReason,
)
from pymedphys._dicom.deidentify.references import InstanceRecord

from . import _synthetic_head as head
from . import _synthetic_head_dicom as files
from .test_deidentify_visual_features_option import (
    CODE,
    KEY,
    _attest,
    _codes,
    _CornerFinder,
    _policy,
)

# As coarse and short as the face block's finder allows, since every slice
# goes through two runs.
_SCAN = head.axial(
    spacing=2.5, thickness=5.0, extent=((-100, 100), (-130, 110), (-30, 110))
)
_CT_FILES = ("01-ct-1.dcm", "02-ct-2.dcm", corpus_module.SEQUESTERED_FILE)
_STRUCTURE_SET = "04-rtstruct.dcm"
_DOSE = ("06-rtdose.dcm", "07-rtdose-review.dcm")
_IN_THE_BLOCK = (-32.0, -76.0, 20.0)


def _head_name(index):
    return f"01-head-{index:03d}.dcm"


@contextlib.contextmanager
def _runs(*others, target=False):
    """Run the collection, with its CT slices replaced by the head's, under
    ``basic``; attest the pack with the head's series alone marked absent;
    and run it again under the option and ``others``."""
    corpus = corpus_module.build_corpus()
    directory = Path(tempfile.mkdtemp(prefix="d"))
    try:
        corpus_module.write_corpus(corpus, directory)
        instances = directory / corpus_module.INSTANCES_DIRECTORY
        template = pydicom.dcmread(instances / _CT_FILES[0])
        for name in _CT_FILES:
            (instances / name).unlink()
        slices = files.ct_files(
            _SCAN,
            head.Head(noise=0.0),
            series=corpus_module.CT_SERIES,
            frame=corpus_module.FRAME_OF_REFERENCE,
            template=template,
        )
        for index, data in enumerate(slices):
            (instances / _head_name(index)).write_bytes(data)
        if target:
            rtss = pydicom.dcmread(instances / _STRUCTURE_SET)
            (instances / _STRUCTURE_SET).write_bytes(
                files.structure_set(
                    [("PTV", files.square(_IN_THE_BLOCK))],
                    frame=corpus_module.FRAME_OF_REFERENCE,
                    template=rtss,
                )
            )
        first = run.run(
            run.discover(instances),
            directory / "r1",
            InstanceTransform(compose_policy("basic"), KEY, unvalidated_policy=True),
            ReleaseGate(),
            qc_destination=directory / "qc1",
        )
        entries = json.loads(first.qc_pack.read_text("utf-8"))
        names = {e["position"]: Path(e["source"]).name for e in entries["instances"]}
        (series,) = [
            s
            for s in entries["series"]
            if names[s["positions"][0]].startswith("01-head")
        ]
        _attest(first.qc_pack.parent, {series["positions"][0]: Face.ABSENT})
        transform = InstanceTransform(
            _policy(*others),
            KEY,
            face_review=read_face_review(first.qc_pack.parent),
            finder=_CornerFinder() if CLEAN_PIXEL_DATA in others else None,
            unvalidated_policy=True,
        )
        second = run.run(
            run.discover(instances),
            directory / "r2",
            transform,
            ReleaseGate(),
            qc_destination=directory / "qc2",
            reporter=transform.reporter,
        )
        pack = json.loads(second.qc_pack.read_text("utf-8"))["instances"]
        outcomes = {
            Path(entry["source"]).name: (
                entry["disposition"],
                None
                if entry.get("output") is None
                else pydicom.dcmread(directory / "r2" / entry["output"]),
            )
            for entry in pack
        }
        reasons = {
            Path(entry["source"]).name: set(outcome.reasons)
            for entry in pack
            for outcome in second.outcomes
            if outcome.position == entry["position"]
        }
        report = json.loads((directory / "r2" / "release-report.json").read_text())
        yield slices, outcomes, reasons, report
    finally:
        shutil.rmtree(directory, ignore_errors=True)


@pytest.fixture(name="defaced", scope="module")
def fixture_defaced():
    with _runs() as found:
        yield found


@pytest.fixture(name="targeted", scope="module")
def fixture_targeted():
    with _runs(target=True) as found:
        yield found


@pytest.fixture(name="with_pixel_data", scope="module")
def fixture_with_pixel_data():
    with _runs(CLEAN_PIXEL_DATA) as found:
        yield found


def _block(slices):
    records = {
        index: InstanceRecord.from_file(data) for index, data in enumerate(slices)
    }
    outcomes = face_blocks.find_face_blocks(records, lambda index: slices[index])
    (outcome,) = list(outcomes.values())
    return outcome.block


@pytest.mark.deid_requirement("PS3.15-E.3.2-01", "PS3.15-E.3.2-02")
def test_a_head_ct_marked_absent_is_released_defaced_with_the_option(defaced):
    slices, outcomes, _, _ = defaced
    block = _block(slices)
    changed = kept = 0

    for index, data in enumerate(slices):
        disposition, dataset = outcomes[_head_name(index)]
        assert disposition == "released", index
        assert dataset.RecognizableVisualFeatures == "NO"
        assert _codes(dataset)[-2:] == [markers.PROFILE_CODE, CODE]
        before = pydicom.dcmread(pydicom.filebase.DicomBytesIO(data))
        source = pydicom.pixels.apply_rescale(
            pydicom.pixels.pixel_array(before), before
        )
        written = pydicom.pixels.apply_rescale(
            pydicom.pixels.pixel_array(dataset), dataset
        )
        points = _SCAN.points(index)
        inside = block.contains(points)
        values = head.hounsfield(points)
        # Outside the block, nothing changes; within it, each voxel is air
        # or as it was, the eyes are air, and the brain above the orbits,
        # which the skull encloses there, is kept.
        assert np.array_equal(written[~inside], source[~inside]), index
        assert np.all((written[inside] == -1000) | (written[inside] == source[inside]))
        eye = inside & np.isin(values, [head.VITREOUS, head.LENS])
        assert np.all(written[eye] == -1000), index
        floor = head.GLOBE_Z + face_blocks.CAVITY_FLOOR
        brain = inside & (values == head.BRAIN) & (points[..., 2] > floor)
        assert np.array_equal(written[brain], source[brain]), index
        kept += int(np.count_nonzero(brain))
        changed += int(np.count_nonzero(written != source))
    assert changed > 0 and kept > 0


@pytest.mark.deid_requirement("PS3.15-E.3.2-01")
def test_rt_instances_in_the_defaced_frame_keep_their_own_face_review(defaced):
    _, outcomes, reasons, report = defaced

    # Without verdicts of their own, the RT Structure Set and RT Dose in the
    # head's Frame of Reference are held, and nothing claims the option for
    # them because their CT was defaced.
    for name in (_STRUCTURE_SET, *_DOSE):
        assert outcomes[name] == ("held-for-review", None), name
        assert HeldVisualFeatures(VisualFeaturesReason.NO_FACE_VERDICT) in reasons[name]
    assert report["face_review"]["ct_series"] == {"defaced": 1, "not_defaced": []}


def test_a_target_in_the_block_holds_the_head_ct(targeted):
    slices, outcomes, reasons, report = targeted
    held = HeldVisualFeatures(VisualFeaturesReason.TARGET_IN_FACE_BLOCK)

    for index in range(len(slices)):
        assert outcomes[_head_name(index)] == ("held-for-review", None), index
        assert held in reasons[_head_name(index)]
    assert report["face_review"]["ct_series"] == {
        "defaced": 0,
        "not_defaced": [{"reason": "target-in-block", "count": 1}],
    }
    counts = {
        entry["code"]: entry["count"]
        for entry in report["held_for_review"]
        if entry["stage"] == "visual-features"
    }
    assert counts["target-in-face-block"] == len(slices)


@pytest.mark.deid_requirement("PS3.15-E.3.1-01", "PS3.15-E.3.2-01")
def test_with_clean_pixel_data_the_head_ct_is_held_for_its_pixel_data(
    with_pixel_data,
):
    slices, outcomes, reasons, report = with_pixel_data

    # Marked absent, and defaced, but its text regions still await review.
    for index in range(len(slices)):
        name = _head_name(index)
        assert outcomes[name] == ("held-for-review", None), index
        assert HeldPixelData(PixelDataReason.TEXT_BLACKED_OUT) in reasons[name]
        assert not any(isinstance(r, HeldVisualFeatures) for r in reasons[name])
    assert report["face_review"]["ct_series"] == {"defaced": 1, "not_defaced": []}
