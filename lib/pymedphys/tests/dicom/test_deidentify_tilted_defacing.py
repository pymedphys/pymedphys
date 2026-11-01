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

"""Defacing CT slices that do not lie along the patient's axes, as a
gantry tilt, a shear, or an oblique stack lays them, on an analytic head.
Every UID and value here is invented.

Most tests give each tilted scan of the analytic head the block found from
its untilted scan, so that what each pixel should become is known exactly:
the block lies in the patient's coordinates, where the head is the same
however it is scanned. Those of a run's outcome use the block that the
finder finds from the tilted slices themselves, and those of the slices it
is given use a stand-in finder that records them.
"""

from __future__ import annotations

import functools
import io
import math

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import face_blocks
from pymedphys._dicom.deidentify.defacing import FaceBlock
from pymedphys._dicom.deidentify.dose_defacing import DoseBlock
from pymedphys._dicom.deidentify.face_blocks import (
    CtDefacer,
    find_face_blocks,
    kept_slices,
)
from pymedphys._dicom.deidentify.references import InstanceRecord
from pymedphys._dicom.deidentify.region_defacing import PetDefacer, cut_contours
from pymedphys._dicom.deidentify.target_hulls import SliceExtent

from . import _synthetic_head as head
from . import _synthetic_head_dicom as files

# Coarse, as in the face block tests, to keep the files small.
_SPACING = 2.0
_THICKNESS = 3.0
_EXTENT = ((-100, 100), (-130, 110), (-60, 120))
_AXIAL = head.axial(spacing=_SPACING, thickness=_THICKNESS, extent=_EXTENT)


def _tilted(degrees: float, heights: tuple[float, float]) -> head.Scan:
    """The head tilted by ``degrees`` about its left-right axis, the slices
    stepped along the table over ``heights``, which reach the whole head
    for the tilt."""
    return head.tilted(
        degrees=degrees,
        spacing=_SPACING,
        thickness=_THICKNESS,
        extent=(_EXTENT[0], _EXTENT[1], heights),
    )


# A positive tilt raises each slice's front, a negative one lowers it.
TILTED = {
    "gantry-tilt-15": _tilted(15.0, (-120, 180)),
    "gantry-tilt-30": _tilted(30.0, (-160, 200)),
    "gantry-tilt-minus-15": _tilted(-15.0, (-60, 190)),
    "gantry-tilt-minus-30": _tilted(-30.0, (-60, 260)),
    "gantry-tilt-15-sheared": head.sheared(
        head.axial(
            spacing=_SPACING,
            thickness=_THICKNESS,
            extent=((-100, 100), (-130, 180), (-60, 120)),
        ),
        15.0,
    ),
    "oblique-about-z-10": head.oblique(_AXIAL, head.rotation(about_z=10.0)),
    "compound-oblique": head.oblique(_AXIAL, head.rotation(about_x=12.0, about_y=-8.0)),
}

HEADS = {
    "plain": head.Head(noise=0.0),
    "frontal-sinus": head.Head(noise=0.0, sinus=True),
    "muscles-poles-and-apex": head.Head(noise=0.0, muscles=4.0, poles=True, apex=True),
    "bolus": head.Head(noise=0.0, bolus=True),
}


@functools.cache
def _block() -> FaceBlock:
    """The block that the finder finds from the untilted head."""
    data = files.ct_files(_AXIAL, head.Head(noise=0.0))
    records = {index: InstanceRecord.from_file(each) for index, each in enumerate(data)}
    (outcome,) = list(
        find_face_blocks(records, lambda position: data[position]).values()
    )
    assert outcome.block is not None
    return outcome.block


def _floor() -> float:
    return max(globe[2] for globe in _block().globes) + face_blocks.CAVITY_FLOOR


@functools.cache
def _files(scan_name: str, head_name: str = "plain") -> tuple[bytes, ...]:
    return tuple(files.ct_files(TILTED[scan_name], HEADS[head_name]))


def _mask(block: FaceBlock, data: bytes, targets=None) -> np.ndarray:
    """The pixels of one slice that defacing writes as air."""
    dataset = pydicom.dcmread(io.BytesIO(data))
    stored = np.asarray(dataset.pixel_array)
    defacer = (
        CtDefacer(block, dataset)
        if targets is None
        else CtDefacer(block, dataset, targets)
    )
    found = defacer.mask(0, stored)
    return np.zeros(stored.shape, dtype=bool) if found is None else found.mask


