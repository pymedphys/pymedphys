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

"""Finding the face block of a head CT, on an analytic head."""

from __future__ import annotations

import dataclasses

import pytest

from pymedphys._imports import numpy as np

from pymedphys._dicom.deidentify import defacing

from . import _synthetic_head as head

_FIXED = defacing.FaceBlock(
    (0.0, -61.0, 20.0),
    (0.0, -1.0, 0.0),
    7.5,
    ((-32.0, -66.0, 20.0), (32.0, -66.0, 20.0)),
)


def _finder(scan: head.Scan) -> defacing.FaceFinder:
    return defacing.FaceFinder(
        scan.orientation, scan.positions, scan.spacing, scan.shape
    )


def _block(scan: head.Scan, *heads: head.Head) -> defacing.FaceBlock:
    finder = _finder(scan)
    for values in scan.slices(*heads):
        finder.add(values)
    return finder.block()


def _assert_around_the_globes(block: defacing.FaceBlock) -> None:
    expected = (
        (-head.GLOBE_X, head.GLOBE_Y, head.GLOBE_Z),
        (head.GLOBE_X, head.GLOBE_Y, head.GLOBE_Z),
    )
    np.testing.assert_allclose(block.globes, expected, atol=1.5)
    np.testing.assert_allclose(block.anterior, (0, -1, 0), atol=0.02)
    np.testing.assert_allclose(
        block.origin, (0, head.GLOBE_Y + defacing.MARGIN, head.GLOBE_Z), atol=1.5
    )
    # From the globes' inferior edge, or a few millimetres lower, up.
    inferior_edge = head.GLOBE_Z - head.GLOBE_RADIUS
    assert inferior_edge - 5.0 <= block.inferior_limit <= inferior_edge


@pytest.mark.parametrize(
    "scan",
    [
        head.axial(),
        head.axial(feet_first=True),
        head.axial(prone=True),
        head.axial(prone=True, feet_first=True),
        head.sagittal(),
    ],
    ids=["head-first-supine", "feet-first", "prone", "prone-feet-first", "sagittal"],
)
def test_the_block_is_found_from_the_globes_whatever_the_orientation(scan):
    _assert_around_the_globes(_block(scan))


@pytest.mark.parametrize(
    "scan, anatomy",
    [
        (head.axial(), head.Head(noise=40.0, seed=1)),
        (head.axial(thickness=5.0), head.Head()),
        (head.axial(spacing=1.5, thickness=3.0), head.Head()),
        (
            head.axial(thickness=5.0, extent=((-100, 100), (-130, 110), (-800, 120))),
            head.Head(),
        ),
    ],
    ids=["noisy", "thick-slices", "coarse-pixels", "long-volume"],
)
def test_the_block_is_found_through_noise_and_coarser_sampling(scan, anatomy):
    _assert_around_the_globes(_block(scan, anatomy))


def test_the_block_holds_the_upper_face_and_keeps_the_rest():
    block = _block(head.axial())
    points = {
        "front of each globe": [(-32, -75, 20), (32, -75, 20)],
        "bridge of the nose": [(0, -90, 12)],
        "forehead": [(0, -85, 60), (0, -70, 100)],
        "mask and air before the face": [(0, -125, 30), (-90, -125, 115)],
    }
    kept = {
        "back of each globe": [(-32, -57, 20), (32, -57, 20)],
        "tip of the nose": [(0, -118, -15)],
        "mouth and chin": [(0, -80, -50), (0, -60, -100)],
        "back of the head": [(0, 90, 30), (0, 60, 100)],
    }
    for part, where in points.items():
        assert block.contains(np.array(where)).all(), part
    for part, where in kept.items():
        assert not block.contains(np.array(where)).any(), part


@pytest.mark.parametrize(
    "anatomy",
    [head.Head(eyes=(True, False)), head.Head(eyes=(False, True))],
    ids=["no-left-eye", "no-right-eye"],
)
def test_a_head_without_both_eyes_is_refused(anatomy):
    with pytest.raises(defacing.FaceBlockRefused) as refused:
        _block(head.axial(), anatomy)

    assert refused.value.problem is defacing.FaceBlockProblem.NO_EYES


def test_a_volume_that_cuts_through_the_eyes_is_refused():
    scan = head.axial(extent=((-100, 100), (-130, 110), (-120, 25)))

    with pytest.raises(defacing.FaceBlockRefused) as refused:
        _block(scan)

    assert refused.value.problem is defacing.FaceBlockProblem.NO_EYES


