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

"""A CT series' globes checked against the eyes that a structure set in its
Frame of Reference draws. Every UID and value here is invented."""

from __future__ import annotations

import functools
import io

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import face_blocks
from pymedphys._dicom.deidentify.defacing import FaceBlock
from pymedphys._dicom.deidentify.face_blocks import (
    EYE_REACH,
    SeriesDefacing,
    SeriesProblem,
    find_face_blocks,
)
from pymedphys._dicom.deidentify.references import InstanceRecord

from . import _synthetic_head as head
from . import _synthetic_head_dicom as files

_SCAN = head.axial(
    spacing=2.0, thickness=3.0, extent=((-100, 100), (-130, 110), (-60, 120))
)
_GLOBES = (
    (-head.GLOBE_X, head.GLOBE_Y, head.GLOBE_Z),
    (head.GLOBE_X, head.GLOBE_Y, head.GLOBE_Z),
)
_BLOCK = FaceBlock((0.0, -60.0, 0.0), (0.0, -1.0, 0.0), 0.0, _GLOBES)


def _eye(centre, radius=head.GLOBE_RADIUS):
    """An eye's contours: circles on three slices through the globe."""
    x, y, z = centre
    return [
        files.circle((x, y, z + dz), np.sqrt(radius**2 - dz**2)) for dz in (-6, 0, 6)
    ]


def _structure_set(*rois, frame=files.FRAME):
    """A structure set of ROIs as (name, contours) pairs."""
    data = files.structure_set(
        [("ORGAN", contours) for _, contours in rois],
        frame=frame,
        names=[name for name, _ in rois],
    )
    return pydicom.dcmread(io.BytesIO(data))


@pytest.mark.parametrize(
    "name",
    [
        "Eye_L",
        "Eye_R",
        "EYE_L",
        "EyeL",
        "LEye",
        "Lt Eye",
        "Rt_Eye",
        "Eyes",
        "Globe_R",
        "Eyeball_L",
        "Eye_L_PRV05",
        "PRV_Eye-R",
        "z_eye_l",
    ],
)
def test_an_eye_is_known_by_its_name(name):
    # pylint: disable = protected-access
    assert face_blocks._is_eye(name)


@pytest.mark.parametrize(
    "name",
    [
        "Lens_L",
        "EyeLens_R",
        "Eye_L_Lens",
        "Cornea_R",
        "Eye_L_ring",
        "Eye-Avoid",
        "OpticNrv_L",
        "Orbit_L",
        "Eyelid_L",
        "Retina_R",
        "Brain",
        "",
    ],
)
def test_parts_of_an_eye_rings_and_other_rois_are_not_eyes(name):
    # pylint: disable = protected-access
    assert not face_blocks._is_eye(name)


def _far(*rois, frame=files.FRAME):
    # pylint: disable = protected-access
    return face_blocks._eyes_far(_structure_set(*rois), frame, _BLOCK)


def test_eyes_drawn_at_the_globes_agree():
    assert not _far(("Eye_R", _eye(_GLOBES[0])), ("Eye_L", _eye(_GLOBES[1])))
    # Both together in one ROI, and an eye drawn with a margin.
    assert not _far(("Eyes", [*_eye(_GLOBES[0]), *_eye(_GLOBES[1])]))
    assert not _far(("Eye_L_PRV05", _eye(_GLOBES[1], head.GLOBE_RADIUS + 5)))


@pytest.mark.parametrize("shift", [(0, -40, 0), (64, 0, 0), (0, 0, 30)])
def test_an_eye_drawn_away_from_the_globes_disagrees(shift):
    eye = np.add(_GLOBES[1], shift)

    assert _far(("Eye_R", _eye(_GLOBES[0])), ("Eye_L", _eye(eye)))


def test_a_point_just_beyond_reach_disagrees():
    near = files.circle(_GLOBES[1], EYE_REACH - 0.01)
    beyond = files.circle(_GLOBES[1], EYE_REACH + 0.01)

    assert not _far(("Eye_L", [near]))
    assert _far(("Eye_L", [beyond]))


