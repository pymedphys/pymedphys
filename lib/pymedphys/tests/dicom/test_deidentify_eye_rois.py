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

from pymedphys._dicom.deidentify import face_blocks, qc_eyes
from pymedphys._dicom.deidentify.defacing import FaceBlock
from pymedphys._dicom.deidentify.face_blocks import (
    EYE_REACH,
    EyeCheck,
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


@pytest.mark.parametrize(
    "value",
    [
        "Eye",
        [files.FRAME, files.ROOT + ".8"],
        [files.FRAME, files.FRAME],
        files.ROOT + ".01",
        files.ROOT + ".9",
    ],
    ids=["not-a-uid", "two-frames", "given-twice", "leading-zero", "undeclared"],
)
def test_an_eye_whose_frame_is_malformed_is_checked(value):
    away = _eye(np.add(_GLOBES[1], (0, -40, 0)))
    dataset = _structure_set(("Eye_L", away))
    dataset.StructureSetROISequence[0].ReferencedFrameOfReferenceUID = value

    # As a target's, a malformed frame may be the series'.
    # pylint: disable = protected-access
    assert face_blocks._eyes_far(dataset, files.FRAME, _BLOCK)


# On the analytic head.


@functools.cache
def _head_files() -> tuple[bytes, ...]:
    return tuple(files.ct_files(_SCAN, head.Head(noise=0.0)))


def _outcome(*others: bytes, **options) -> SeriesDefacing:
    data = [*_head_files(), *others]
    records = {
        position: InstanceRecord.from_file(each) for position, each in enumerate(data)
    }
    (outcome,) = list(
        find_face_blocks(records, lambda position: data[position], **options).values()
    )
    return outcome


def _held_for_eyes(outcome: SeriesDefacing) -> bool:
    """Whether a series is defaced and held until a reviewer confirms its
    block, with the sheet that shows its eyes."""
    return (
        outcome.problem is None
        and outcome.block is not None
        and outcome.frame == files.FRAME
        and outcome.eyes is EyeCheck.DISAGREE
        and outcome.hold is SeriesProblem.EYES_DISAGREE
        and outcome.held
        and outcome.block_sha256 is not None
        and outcome.sheet is not None
    )


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
    assert outcome.eyes is EyeCheck.AGREE
    assert outcome.block_sha256 is None and outcome.sheet is None


def test_an_eye_drawn_away_from_the_globes_defaces_and_holds_the_head_ct():
    # Drawn 40 mm below the eye, where the finder found no globe.
    rtss = _rtss(
        ("Eye_R", "ORGAN", _eye(_GLOBES[0])),
        ("Eye_L", "ORGAN", _eye(np.add(_GLOBES[1], (0, 0, -40)))),
    )

    outcome = _outcome(rtss)

    # The block is the one that eyes drawn at the globes give: the series is
    # defaced with it, and held until a reviewer confirms it.
    assert _held_for_eyes(outcome)
    assert outcome.block == _outcome().block
    # The sheet's rows: the two globes, then the eye drawn away from them.
    assert outcome.sheet.rows == 3


def test_an_eye_in_another_frame_leaves_the_head_ct_defaced():
    rtss = _rtss(
        ("Eye_L", "ORGAN", _eye(np.add(_GLOBES[1], (0, 0, -40)))),
        frame=files.ROOT + ".8",
    )

    assert _outcome(rtss).problem is None


def test_an_eye_naming_no_frame_in_a_set_of_another_frame_is_checked():
    # The set is searched for targets, being of the same patient, and an
    # eye of it naming no frame may be in the series' frame, as a target
    # naming none may.
    dataset = pydicom.dcmread(
        io.BytesIO(
            _rtss(
                ("Eye_L", "ORGAN", _eye(np.add(_GLOBES[1], (0, 0, -40)))),
                frame=files.ROOT + ".8",
            )
        )
    )
    del dataset.StructureSetROISequence[0].ReferencedFrameOfReferenceUID
    buffer = io.BytesIO()
    dataset.save_as(buffer, enforce_file_format=True)

    assert _held_for_eyes(_outcome(buffer.getvalue()))


def test_a_target_kept_in_the_block_leaves_eyes_that_disagree_holding_the_series():
    rtss = _rtss(
        ("PTV", "PTV", files.square((-32.0, -76.0, 20.0))),
        ("Eye_L", "ORGAN", _eye(np.add(_GLOBES[1], (0, 0, -40)))),
    )

    outcome = _outcome(rtss)

    assert _held_for_eyes(outcome)
    # Defaced around the target, and held for the eyes.
    assert outcome.targets.in_block


def test_a_target_that_cannot_be_placed_is_the_reason_before_the_eyes():
    rtss = _rtss(
        ("PTV", "PTV", files.square((-32.0, -76.0, 2e6))),
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

    # No eye can be drawn from it, so the sheet shows the globes alone.
    assert _held_for_eyes(outcome)
    assert outcome.sheet.rows == 2


# A reviewer's confirmation of the block.


def _away():
    return _rtss(
        ("Eye_R", "ORGAN", _eye(_GLOBES[0])),
        ("Eye_L", "ORGAN", _eye(np.add(_GLOBES[1], (0, 0, -40)))),
    )


def test_a_confirmed_block_defaces_the_series_without_holding_it():
    held = _outcome(_away())

    outcome = _outcome(_away(), confirmed={held.block_sha256})

    assert outcome.problem is None and not outcome.held
    assert outcome.hold is None
    assert outcome.eyes is EyeCheck.CONFIRMED
    assert outcome.block == held.block
    assert outcome.block_sha256 == held.block_sha256
    assert outcome.sheet is None


def test_another_digest_confirms_nothing():
    held = _outcome(_away())
    other = bytes(a ^ b for a, b in zip(held.block_sha256, b"\x01" + bytes(31)))

    outcome = _outcome(_away(), confirmed={other, bytes(32)})

    assert _held_for_eyes(outcome)
    assert outcome.block_sha256 == held.block_sha256


def test_a_confirmation_of_eyes_that_agree_changes_nothing():
    rtss = _rtss(
        ("Eye_R", "ORGAN", _eye(_GLOBES[0])), ("Eye_L", "ORGAN", _eye(_GLOBES[1]))
    )
    held = _outcome(_away())

    outcome = _outcome(rtss, confirmed={held.block_sha256})

    assert outcome.eyes is EyeCheck.AGREE and outcome.block_sha256 is None


def test_a_slice_changed_gives_another_digest():
    data = list(_head_files())
    changed = pydicom.dcmread(io.BytesIO(data[0]))
    changed.SeriesDescription = "changed"
    buffer = io.BytesIO()
    changed.save_as(buffer, enforce_file_format=True)
    data[0] = buffer.getvalue()
    data.append(_away())
    records = {p: InstanceRecord.from_file(each) for p, each in enumerate(data)}

    (outcome,) = list(
        find_face_blocks(
            records,
            lambda position: data[position],
            confirmed={_outcome(_away()).block_sha256},
        ).values()
    )

    # The same block, of other files, which the confirmation does not cover.
    assert outcome.block == _outcome().block
    assert _held_for_eyes(outcome)
    assert outcome.block_sha256 != _outcome(_away()).block_sha256


def test_without_sheets_a_series_is_held_with_its_digest_alone():
    outcome = _outcome(_away(), sheets=False)

    assert outcome.eyes is EyeCheck.DISAGREE and outcome.held
    assert outcome.block_sha256 == _outcome(_away()).block_sha256
    assert outcome.sheet is None


def test_the_counts_give_each_defaced_series_by_its_eyes():
    held = _outcome(_away())
    counts = face_blocks.FaceBlockCounts()

    counts.record(
        [
            held,
            _outcome(_away(), confirmed={held.block_sha256}),
            _outcome(),
            SeriesDefacing(None, SeriesProblem.TARGET_IN_BLOCK),
        ]
    )

    assert counts.defaced == 3
    assert counts.eyes_unconfirmed == 1
    assert counts.eyes_confirmed == 1
    assert counts.not_defaced == {SeriesProblem.TARGET_IN_BLOCK: 1}


def test_a_frame_whose_eyes_are_unconfirmed_is_defaced_and_unconfirmed():
    held = _outcome(_away())
    data = [*_head_files(), _away()]
    records = {p: InstanceRecord.from_file(each) for p, each in enumerate(data)}

    defaced = face_blocks.find_defaced(records, {"held": held})
    confirmed = face_blocks.find_defaced(
        records,
        {"confirmed": _outcome(_away(), confirmed={held.block_sha256})},
    )

    assert defaced.frames == confirmed.frames == {files.FRAME}
    assert defaced.unconfirmed == {files.FRAME}
    assert confirmed.unconfirmed == frozenset()


def test_unconfirmed_frames_are_among_the_defaced():
    with pytest.raises(ValueError):
        face_blocks.Defaced(frozenset(), frozenset(), frozenset({files.FRAME}))


_DIGEST = bytes(range(32))


@pytest.mark.parametrize(
    "fields, message",
    [
        (
            {"problem": SeriesProblem.EYES_DISAGREE, "block": None, "frame": None},
            "hold a defaced series",
        ),
        ({"eyes": EyeCheck.DISAGREE}, "SHA-256"),
        ({"eyes": EyeCheck.CONFIRMED}, "SHA-256"),
        ({"block_sha256": _DIGEST}, "SHA-256"),
        ({"eyes": EyeCheck.DISAGREE, "block_sha256": b"short"}, "SHA-256"),
        ({"eyes": "disagree", "block_sha256": _DIGEST}, "eyes checked"),
        (
            {
                "eyes": EyeCheck.DISAGREE,
                "block_sha256": _DIGEST,
                "block": None,
                "frame": None,
                "problem": SeriesProblem.UNREADABLE,
            },
            "eyes checked",
        ),
        (
            {
                "eyes": EyeCheck.CONFIRMED,
                "block_sha256": _DIGEST,
                "sheet": qc_eyes.EyeSheet(np.zeros((1, 1, 3), np.uint8), (), 1, 2),
            },
            "sheet",
        ),
    ],
)
def test_a_series_outcome_is_consistent(fields, message):
    given = {"block": _BLOCK, "problem": None, "frame": files.FRAME, **fields}

    with pytest.raises(ValueError, match=message):
        SeriesDefacing(**given)


def test_a_block_digest_binds_its_sources_and_block():
    sources = [bytes([k]) * 32 for k in range(3)]
    digest = face_blocks.block_digest(sources, _BLOCK)
    moved = FaceBlock(_BLOCK.origin, _BLOCK.anterior, 1e-9, _BLOCK.globes)

    assert len(digest) == 32
    # Of the sources as a set, in any order, but not of fewer or others.
    assert face_blocks.block_digest(sources[::-1], _BLOCK) == digest
    assert face_blocks.block_digest(sources[:2], _BLOCK) != digest
    assert face_blocks.block_digest([*sources, sources[0]], _BLOCK) != digest
    assert face_blocks.block_digest(sources, moved) != digest
    swapped = FaceBlock(
        _BLOCK.origin, _BLOCK.anterior, _BLOCK.inferior_limit, _GLOBES[::-1]
    )
    assert face_blocks.block_digest(sources, swapped) != digest
    with pytest.raises(ValueError):
        face_blocks.block_digest([b"short"], _BLOCK)
