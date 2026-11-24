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

"""The QC pack's sheet of a CT series' globes beside its eye ROIs, drawn
from invented slices and contours."""

from __future__ import annotations

from pymedphys._imports import numpy as np
from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import qc_eyes
from pymedphys._dicom.deidentify.defacing import FaceBlock
from pymedphys._dicom.deidentify.qc_eyes import (
    EYE_ROWS,
    FIELD,
    PIXEL,
    WINDOW,
    EyeSheet,
    Plane,
    Sampler,
    SliceGeometry,
    eye_sheet,
    planes_of,
)

_REACH = 25.0
_GLOBES = ((-30.0, -50.0, 0.0), (30.0, -50.0, 0.0))
# Ahead of y = -60 and above z = -50.
_BLOCK = FaceBlock((0.0, -60.0, 0.0), (0.0, -1.0, 0.0), -50.0, _GLOBES)
_SIDE = round(FIELD / PIXEL)
_GUTTER = 8
_AXIAL = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0)
_LEVELS = tuple(float(z) for z in range(-20, 21, 4))


def _slices(levels=_LEVELS, orientation=_AXIAL):
    return [
        SliceGeometry((-100.0, -100.0, z), orientation, (1.0, 1.0), (200, 200))
        for z in levels
    ]


def _circle(centre, radius, count=64):
    x, y, z = centre
    angles = np.linspace(0, 2 * np.pi, count, endpoint=False)
    return np.stack(
        [x + radius * np.cos(angles), y + radius * np.sin(angles), np.full(count, z)],
        axis=-1,
    )


def _roi(centre, radius=10.0):
    return [("CLOSED_PLANAR", _circle(centre, radius))]


def _colours(image):
    return {tuple(int(v) for v in pixel) for pixel in image.reshape(-1, 3)}


# The planes.


def test_each_row_is_an_axial_coronal_and_sagittal_plane_through_a_globe():
    planes = planes_of(_BLOCK, [], _REACH)

    assert planes == tuple(
        Plane(axis, globe) for globe in _GLOBES for axis in (2, 1, 0)
    )


def test_an_eye_within_reach_of_a_globe_adds_no_row():
    rois = [_roi(_GLOBES[0]), _roi(_GLOBES[1], radius=_REACH - 0.01)]

    assert len(planes_of(_BLOCK, rois, _REACH)) == 6


def test_each_eye_that_disagrees_adds_a_row_through_its_farthest_point():
    near = _roi((30.0, -50.0, -30.0), radius=1.0)
    far = _roi((30.0, -50.0, -60.0), radius=1.0)

    planes = planes_of(_BLOCK, [near, far], _REACH)

    assert len(planes) == 12
    # The farthest first, each through the ROI's point farthest from both.
    farthest = planes[6].centre
    assert farthest[2] == -60.0
    assert np.isclose(
        np.linalg.norm(np.subtract(farthest, _GLOBES[1])),
        np.max(np.linalg.norm(far[0][1] - _GLOBES[1], axis=1)),
    )
    assert planes[9].centre[2] == -30.0
    assert [plane.axis for plane in planes[6:]] == [2, 1, 0, 2, 1, 0]


def test_no_more_than_the_most_rows_of_eyes_are_drawn():
    rois = [_roi((30.0, -50.0, -30.0 - k), radius=1.0) for k in range(EYE_ROWS + 3)]

    planes = planes_of(_BLOCK, rois, _REACH)

    assert len(planes) == 3 * (2 + EYE_ROWS)
    # Those kept are the farthest.
    assert min(plane.centre[2] for plane in planes) == -30.0 - (EYE_ROWS + 2)
    assert max(plane.centre[2] for plane in planes[6:]) <= -30.0 - 3 + 1


def test_an_eye_with_a_point_not_a_number_disagrees_through_its_finite_points():
    within = _circle(_GLOBES[1], 5.0)
    within[0] = np.nan

    planes = planes_of(_BLOCK, [[("CLOSED_PLANAR", within)]], _REACH)

    assert len(planes) == 9
    assert all(np.isfinite(planes[6].centre))


def test_an_eye_with_no_finite_point_or_no_contour_adds_no_row():
    unplaceable = np.full((4, 3), np.nan)

    assert len(planes_of(_BLOCK, [[("CLOSED_PLANAR", unplaceable)], []], _REACH)) == 6


# The tiles' geometry.