def test_an_eye_that_cannot_be_placed_disagrees():
    eye = _eye(_GLOBES[1])
    eye[0][0, 0] = np.nan

    assert _far(("Eye_L", eye))


def test_other_rois_and_eyes_in_another_frame_are_not_checked():
    away = _eye(np.add(_GLOBES[1], (0, -40, 0)))

    assert not _far(("Lens_L", away), ("Brain", away))
    assert not _far(("Eye_L", away), frame=files.ROOT + ".8")


def test_an_eye_that_names_no_frame_is_checked():
    away = _eye(np.add(_GLOBES[1], (0, -40, 0)))
    dataset = _structure_set(("Eye_L", away))
    dataset.StructureSetROISequence[0].ReferencedFrameOfReferenceUID = ""

    # pylint: disable = protected-access
    assert face_blocks._eyes_far(dataset, files.FRAME, _BLOCK)


# On the analytic head.


@functools.cache
def _head_files() -> tuple[bytes, ...]:
    return tuple(files.ct_files(_SCAN, head.Head(noise=0.0)))


def _outcome(*others: bytes) -> SeriesDefacing:
    data = [*_head_files(), *others]
    records = {
        position: InstanceRecord.from_file(each) for position, each in enumerate(data)
    }
    (outcome,) = list(
        find_face_blocks(records, lambda position: data[position]).values()
    )
    return outcome


def _rtss(*rois, frame=files.FRAME):
    return files.structure_set(
        [(kind, contours) for _, kind, contours in rois],
        frame=frame,
        names=[name for name, _, _ in rois],
    )


def test_eyes_drawn_on_the_head_leave_its_series_defaced():
    rtss = _rtss(
        ("Eye_R", "ORGAN", _eye(_GLOBES[0])), ("Eye_L", "ORGAN", _eye(_GLOBES[1]))
    )

    outcome = _outcome(rtss)

    assert outcome.problem is None and not outcome.held


def test_an_eye_drawn_away_from_the_globes_holds_the_head_ct():
    # Drawn 40 mm below the eye, where the finder found no globe.
    rtss = _rtss(
        ("Eye_R", "ORGAN", _eye(_GLOBES[0])),
        ("Eye_L", "ORGAN", _eye(np.add(_GLOBES[1], (0, 0, -40)))),
    )

    outcome = _outcome(rtss)

    assert outcome.problem is SeriesProblem.EYES_DISAGREE
    assert outcome.held and outcome.block is None and outcome.frame is None


def test_an_eye_in_another_frame_leaves_the_head_ct_defaced():
    rtss = _rtss(
        ("Eye_L", "ORGAN", _eye(np.add(_GLOBES[1], (0, 0, -40)))),
        frame=files.ROOT + ".8",
    )

    assert _outcome(rtss).problem is None


def test_a_target_in_the_block_is_the_reason_before_the_eyes():
    rtss = _rtss(
        ("PTV", "PTV", files.square((-32.0, -76.0, 20.0))),
        ("Eye_L", "ORGAN", _eye(np.add(_GLOBES[1], (0, 0, -40)))),
    )

    assert _outcome(rtss).problem is SeriesProblem.TARGET_IN_BLOCK


def test_a_structure_set_that_cannot_be_read_again_for_its_eyes_holds_the_series():
    rtss = _rtss(("Eye_L", "ORGAN", _eye(_GLOBES[1])))
    data = [*_head_files(), rtss]
    records = {p: InstanceRecord.from_file(each) for p, each in enumerate(data)}
    reads = {"count": 0}

    def read(position):
        # The target search reads it; the eye check finds it changed.
        if position == len(data) - 1:
            reads["count"] += 1
            return data[position] if reads["count"] == 1 else b"not DICOM"
        return data[position]

    (outcome,) = list(find_face_blocks(records, read).values())

    assert outcome.problem is SeriesProblem.EYES_DISAGREE