class _GivenFinder:
    """A stand-in for the face block's finder that takes any stack and gives
    the untilted head's block, recording the positions that it is given."""

    given: list[tuple[float, float, float]] = []

    def __init__(self, orientation, positions, spacing, shape) -> None:
        del orientation, spacing, shape
        _GivenFinder.given = [tuple(each) for each in positions]

    def add(self, frame) -> None:
        del frame

    def block(self) -> FaceBlock:
        return _block()


@pytest.fixture(name="given_finder")
def fixture_given_finder(monkeypatch):
    _block()
    monkeypatch.setattr(face_blocks.defacing, "FaceFinder", _GivenFinder)
    return _GivenFinder


def _outcome(data: tuple[bytes, ...], *others: bytes):
    every = list(data) + list(others)
    records = {
        position: InstanceRecord.from_file(each) for position, each in enumerate(every)
    }
    (outcome,) = list(
        find_face_blocks(records, lambda position: every[position]).values()
    )
    return outcome


# Writing air.


@pytest.mark.parametrize("head_name", HEADS.keys())
@pytest.mark.parametrize("scan_name", TILTED.keys())
def test_a_tilted_slice_is_written_as_air_where_an_axial_one_through_each_pixel_is(
    scan_name, head_name
):
    """Each pixel is judged by its own centre: in the block, below the
    floor by its own height, it is air, and above the floor it is kept
    exactly where the head's brain lies, whatever heights the slice spans,
    so the eyes, the forehead, the bolus, and the frontal sinus are air."""
    block, floor = _block(), _floor()
    scan, anatomy = TILTED[scan_name], HEADS[head_name]
    brain_kept = eye_written = sinus_written = 0

    for index, data in enumerate(_files(scan_name, head_name)):
        mask = _mask(block, data)
        points = scan.points(index)
        values = head.hounsfield(points, anatomy)
        inside = block.contains(points)
        brain = (values == head.BRAIN) & (points[..., 2] > floor)

        np.testing.assert_array_equal(mask, inside & ~brain, err_msg=str(index))
        brain_kept += int((inside & brain).sum())
        eye_written += int((inside & np.isin(values, [head.VITREOUS, head.LENS])).sum())
        sinus_written += int((inside & _in_sinus(points)).sum())

    assert brain_kept > 1000
    assert eye_written > 500
    if anatomy.sinus:
        assert sinus_written > 50


def _in_sinus(points: np.ndarray) -> np.ndarray:
    (x0, y0, z0), (a, b, c) = head.SINUS_CENTRE, head.SINUS_AXES
    x, y, z = points[..., 0] - x0, points[..., 1] - y0, points[..., 2] - z0
    return (x / a) ** 2 + (y / b) ** 2 + (z / c) ** 2 <= 1


def test_the_brain_above_the_floor_joins_the_brain_behind_the_plane_below_it():
    """A slice whose front is raised by a tilt reaches the brain above the
    floor ahead of the plane only through the brain below the floor, which
    it writes as air: that brain is still kept, as an axial slice through
    it would keep it."""
    block, floor = _block(), _floor()
    scan = TILTED["gantry-tilt-30"]
    joined_below = 0

    for index, data in enumerate(_files("gantry-tilt-30")):
        mask = _mask(block, data)
        points = scan.points(index)
        brain = head.hounsfield(points, HEADS["plain"]) == head.BRAIN
        inside = block.contains(points)
        kept = inside & brain & (points[..., 2] > floor) & ~mask
        # Along a column of the slice, from its brain kept ahead of the
        # plane back to the plane, the block holds only brain below the
        # floor, which is written as air: the kept brain joins the brain
        # behind the plane only through it.
        for column in np.flatnonzero(kept.any(axis=0)):
            last = np.flatnonzero(kept[:, column]).max()
            between = np.flatnonzero(inside[last + 1 :, column]) + last + 1
            if between.size and (points[between, column, 2] <= floor).all():
                assert brain[between, column].all()
                assert mask[between, column].all()
                joined_below += 1

    assert joined_below >= 2