@pytest.mark.parametrize(
    "axis, step, moves",
    [
        # Axial, from the feet: the patient's left to the viewer's right,
        # posterior down.
        (2, (1.0, 0.0, 0.0), (0, 1)),
        (2, (0.0, 1.0, 0.0), (1, 0)),
        # Coronal, from the front: the patient's left to the viewer's
        # right, superior up.
        (1, (1.0, 0.0, 0.0), (0, 1)),
        (1, (0.0, 0.0, 1.0), (-1, 0)),
        # Sagittal, from the patient's left: posterior to the viewer's
        # right, so anterior on the left, superior up.
        (0, (0.0, 1.0, 0.0), (0, 1)),
        (0, (0.0, 0.0, 1.0), (-1, 0)),
    ],
)
def test_a_tile_is_oriented_as_a_radiologist_reads_it(axis, step, moves):
    centre = (10.0, -20.0, 30.0)
    plane = Plane(axis, centre)
    middle = (_SIDE - 1) / 2

    row, column = plane.pixel(np.add(centre, np.multiply(step, PIXEL)))

    assert plane.pixel(centre) == (middle, middle)
    assert (row - middle, column - middle) == pytest.approx(moves)


@pytest.mark.parametrize("axis", [0, 1, 2])
def test_each_pixel_centre_projects_to_its_own_row_and_column(axis):
    plane = Plane(axis, (1.0, 2.0, 3.0))
    points = plane.points()

    rows, columns = plane.pixel(points)

    assert points.shape == (_SIDE, _SIDE, 3)
    assert np.allclose(points[..., axis], plane.centre[axis])
    assert np.allclose(rows, np.arange(_SIDE)[:, np.newaxis])
    assert np.allclose(columns, np.arange(_SIDE)[np.newaxis, :])


# Sampling.


def test_an_axial_plane_is_taken_through_the_nearest_slice():
    sampler = Sampler([Plane(2, (0.0, 0.0, 5.5))], _slices())

    ((plane, _, _),) = sampler.tiles()

    assert plane.centre[2] == 4.0
    assert sampler.wanted == {_LEVELS.index(4.0)}
    assert sampler.half_spacing == 2.0
    assert np.allclose(sampler.normal, (0, 0, 1))


def test_a_plane_across_the_slices_wants_only_those_within_its_field():
    slices = _slices()
    sampler = Sampler([Plane(1, (0.0, -50.0, 0.0))], slices)

    for index in sampler.wanted:
        sampler.add(index, np.full((200, 200), _LEVELS[index] * 10, np.float32))
    ((_, values, beyond),) = sampler.tiles()

    # Every slice, since the stack is shorter than the tile; each pixel
    # from the slice nearest it, and none beyond the stack, half a spacing
    # past its last slice.
    assert sampler.wanted == set(range(len(slices)))
    z = Plane(1, (0.0, -50.0, 0.0)).points()[..., 2]
    nearest = np.asarray(_LEVELS)[np.argmin(np.abs(z[..., None] - _LEVELS), axis=-1)]
    inside = np.abs(z) <= 22.0 + 1e-6
    inside &= np.abs(Plane(1, (0.0, -50.0, 0.0)).points()[..., 0]) <= 99.5
    assert np.array_equal(~beyond, inside)
    assert np.array_equal(values[inside], (nearest * 10)[inside])
    assert np.isnan(values[beyond]).all()


def test_slices_given_in_any_order_are_sampled_alike():
    planes = [Plane(1, (0.0, -50.0, 0.0)), Plane(2, (0.0, 0.0, 7.0))]
    ordered, shuffled = _slices(), _slices(_LEVELS[::-1])
    tiles = []
    for slices in (ordered, shuffled):
        sampler = Sampler(planes, slices)
        for index in sampler.wanted:
            level = slices[index].position[2]
            sampler.add(index, np.full((200, 200), level, np.float32))
        tiles.append(sampler.tiles())

    for (plane, values, beyond), (other, again, past) in zip(*tiles):
        assert plane == other
        assert np.array_equal(values, again, equal_nan=True)
        assert np.array_equal(beyond, past)


def test_a_sampler_needs_a_plane_and_a_slice():
    with pytest.raises(ValueError):
        Sampler([], _slices())
    with pytest.raises(ValueError):
        Sampler([Plane(2, (0.0, 0.0, 0.0))], [])


def test_one_slice_is_sampled_within_half_its_largest_pixel_spacing():
    (geometry,) = _slices((0.0,))
    sampler = Sampler([Plane(1, (0.0, -50.0, 0.0))], [geometry])

    assert sampler.half_spacing == 0.5
    assert sampler.wanted == {0}


# The sheet.