def test_spheres_without_a_bony_orbit_are_not_eyes():
    with pytest.raises(defacing.FaceBlockRefused) as refused:
        _block(head.axial(), head.Head(orbits=False, skull=False))

    assert refused.value.problem is defacing.FaceBlockProblem.NO_EYES


def test_two_heads_in_view_are_refused():
    scan = head.axial(spacing=1.5, extent=((-230, 230), (-130, 110), (-120, 120)))

    with pytest.raises(defacing.FaceBlockRefused) as refused:
        _block(scan, head.Head(shift=-120.0), head.Head(shift=120.0))

    assert refused.value.problem is defacing.FaceBlockProblem.AMBIGUOUS_EYES
    assert str(refused.value) == "ambiguous-eyes"


def test_the_block_is_the_same_each_time():
    scan = head.axial(feet_first=True)

    assert _block(scan) == _block(scan)


def test_a_block_needs_every_slice():
    scan = head.axial()
    finder = _finder(scan)
    for values, _ in zip(scan.slices(), range(len(scan.positions) - 1)):
        finder.add(values)

    with pytest.raises(ValueError, match="every slice"):
        finder.block()


@pytest.mark.parametrize(
    "scan",
    [
        head.axial(),
        head.axial(prone=True, feet_first=True),
        head.sagittal(),
        head.tilted(degrees=15.0),
    ],
    ids=["axial", "prone-feet-first", "sagittal", "gantry-tilt-15"],
)
def test_a_slice_mask_marks_the_pixels_whose_centres_are_in_the_block(scan):
    block = _FIXED

    marked = []
    for index in (0, len(scan.positions) // 2, len(scan.positions) - 1):
        mask = block.slice_mask(
            scan.positions[index], scan.orientation, scan.spacing, scan.shape
        )
        points = scan.points(index)
        expected = (points[..., 1] < -61.0) & (points[..., 2] > 7.5)
        assert mask.shape == scan.shape
        np.testing.assert_array_equal(mask, expected)
        marked.append(int(mask.sum()))

    assert 0 < sum(marked) < 3 * scan.shape[0] * scan.shape[1]


def test_a_point_on_either_plane_is_outside_the_block():
    block = _FIXED
    points = np.array([[0.0, -61.0, 50.0], [0.0, -80.0, 7.5], [0.0, -61.1, 7.6]])

    np.testing.assert_array_equal(block.contains(points), [False, False, True])


@pytest.mark.parametrize("turn", [-25.0, 20.0])
def test_the_block_turns_with_a_head_turned_in_its_mask(turn):
    block = _block(head.axial(), head.Head(turn=turn))
    angle = np.radians(turn)

    np.testing.assert_allclose(
        block.anterior, (np.sin(angle), -np.cos(angle), 0), atol=0.03
    )
    # The front of each globe, in the head's own frame, is in the block, and
    # the back of each is not.
    for side in (-1, 1):
        for depth, inside in ((-9.0, True), (9.0, False)):
            x, y = side * head.GLOBE_X, head.GLOBE_Y + depth
            point = (
                x * np.cos(angle) - y * np.sin(angle),
                x * np.sin(angle) + y * np.cos(angle),
                head.GLOBE_Z,
            )
            assert block.contains(np.array(point)) == inside, (side, depth)


def test_a_head_recorded_facing_the_wrong_way_is_refused():
    with pytest.raises(defacing.FaceBlockRefused) as refused:
        _block(head.axial(), head.Head(facing_back=True))

    assert refused.value.problem is defacing.FaceBlockProblem.HEAD_NOT_BEHIND_EYES


@pytest.mark.parametrize(
    "scan",
    [
        head.tilted(degrees=15.0),
        head.tilted(degrees=0.5),
        dataclasses.replace(
            head.axial(),
            orientation=(
                float(np.cos(np.radians(10))),
                float(np.sin(np.radians(10))),
                0.0,
                float(-np.sin(np.radians(10))),
                float(np.cos(np.radians(10))),
                0.0,
            ),
        ),
    ],
    ids=["gantry-tilt-15", "gantry-tilt-half-degree", "oblique-10"],
)
def test_a_volume_not_along_the_patient_axes_is_refused(scan):
    with pytest.raises(defacing.FaceBlockRefused) as refused:
        _finder(scan)

    assert refused.value.problem is defacing.FaceBlockProblem.NOT_ALONG_PATIENT_AXES


def test_two_slices_at_one_position_are_refused():
    scan = head.axial()
    scan = dataclasses.replace(scan, positions=scan.positions[:1] + scan.positions[:-1])

    with pytest.raises(defacing.FaceBlockRefused) as refused:
        _finder(scan)

    assert refused.value.problem is defacing.FaceBlockProblem.NOT_ALONG_PATIENT_AXES