def test_the_rule_for_an_axial_slice_is_unchanged():
    block, floor = _block(), _floor()

    for index, data in enumerate(files.ct_files(_AXIAL, HEADS["frontal-sinus"])):
        points = _AXIAL.points(index)
        values = head.hounsfield(points, HEADS["frontal-sinus"])
        brain = (values == head.BRAIN) & (points[..., 2] > floor)

        np.testing.assert_array_equal(
            _mask(block, data), block.contains(points) & ~brain
        )


# Which slices the finder is given.


def _top(scan: head.Scan, index: int) -> float:
    return float(scan.points(index)[..., 2].max())


@pytest.mark.parametrize(
    "scan",
    [
        TILTED["gantry-tilt-30"],
        TILTED["gantry-tilt-minus-15"],
        TILTED["compound-oblique"],
        _AXIAL,
    ],
    ids=["gantry-tilt-30", "gantry-tilt-minus-15", "compound-oblique", "axial"],
)
def test_the_finder_is_given_each_slice_that_reaches_within_head_reach_of_the_top(
    given_finder, monkeypatch, scan
):
    monkeypatch.setattr(face_blocks, "HEAD_REACH", 60.0)
    highest = max(_top(scan, index) for index in range(len(scan.positions)))

    _outcome(tuple(files.ct_files(scan, HEADS["plain"])))

    expected = {
        index
        for index in range(len(scan.positions))
        if _top(scan, index) >= highest - 60.0
    }
    # Each position as the files write it, to 16 characters, is the scan's
    # nearest.
    positions = np.array(scan.positions)
    given = {
        int(np.argmin(np.linalg.norm(positions - np.array(each), axis=1)))
        for each in given_finder.given
    }
    assert len(given) == len(given_finder.given)
    assert given == expected
    assert 0 < len(given) < len(scan.positions)


def test_every_slice_of_a_sagittal_stack_is_given_to_the_finder(
    given_finder, monkeypatch
):
    monkeypatch.setattr(face_blocks, "HEAD_REACH", 60.0)
    scan = head.sagittal(spacing=4.0, thickness=8.0)

    _outcome(tuple(files.ct_files(scan, HEADS["plain"])))

    assert len(given_finder.given) == len(scan.positions)


@pytest.mark.parametrize(
    "scan_name", ["gantry-tilt-30", "gantry-tilt-15-sheared", "compound-oblique"]
)
def test_a_tilted_series_is_defaced_by_its_own_block_as_each_pixel_lies(scan_name):
    """The finder finds the block from the tilted slices themselves, near
    the untilted head's, and the run writes air by it as each pixel lies."""
    scan, data = TILTED[scan_name], _files(scan_name)
    outcome = _outcome(data)

    assert outcome.problem is None and outcome.frame == files.FRAME
    np.testing.assert_allclose(outcome.block.globes, _block().globes, atol=2.0)
    floor = max(globe[2] for globe in outcome.block.globes) + face_blocks.CAVITY_FLOOR
    for index, each in enumerate(data):
        points = scan.points(index)
        brain = (head.hounsfield(points, HEADS["plain"]) == head.BRAIN) & (
            points[..., 2] > floor
        )
        np.testing.assert_array_equal(
            _mask(outcome.block, each), outcome.block.contains(points) & ~brain
        )


# Targets on tilted slices.

_GLOBE_FRONT = (-head.GLOBE_X, -76.0, head.GLOBE_Z)


def _distance_to_square(points: np.ndarray, centre, half: float) -> np.ndarray:
    """Each point's distance from an axial square of half side ``half``."""
    x, y, z = centre
    dx = np.maximum(np.abs(points[..., 0] - x) - half, 0)
    dy = np.maximum(np.abs(points[..., 1] - y) - half, 0)
    return np.sqrt(dx**2 + dy**2 + (points[..., 2] - z) ** 2)