def _sheet(rois=(), levels=_LEVELS, values=None):
    slices = _slices(levels)
    planes = planes_of(_BLOCK, rois, _REACH)
    sampler = Sampler(planes, slices)
    for index in sorted(sampler.wanted):
        sampler.add(
            index,
            np.full((200, 200), 40.0, np.float32) if values is None else values,
        )
    frames = tuple((index, 0) for index in sorted(sampler.wanted))
    return eye_sheet(_BLOCK, rois, _REACH, sampler, frames, len(slices)), sampler


def test_the_sheet_lays_its_tiles_out_in_rows_of_three():
    sheet, _ = _sheet([_roi((30.0, -50.0, -40.0), radius=1.0)])

    assert sheet.rows == 3
    assert sheet.image.dtype == np.uint8
    assert sheet.image.shape == (3 * _SIDE + 2 * _GUTTER, 3 * _SIDE + 2 * _GUTTER, 3)
    # Grey gutters between the tiles.
    assert (sheet.image[_SIDE : _SIDE + _GUTTER] == 128).all()
    assert (sheet.image[:, _SIDE : _SIDE + _GUTTER] == 128).all()


def test_the_sheet_windows_the_slices_tints_the_block_and_greys_beyond():
    sheet, _ = _sheet()
    axial = sheet.image[:_SIDE, :_SIDE]
    plane = Plane(2, _GLOBES[0])
    inside = _BLOCK.contains(plane.points())
    grey = round((40.0 - WINDOW[0]) / (WINDOW[1] - WINDOW[0]) * 255)
    tinted = np.round(grey * 0.65 + np.array((0, 128, 255)) * 0.35)
    colours = _colours(axial)

    assert inside.any() and (~inside).any()
    assert (grey, grey, grey) in colours
    assert tuple(int(v) for v in tinted) in colours
    # The coronal tile reaches past the stack's top and bottom.
    assert (40, 40, 40) in _colours(sheet.image[:_SIDE, _SIDE + _GUTTER : 2 * _SIDE])
    # The globes, cyan.
    assert (0, 255, 255) in colours


def test_an_eye_is_drawn_yellow_within_reach_and_red_beyond():
    across = [("CLOSED_PLANAR", _circle((45.0, -50.0, 0.0), 20.0))]

    sheet, _ = _sheet([across])

    # From 5 mm of the left globe to 35 mm from it.
    colours = _colours(sheet.image)
    assert (255, 32, 0) in colours
    assert (255, 255, 0) in colours


def test_an_eye_off_the_plane_is_not_drawn_on_it():
    above = [("CLOSED_PLANAR", _circle((30.0, -50.0, 12.0), 30.0))]

    sheet, _ = _sheet([above])

    # The globes' axial tiles, through z = 0, do not show it; its own row
    # does, through the slice nearest it.
    for row in range(2):
        start = row * (_SIDE + _GUTTER)
        tile = sheet.image[start : start + _SIDE, :_SIDE]
        assert (255, 32, 0) not in _colours(tile)
    tile = sheet.image[2 * (_SIDE + _GUTTER) :, :_SIDE]
    assert (255, 32, 0) in _colours(tile)


def test_a_point_contour_is_drawn_at_its_points():
    # 31 mm from the left globe, on a slice.
    point = [("POINT", np.array([[30.0, -80.0, 8.0]]))]

    sheet, _ = _sheet([point])

    assert sheet.rows == 3
    tile = sheet.image[2 * (_SIDE + _GUTTER) :, :_SIDE]
    assert (255, 32, 0) in _colours(tile)


def test_the_sheet_shows_its_size_and_counts_but_not_its_image():
    sheet = EyeSheet(np.zeros((2, 2, 3), np.uint8), ((0, 0),), 4, 2)

    assert repr(sheet) == (
        "EyeSheet(shape=(2, 2, 3), frames=1, total_frames=4, rows=2)"
    )


def test_padding_is_black():
    values = np.full((200, 200), np.nan, np.float32)

    sheet, _ = _sheet(values=values)

    # The first axial tile at (-90, 20), on the slices but outside the
    # block, away from the globes' marks.
    assert tuple(int(v) for v in sheet.image[300, 40]) == (0, 0, 0)


def test_a_malformed_contour_too_long_to_sample_shows_only_its_points():
    # pylint: disable = protected-access
    huge = np.array([[30.0, -50.0, 0.0], [30.0 + 1e9, -50.0, 0.0]])

    sheet, _ = _sheet([[("OPEN_PLANAR", huge)]])

    assert sheet.rows == 3
    assert qc_eyes._SAMPLES == 1 << 20