@pytest.mark.parametrize("scan_name", ["gantry-tilt-30", "gantry-tilt-15-sheared"])
def test_a_target_on_a_tilted_ct_keeps_the_pixels_whose_boxes_meet_it(scan_name):
    scan = TILTED[scan_name]
    data = _files(scan_name)
    outcome = _outcome(data, files.structure_set([("PTV", files.square(_GLOBE_FRONT))]))
    block, targets = outcome.block, outcome.targets
    normal = np.cross(scan.orientation[:3], scan.orientation[3:])
    heights = np.array([np.dot(position, normal) for position in scan.positions])
    # Every point of the target, a 4 mm square, at 0.1 mm.
    grid = np.linspace(-2.0, 2.0, 41)
    samples = np.array(
        [
            (_GLOBE_FRONT[0] + dx, _GLOBE_FRONT[1] + dy, _GLOBE_FRONT[2])
            for dx in grid
            for dy in grid
        ]
    )
    kept_for_target = 0

    assert outcome.problem is None and targets.in_block
    assert targets.depth == pytest.approx(
        np.min(np.diff(np.sort(heights))) / 2, abs=1e-5
    )
    for index, each in enumerate(data):
        plain = _mask(block, each)
        around = _mask(block, each, targets)
        assert not (around & ~plain).any()
        kept = plain & ~around
        kept_for_target += int(kept.sum())
        points = scan.points(index)
        # Each kept pixel's box, its square and the depth either side, may
        # meet the target: its centre lies within the box's half diagonal.
        reach = math.sqrt(2 * (_SPACING / 2) ** 2 + targets.depth**2) + 0.02
        assert (_distance_to_square(points[kept], _GLOBE_FRONT, 2.0) <= reach).all()
        # Each point of the target placed on this slice, within the depth,
        # is on a pixel that is kept, or that is not written as air.
        near = np.abs(samples @ normal - heights[index]) <= targets.depth
        offsets = samples[near] - np.array(scan.positions[index])
        rows = np.rint(offsets @ np.array(scan.orientation[3:]) / _SPACING).astype(int)
        columns = np.rint(offsets @ np.array(scan.orientation[:3]) / _SPACING).astype(
            int
        )
        assert not around[rows, columns].any()

    assert kept_for_target > 0


def test_a_tilted_stack_s_far_slices_do_not_decide_whether_a_target_is_shown():
    """A tilt steps each slice's pixels within the plane, so the slices far
    from a target share little of the plane with those that show it: only
    the slices nearest the target decide."""
    scan = TILTED["gantry-tilt-30"]
    outcome = _outcome(
        _files("gantry-tilt-30"),
        files.structure_set([("PTV", files.square(_GLOBE_FRONT))]),
    )
    extent = SliceExtent.of(
        [(position, scan.orientation) for position in scan.positions],
        scan.spacing,
        scan.shape,
        outcome.targets.depth,
    )
    _, down_column = extent.within(-math.inf, math.inf)
    along = float(np.dot(_GLOBE_FRONT, down_column.direction))

    # Every slice's pixels together do not reach the target's place down a
    # column, so judged by them all it would hold the series.
    assert not down_column.low <= along <= down_column.high
    assert outcome.problem is None and outcome.targets.in_block


@pytest.mark.parametrize(
    ("y", "held"),
    [(-128.0, False), (-133.0, True)],
    ids=["within-the-nearest-slices", "beyond-the-nearest-slices"],
)
def test_a_target_beyond_its_nearest_tilted_slices_holds_the_series(y, held):
    target = files.square((-head.GLOBE_X, y, head.GLOBE_Z), half=0.5)

    outcome = _outcome(_files("gantry-tilt-30"), files.structure_set([("PTV", target)]))

    if held:
        assert outcome.problem is face_blocks.SeriesProblem.TARGET_IN_BLOCK
    else:
        assert outcome.problem is None and outcome.targets.in_block


# RT Dose, PET, and contours on their own grids beside a tilted CT.


@functools.cache
def _region(scan_name: str) -> DoseBlock:
    data = _files(scan_name)
    block = _block()
    return DoseBlock(
        block,
        kept_slices(block, range(len(data)), lambda position: data[position]),
    )


def _nearest_written(scan: head.Scan, data, points: np.ndarray):
    """Whether defacing writes air at each point's nearest pixel, of the
    nearest slice within half the slices' spacing, or None where it has
    none, and whether that pixel is the head's kept brain, by brute force
    over every slice."""
    normal = np.cross(scan.orientation[:3], scan.orientation[3:])
    heights = np.array([np.dot(position, normal) for position in scan.positions])
    reach = np.min(np.diff(np.sort(heights))) / 2
    along = points @ normal
    nearest = np.argmin(np.abs(along[:, np.newaxis] - heights[np.newaxis, :]), axis=1)
    found = np.full(len(points), -1)
    masks = {}
    for index in np.unique(nearest):
        chosen = np.flatnonzero(
            (nearest == index) & (np.abs(along - heights[index]) <= reach)
        )
        offsets = points[chosen] - np.array(scan.positions[index])
        rows = np.rint(offsets @ np.array(scan.orientation[3:]) / _SPACING).astype(int)
        columns = np.rint(offsets @ np.array(scan.orientation[:3]) / _SPACING).astype(
            int
        )
        within = (
            (rows >= 0)
            & (rows < scan.shape[0])
            & (columns >= 0)
            & (columns < scan.shape[1])
        )
        if index not in masks:
            masks[index] = _mask(_block(), data[index])
        written = masks[index][rows[within], columns[within]]
        centres = scan.points(index)[rows[within], columns[within]]
        # Kept where the pixel is in the block and not written as air.
        found[chosen[within]] = np.where(~written & _block().contains(centres), 1, 0)
    return found


@pytest.mark.parametrize("scan_name", ["gantry-tilt-30", "oblique-about-z-10"])
def test_dose_beside_a_tilted_ct_keeps_only_what_the_ct_keeps_in_the_block(
    scan_name,
):
    scan, data = TILTED[scan_name], _files(scan_name)
    region = _region(scan_name)
    # An axial dose grid over the face, at 2.5 mm.
    x, y, z = np.meshgrid(
        np.arange(-60, 61, 2.5), np.arange(-110, -40, 2.5), np.arange(0, 100, 2.5)
    )
    points = np.column_stack([x.ravel(), y.ravel(), z.ravel()])
    points = points[_block().contains(points)]

    kept = region.kept(points)

    expected = _nearest_written(scan, data, points) == 1
    np.testing.assert_array_equal(kept, expected)
    values = head.hounsfield(points, HEADS["plain"])
    assert kept.any()
    assert (points[kept, 2] > _floor()).all()
    assert not kept[np.isin(values, [head.VITREOUS, head.LENS])].any()


def test_pet_beside_a_tilted_ct_is_set_to_zero_where_the_ct_is_air():
    region = _region("gantry-tilt-30")
    for height in (head.GLOBE_Z, 60.0):
        position = (-100.0, -130.0, height)
        shape = (61, 51)
        dataset = pydicom.dcmread(
            io.BytesIO(
                files.pet(
                    np.full(shape, 100, dtype=np.uint16),
                    position=position,
                    spacing=(4.0, 4.0),
                )
            )
        )
        mask = PetDefacer(region, dataset).mask(0, dataset.pixel_array)
        rows, columns = np.mgrid[0 : shape[0], 0 : shape[1]]
        points = np.stack(
            [-100.0 + 4.0 * columns, -130.0 + 4.0 * rows, np.full(shape, height)],
            axis=-1,
        )
        inside = _block().contains(points)

        assert mask is not None
        np.testing.assert_array_equal(
            mask.mask, inside & ~region.kept(points.reshape(-1, 3)).reshape(shape)
        )
        values = head.hounsfield(points, HEADS["plain"])
        assert mask.mask[inside & np.isin(values, [head.VITREOUS, head.LENS])].all()
        if height > _floor():
            assert not mask.mask[inside & (values == head.BRAIN)].all()


def test_contours_on_a_tilted_ct_are_cut_by_the_whole_block():
    """Contours are cut by the pixels that the CT writes as air only on
    axial slices, so on a tilted CT an outline that reaches the face is cut
    by the whole block, and what is written of it lies outside the block."""
    region = _region("gantry-tilt-30")
    outline = np.array(
        [
            (75.0 * math.cos(angle), 95.0 * math.sin(angle) - 10.0, 60.0)
            for angle in np.linspace(0, 2 * math.pi, 72, endpoint=False)
        ]
    )
    dataset = pydicom.dcmread(io.BytesIO(files.structure_set([("EXTERNAL", outline)])))

    cut = cut_contours(region, dataset, files.FRAME)

    (written,) = list(cut.values())
    assert written
    for contour in written:
        assert contour.values is not None
        points = np.asarray([float(v) for v in contour.values]).reshape(-1, 3)
        ahead = (points - np.array(_block().origin)) @ np.array(_block().anterior)
        assert (ahead <= 1e-6).all()
