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

# pylint: disable = protected-access, too-many-lines
"""A deformable registration's grids in the QC pack (D-017).

Every name, UID, and data set here is invented or synthetic.
"""

import hashlib
import io
import json
import math
import shutil
import tempfile
from pathlib import Path

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import (
    face_review,
    qc_grids,
    qc_previews,
    qc_surfaces,
    run,
    run_qc,
)
from pymedphys._dicom.deidentify.face_review import (
    NO_GRIDS,
    FaceReview,
    grid_data_sha256,
    read_face_review,
    registration_frames,
)
from pymedphys._dicom.deidentify.instance_transform import (
    InstanceTransform,
    ReleaseGate,
)
from pymedphys._dicom.deidentify.policy import compose_policy
from pymedphys._dicom.deidentify.qc_attestation import Face
from pymedphys._dicom.deidentify.qc_pack import (
    GRID_KINDS,
    NO_CONTOURS_SHA256,
    NO_GRIDS_SHA256,
    NO_PIXELS_SHA256,
    InstanceEntry,
    NotPreviewedEntry,
    NotPreviewedReason,
    Preview,
    PreviewKind,
    QcPack,
    QcPackError,
    pictured_frames,
)
from pymedphys._dicom.deidentify.reasons import (
    HeldVisualFeatures,
    VisualFeaturesReason,
)

from . import _synthetic_head as head
from . import _synthetic_head_dicom as files
from .test_deidentify_qc_face_verdicts import REFERENCE, _released
from .test_deidentify_qc_previews import _decoded
from .test_deidentify_visual_features_option import KEY, _attest, _policy

# Off centre, with points 3 mm apart along the rows, 5 mm along the
# columns, and 4 mm between planes.
_ORIGIN = (-37.3, 21.9, 113.7)
_RESOLUTION = (3.0, 5.0, 4.0)
# Orientations whose axes lie along the patient's, as qc_segments' tests
# take them, and one turned 30 degrees about the patient's z axis.
_TURN = math.radians(30)
_ORIENTATIONS = {
    "axial": (1.0, 0.0, 0.0, 0.0, 1.0, 0.0),
    "axial flipped": (-1.0, 0.0, 0.0, 0.0, -1.0, 0.0),
    "sagittal": (0.0, 1.0, 0.0, 0.0, 0.0, -1.0),
    "coronal": (1.0, 0.0, 0.0, 0.0, 0.0, -1.0),
    "oblique": (
        math.cos(_TURN),
        math.sin(_TURN),
        0.0,
        -math.sin(_TURN),
        math.cos(_TURN),
        0.0,
    ),
}


def _read(data):
    return pydicom.dcmread(io.BytesIO(data))


def _registration(vectors, position=_ORIGIN, resolution=_RESOLUTION, **arguments):
    return _read(files.registration([(vectors, position, resolution)], **arguments))


def _one(dataset):
    (grid,) = qc_grids.grids_of(dataset)
    return grid


def _point(orientation, index, position=_ORIGIN, resolution=_RESOLUTION):
    """A grid point's patient coordinates, by PS3.3 Equation C.20.3-1."""
    cosines = np.array(orientation)
    row, column = cosines[:3], cosines[3:]
    normal = np.cross(row, column)
    i, j, k = index
    return (
        np.array(position)
        + i * resolution[0] * row
        + j * resolution[1] * column
        + k * resolution[2] * normal
    )


# Reading a grid.


def test_the_vectors_run_along_rows_then_columns_then_planes():
    # Each vector holds its own index, by PS3.3 Section C.20.3.1.3:
    # k * rows * columns + j * columns + i.
    planes, rows, columns = 2, 3, 4
    count = planes * rows * columns
    flat = np.arange(count * 3, dtype=np.float32).reshape(count, 3)
    dataset = _registration(flat.reshape(planes, rows, columns, 3))

    grid = _one(dataset)

    assert grid.dimensions == (columns, rows, planes)
    assert grid.origin == pytest.approx(_ORIGIN)
    assert grid.resolution == pytest.approx(_RESOLUTION)
    for k in range(planes):
        for j in range(rows):
            for i in range(columns):
                index = k * rows * columns + j * columns + i
                assert (grid.vectors[k, j, i] == flat[index]).all()
    assert repr(grid) == "DeformationGrid(dimensions=(4, 3, 2))"


def test_every_grid_of_every_item_is_read_in_order():
    first = np.ones((1, 2, 2, 3), np.float32)
    second = np.full((2, 1, 3, 3), 2.0, np.float32)
    dataset = _read(
        files.registration(
            [(first, _ORIGIN, _RESOLUTION), (second, _ORIGIN, _RESOLUTION)]
        )
    )
    # An item with matrices alone, and an empty grid sequence, hold none.
    dataset.DeformableRegistrationSequence.insert(1, pydicom.Dataset())
    empty = pydicom.Dataset()
    empty.DeformableRegistrationGridSequence = []
    dataset.DeformableRegistrationSequence.append(empty)

    grids = qc_grids.grids_of(dataset)

    assert [grid.dimensions for grid in grids] == [(2, 2, 1), (3, 1, 2)]
    assert qc_grids.grids_of(pydicom.Dataset()) == ()


def _changed(change):
    dataset = _registration(np.zeros((2, 2, 2, 3), np.float32))
    grid = dataset.DeformableRegistrationSequence[0][
        "DeformableRegistrationGridSequence"
    ][0]
    change(dataset, grid)
    return dataset


def _vectors(grid, values):
    grid.VectorGridData = np.asarray(values, "<f4").tobytes()


@pytest.mark.parametrize(
    "change",
    [
        lambda d, g: delattr(g, "ImageOrientationPatient"),
        lambda d, g: delattr(g, "ImagePositionPatient"),
        lambda d, g: delattr(g, "GridDimensions"),
        lambda d, g: delattr(g, "GridResolution"),
        lambda d, g: delattr(g, "VectorGridData"),
        # Direction cosines not of unit length, and not orthogonal.
        lambda d, g: setattr(g, "ImageOrientationPatient", [1, 0, 0, 0, 1.01, 0]),
        lambda d, g: setattr(g, "ImageOrientationPatient", [1, 0, 0, 0.01, 0.99995, 0]),
        lambda d, g: setattr(g, "ImageOrientationPatient", [1, 0, 0, 0, 1]),
        lambda d, g: setattr(g, "ImagePositionPatient", [0, 0, 2e6]),
        lambda d, g: setattr(g, "GridResolution", [1.0, 0.0, 1.0]),
        lambda d, g: setattr(g, "GridResolution", [1.0, -1.0, 1.0]),
        lambda d, g: setattr(g, "GridResolution", [1.0, math.inf, 1.0]),
        lambda d, g: setattr(g, "GridDimensions", [2, 2, 0]),
        # Vector Grid Data of one vector too few, and too many.
        lambda d, g: setattr(g, "VectorGridData", bytes(7 * 12)),
        lambda d, g: setattr(g, "VectorGridData", bytes(9 * 12)),
        # A vector that is infinite, or undefined in part.
        lambda d, g: _vectors(g, [math.inf] + [0.0] * 23),
        lambda d, g: _vectors(g, [math.nan] + [0.0] * 23),
        # Points that span more than a patient along z, or a bore across.
        lambda d, g: setattr(g, "GridResolution", [1.0, 1.0, 2001.0]),
        lambda d, g: setattr(g, "GridResolution", [1001.0, 1.0, 1.0]),
    ],
)
def test_a_grid_that_cannot_be_drawn_is_refused(change):
    assert qc_grids.grids_of(_changed(change)) is None


def test_a_grid_read_in_big_endian_is_refused():
    dataset = _registration(np.zeros((1, 1, 1, 3), np.float32))
    dataset.set_original_encoding(False, False)

    assert qc_grids.grids_of(dataset) is None


def test_a_deformable_registration_sequence_that_cannot_be_read_has_no_grids():
    dataset = pydicom.Dataset()
    dataset[0x00640002] = pydicom.DataElement(0x00640002, "OB", b"\x01\x02")

    assert qc_grids.grids_of(dataset) is None


def test_an_undefined_vector_is_undefined_in_every_component():
    vectors = np.zeros((1, 1, 2, 3), np.float32)
    vectors[0, 0, 1] = np.nan

    grid = _one(_registration(vectors))

    assert np.isnan(grid.vectors[0, 0, 1]).all()


# Placing a grid's points among the voxels.


def _volume(grid, values):
    sampling = qc_grids._Sampling(grid)
    return sampling, sampling.volume(np.asarray(values, np.float32))


@pytest.mark.parametrize("orientation", list(_ORIENTATIONS))
def test_each_grid_point_is_drawn_at_the_voxel_nearest_it(orientation):
    # One point of a grid finer than the voxels holds a value, so only the
    # voxel nearest it can, and no other voxel is nearest any point of
    # value.
    resolution = (0.8, 1.2, 0.6)
    shape = (6, 7, 9)
    values = np.zeros(shape, np.float32)
    values[3, 2, 5] = 1.0
    vectors = np.zeros((*shape, 3), np.float32)
    grid = _one(
        _registration(
            vectors, resolution=resolution, orientation=_ORIENTATIONS[orientation]
        )
    )

    sampling, volume = _volume(grid, values)

    point = _point(_ORIENTATIONS[orientation], (5, 2, 3), resolution=resolution)
    expected = (
        int(np.abs(sampling.zs - point[2]).argmin()),
        int(np.abs(sampling.ys - point[1]).argmin()),
        int(np.abs(sampling.xs - point[0]).argmin()),
    )
    assert list(zip(*np.nonzero(volume > 0))) == [expected]
    # The voxels lie along the patient's axes at whole multiples of their
    # side: x and y ascending, z descending.
    voxel = sampling.voxel
    assert voxel == qc_surfaces.MINIMUM_VOXEL
    for axis, along in enumerate((sampling.xs, sampling.ys, -sampling.zs)):
        assert np.allclose(np.diff(along), voxel), axis
        assert np.allclose(along / voxel, np.rint(along / voxel)), axis


@pytest.mark.parametrize("orientation", list(_ORIENTATIONS))
def test_each_voxel_within_half_a_cell_of_a_coarse_grid_takes_its_nearest_point(
    orientation,
):
    # Points 10 mm apart, coarser than the voxels, each holding its own
    # number, so that each voxel's value names the point it was drawn from.
    resolution = (10.0, 12.0, 14.0)
    shape = (3, 4, 5)
    values = np.arange(1, 1 + math.prod(shape), dtype=np.float32).reshape(shape)
    cosines = _ORIENTATIONS[orientation]
    grid = _one(
        _registration(
            np.zeros((*shape, 3), np.float32),
            resolution=resolution,
            orientation=cosines,
        )
    )

    sampling, volume = _volume(grid, values)

    assert sampling.voxel == pytest.approx(10.0)
    centres = np.stack(
        np.meshgrid(sampling.zs, sampling.ys, sampling.xs, indexing="ij"), axis=-1
    )[..., ::-1]
    cosines = np.array(cosines)
    directions = np.array(
        [cosines[:3], cosines[3:], np.cross(cosines[:3], cosines[3:])]
    )
    # Each voxel's centre in the grid's index coordinates, found apart from
    # the module, as the solution of Equation C.20.3-1.
    relative = centres - np.array(_ORIGIN)
    indices = np.einsum("...a,ia->...i", relative, directions) / np.array(resolution)
    within = np.all(
        (indices > -0.5 + 1e-9) & (indices < np.array(shape[::-1]) - 0.5 - 1e-9),
        axis=-1,
    )
    nearest = np.rint(indices).astype(int)
    for voxel in zip(*np.nonzero(within)):
        i, j, k = nearest[voxel]
        # A point nearest the voxel is also pushed into it, so a voxel may
        # hold a greater value, though never a smaller one.
        assert volume[voxel] >= values[k, j, i], voxel
    outside = ~within & ~np.isnan(volume)
    # Beyond half a cell of the grid, a voxel holds a value only where a
    # point is nearest it.
    assert outside.sum() <= math.prod(shape)
    assert np.isnan(volume[~within]).sum() + outside.sum() == (~within).sum()
    # Every point is drawn.
    drawn = set(volume[~np.isnan(volume)].tolist())
    assert drawn == set(values.ravel().tolist())


def test_points_finer_than_the_voxels_leave_no_gap():
    # A line of points 0.5 mm apart along the rows.
    shape = (1, 1, 60)
    values = np.ones(shape, np.float32)
    grid = _one(
        _registration(np.zeros((*shape, 3), np.float32), resolution=(0.5, 1.0, 1.0))
    )

    sampling, volume = _volume(grid, values)

    on = np.argwhere(volume > 0)
    assert len(set(on[:, 0])) == 1 and len(set(on[:, 1])) == 1
    columns = np.sort(on[:, 2])
    assert (np.diff(columns) == 1).all()
    assert len(columns) * sampling.voxel >= 59 * 0.5


# The quantities.


def test_variation_takes_the_larger_one_sided_difference():
    # A displacement of (3, 4, 0) mm at one point of three, 2 mm apart:
    # a central difference there is 0, but either one-sided difference is
    # 5 mm over 2 mm.
    vectors = np.zeros((1, 1, 3, 3))
    vectors[0, 0, 1] = (3.0, 4.0, 0.0)

    found = np.asarray(qc_grids._variation(vectors, (2.0, 1.0, 1.0)))

    assert found[0, 0] == pytest.approx([2.5, 2.5, 2.5])


def test_variation_sums_the_axes_and_skips_an_undefined_neighbour():
    vectors = np.zeros((2, 2, 1, 3))
    vectors[0, 0, 0] = (1.0, 0.0, 0.0)
    vectors[1, 1, 0] = np.nan

    found = np.asarray(qc_grids._variation(vectors, (1.0, 2.0, 4.0)))

    # At (0, 0): along the rows, 1 mm over 2 mm; between planes, 1 mm over
    # 4 mm; root sum of squares.
    assert found[0, 0, 0] == pytest.approx(math.hypot(0.5, 0.25))
    # At (1, 0): its only row neighbour is the undefined point, so the
    # rows add nothing; between planes, 1 mm over 4 mm.
    assert found[1, 0, 0] == pytest.approx(0.25)
    assert np.isnan(found[1, 1, 0])


def test_a_ladder_is_the_dose_ladder_cut_to_its_highest_levels():
    values = np.array([np.nan, 0.0, 3e-45, 1e-3, 3.0, -2.0])

    levels = qc_grids.ladder_levels(values)

    full = qc_surfaces.dose_levels(3.0, 3e-45)
    assert len(full) > qc_surfaces.MAXIMUM_DOSE_LEVELS
    assert len(levels) == qc_surfaces.MAXIMUM_DOSE_LEVELS
    assert levels[0] == 0.0
    assert levels[1:] == full[-(qc_surfaces.MAXIMUM_DOSE_LEVELS - 1) :]
    assert qc_grids.ladder_levels(np.array([0.0, -1.0, np.nan])) == (0.0,)
    assert qc_grids.ladder_levels(np.array([1.0, 0.5])) == qc_surfaces.dose_levels(
        1.0, 0.5
    )


# The sheets.


def _head_field(cut=False, undefined=False):
    """A registration over the whole analytic head, 4 mm apart, displaced
    by (1, 1.5, 2) mm wherever the head is, and not elsewhere, cut ahead of
    y = -80 where ``cut``, and undefined beyond 115 mm of the head's centre
    where ``undefined``."""
    resolution = (4.0, 4.0, 4.0)
    position = (-100.0, -130.0, -132.0)
    shape = (72, 61, 51)
    points = np.stack(
        np.meshgrid(
            position[2] + resolution[2] * np.arange(shape[0]),
            position[1] + resolution[1] * np.arange(shape[1]),
            position[0] + resolution[0] * np.arange(shape[2]),
            indexing="ij",
        ),
        axis=-1,
    )[..., ::-1]
    inside = head.hounsfield(points) >= -300
    if cut:
        inside &= points[..., 1] > -80
    vectors = np.zeros((*shape, 3), np.float32)
    vectors[inside] = (1.0, 1.5, 2.0)
    if undefined:
        vectors[np.linalg.norm(points, axis=-1) > 115] = np.nan
    return _one(_registration(vectors, position, resolution))


def _ladders(sheet):
    """Each ladder of a sheet between the white rules, from the top."""
    rules = np.flatnonzero((sheet == qc_grids.LADDER_RULE).all(axis=1))
    edges = [-1, *rules, len(sheet)]
    return [
        sheet[start + 1 : end]
        for start, end in zip(edges[:-1], edges[1:])
        if end - start > 1
    ]


@pytest.mark.deid_requirement("MIDI-BP-15")
def test_a_sheet_shows_the_face_that_a_grid_traces():
    whole = qc_grids.grid_sheets(_head_field())
    cut = qc_grids.grid_sheets(_head_field(cut=True))

    assert len(whole) == len(qc_grids.QUANTITIES) == len(GRID_KINDS)
    for sheet in whole:
        assert sheet.dtype == np.uint8 and sheet.ndim == 2
    # The nose shows in each sheet of the whole head, and not of the cut.
    for whole_sheet, cut_sheet in zip(whole, cut):
        assert whole_sheet.shape != cut_sheet.shape or (whole_sheet != cut_sheet).any()
    # The same grid always gives the same PNGs.
    again = qc_grids.grid_sheets(_head_field())
    assert [qc_previews.png(each) for each in again] == [
        qc_previews.png(each) for each in whole
    ]


def test_the_frontal_view_of_a_displaced_head_is_its_outline():
    field = _head_field()
    sampling = qc_grids._Sampling(field)
    displacement = qc_grids.grid_sheets(field)[0]
    # Without an undefined vector, the displacement sheet has one ladder,
    # whose first row, its support, is the head's frontal silhouette.
    (ladder,) = _ladders(displacement)
    # The frontal view is the first tile, as wide as its rays' reach to
    # either side of the voxel at or next to the middle.
    rows, deep, wide = sampling.shape
    middle_y, middle_x = (deep - 1) // 2, (wide - 1) // 2
    reach = math.ceil(
        math.hypot(
            max(middle_y, deep - 1 - middle_y), max(middle_x, wide - 1 - middle_x)
        )
    )
    frontal = ladder[:rows, reach - middle_x : reach - middle_x + wide]
    silhouette = (
        head.hounsfield(
            np.stack(
                np.meshgrid(sampling.zs, sampling.ys, sampling.xs, indexing="ij"),
                axis=-1,
            )[..., ::-1]
        )
        >= -300
    ).any(axis=1)
    # But for a few rays that graze the outline, where the grid's points
    # fall 2 mm from the voxels' centres, along y.
    lit = frontal > 0
    assert (lit & ~silhouette).sum() <= 0.01 * silhouette.sum()
    assert (silhouette & ~lit).sum() <= 0.01 * silhouette.sum()


def test_an_undefined_region_adds_a_ladder_of_where_the_grid_is_defined():
    defined = qc_grids.grid_sheets(_head_field())
    undefined = qc_grids.grid_sheets(_head_field(undefined=True))

    assert len(_ladders(defined[0])) == 1
    assert len(_ladders(undefined[0])) == 2
    # The variation sheet has one ladder, and each component's two, its
    # positive values', then its negative values'.
    assert [len(_ladders(sheet)) for sheet in defined[1:]] == [1, 2, 2, 2]


def test_a_component_s_sign_is_shown_by_its_own_ladder():
    vectors = np.zeros((4, 4, 4, 3), np.float32)
    vectors[1:3, 1:3, 1:3, 0] = 5.0
    vectors[0, 0, 0, 0] = -1.0
    grid = _one(_registration(vectors, resolution=(4.0, 4.0, 4.0)))

    sheets = qc_grids.grid_sheets(grid)

    x, y, z = sheets[2:]
    positive, negative = _ladders(x)
    assert positive.any() and negative.any()
    # Each of y and z is 0 everywhere, so each ladder is its support alone,
    # with nothing in it.
    for sheet in (y, z):
        for ladder in _ladders(sheet):
            assert not ladder.any()


def test_a_sheet_over_its_tallest_is_not_drawn():
    field = _head_field()
    assert qc_grids.grid_sheets(field, tallest=200) is None


def test_values_too_small_for_a_voxel_stay_above_0():
    found = qc_grids._held(np.array([1e-50, 0.0, np.nan]), (0.0,))
    assert found[0] > 0 and found[1] == 0 and np.isnan(found[2])
    assert qc_grids._held(np.array([1e50]), (0.0,)) is None
    assert qc_grids._held(np.array([1e-40]), (0.0, 1e-40)) is None


# The previews.


def test_a_registration_is_previewed_by_each_of_its_grids_sheets():
    first = np.zeros((2, 3, 4, 3), np.float32)
    first[1, 1, 1] = (1.0, -2.0, 3.0)
    second = np.ones((1, 2, 2, 3), np.float32)
    data = files.registration(
        [(first, _ORIGIN, _RESOLUTION), (second, (0.0, 0.0, 0.0), (2.0, 2.0, 2.0))]
    )

    found = qc_previews.previews_of({3: data}, ())

    assert not found.not_previewed
    assert found.grids_shown == {3}
    assert not found.pixels_shown and not found.contours_shown
    assert [(p.kind, p.frames, p.total_frames) for p in found.previews] == [
        (kind, ((3, grid),), 2) for grid in range(2) for kind in GRID_KINDS
    ]
    for preview in found.previews:
        assert _decoded(preview.png).ndim == 2
    # A grid sheet lists grids, not frames of pixel data.
    listed = [(p.kind.value, p.frames) for p in found.previews]
    assert pictured_frames(listed, ()) == {}


@pytest.mark.parametrize("why", ["unreadable", "too tall"])
def test_a_registration_whose_grids_are_not_all_drawn_is_listed(monkeypatch, why):
    first = np.ones((2, 2, 2, 3), np.float32)
    second = np.ones((2, 2, 2, 3), np.float32)
    dataset = _read(
        files.registration(
            [(first, _ORIGIN, _RESOLUTION), (second, _ORIGIN, _RESOLUTION)]
        )
    )
    if why == "unreadable":
        grid = dataset.DeformableRegistrationSequence[1][
            "DeformableRegistrationGridSequence"
        ][0]
        grid.VectorGridData = bytes(12)
    else:
        monkeypatch.setattr(qc_grids, "MAXIMUM_SHEET_PIXELS", 10)

    found = qc_previews.previews_of({0: files.written(dataset)}, ())

    assert found.not_previewed == (
        NotPreviewedEntry(0, NotPreviewedReason.GRIDS_NOT_SHOWN),
    )
    # None of its grids' sheets is kept, the first grid's included.
    assert not found.previews
    assert not found.grids_shown


def test_a_high_risk_registration_is_shown_by_its_grids():
    data = files.registration([(np.ones((1, 2, 2, 3)), _ORIGIN, _RESOLUTION)])

    found = qc_previews.previews_of({0: data}, {0})

    assert not found.not_previewed
    assert found.grids_shown == {0}


def test_a_registration_without_a_grid_has_no_previews():
    dataset = _read(files.registration([(np.ones((1, 1, 1, 3)), _ORIGIN, _RESOLUTION)]))
    del dataset.DeformableRegistrationSequence[0].DeformableRegistrationGridSequence

    found = qc_previews.previews_of({0: files.written(dataset)}, ())

    assert not found.previews and not found.not_previewed
    assert not found.grids_shown


def test_grid_sheets_follow_the_segments_sheets_and_precede_high_risk_instances():
    kinds = list(PreviewKind)
    assert kinds.index(GRID_KINDS[0]) > kinds.index(PreviewKind.SEGMENTATION_SEGMENTS)
    assert [kind.value for kind in GRID_KINDS] == [
        f"registration-grid-{quantity}" for quantity in qc_grids.QUANTITIES
    ]


# The grids' digest.


def _two_grids():
    first = np.arange(2 * 3 * 4 * 3, dtype=np.float32).reshape(2, 3, 4, 3)
    second = np.ones((1, 2, 2, 3), np.float32)
    return _read(
        files.registration(
            [(first, _ORIGIN, _RESOLUTION), (second, (0.0, 0.0, 0.0), (2.0, 2.0, 2.0))]
        )
    )


def _second_grid(dataset):
    return dataset.DeformableRegistrationSequence[1].DeformableRegistrationGridSequence[
        0
    ]


@pytest.mark.parametrize(
    "change",
    [
        lambda d: setattr(
            _second_grid(d), "ImageOrientationPatient", [0, 1, 0, 1, 0, 0]
        ),
        lambda d: setattr(_second_grid(d), "ImagePositionPatient", [0.0, 0.0, 0.5]),
        lambda d: setattr(_second_grid(d), "GridDimensions", [2, 1, 2]),
        lambda d: setattr(_second_grid(d), "GridResolution", [2.0, 2.0, 2.5]),
        lambda d: setattr(
            _second_grid(d),
            "VectorGridData",
            _second_grid(d).VectorGridData[:-1] + b"\x01",
        ),
        lambda d: setattr(
            _second_grid(d), "VectorGridData", _second_grid(d).VectorGridData[:-12]
        ),
        lambda d: _second_grid(d).pop(0x00640009),
        # Or in the other order.
        lambda d: d.DeformableRegistrationSequence.reverse(),
    ],
)
def test_the_grids_digest_covers_how_each_is_placed_and_displaced(change):
    dataset = _two_grids()
    before = grid_data_sha256(dataset)

    change(dataset)

    assert grid_data_sha256(dataset) != before


def test_the_grids_digest_does_not_follow_the_frames_they_register():
    dataset = _two_grids()
    before = grid_data_sha256(dataset)

    dataset.FrameOfReferenceUID = files.ROOT + ".77"
    dataset.DeformableRegistrationSequence[0].SourceFrameOfReferenceUID = (
        files.ROOT + ".78"
    )

    assert grid_data_sha256(dataset) == before


def test_no_grids_have_one_digest():
    dataset = _two_grids()
    assert NO_GRIDS == bytes.fromhex(NO_GRIDS_SHA256)
    assert NO_GRIDS == hashlib.sha256(bytes(8)).digest()
    assert grid_data_sha256(pydicom.Dataset()) == NO_GRIDS
    for item in dataset.DeformableRegistrationSequence:
        item.DeformableRegistrationGridSequence = []
    assert grid_data_sha256(dataset) == NO_GRIDS
    del dataset.DeformableRegistrationSequence
    assert grid_data_sha256(dataset) == NO_GRIDS


@pytest.mark.parametrize(
    "change",
    [
        lambda d: _second_grid(d).__setitem__(
            0x00200032,
            pydicom.dataelem.RawDataElement(
                pydicom.tag.Tag(0x00200032), "DS", 5, b"x\\y\\z", 0, False, True
            ),
        ),
        lambda d: d.__setitem__(
            0x00640002, pydicom.DataElement(0x00640002, "OB", b"\x01\x02")
        ),
    ],
)
def test_grids_that_cannot_be_read_have_no_digest(change):
    dataset = _two_grids()
    change(dataset)

    with pytest.raises(ValueError, match="cannot be read") as raised:
        grid_data_sha256(dataset)
    assert raised.value.__cause__ is None


# The frames a registration names.


def test_a_registration_names_its_own_frame_and_each_source_frame():
    vectors = np.zeros((1, 1, 1, 3), np.float32)
    data = files.registration(
        [(vectors, _ORIGIN, _RESOLUTION), (vectors, _ORIGIN, _RESOLUTION)],
        frame=files.ROOT + ".71",
        sources=(files.ROOT + ".72 ", files.ROOT + ".71"),
    )

    assert registration_frames(_read(data)) == {files.ROOT + ".71", files.ROOT + ".72"}


@pytest.mark.parametrize(
    "change",
    [
        lambda d: delattr(d, "FrameOfReferenceUID"),
        lambda d: setattr(d, "FrameOfReferenceUID", ""),
        lambda d: delattr(
            d.DeformableRegistrationSequence[0], "SourceFrameOfReferenceUID"
        ),
        lambda d: setattr(
            d.DeformableRegistrationSequence[0], "SourceFrameOfReferenceUID", ""
        ),
        lambda d: d.__setitem__(
            0x00640002, pydicom.DataElement(0x00640002, "OB", b"\x01\x02")
        ),
    ],
)
def test_a_registration_whose_frames_cannot_all_be_read_may_be_in_any(change):
    dataset = _registration(np.zeros((1, 1, 1, 3), np.float32))
    change(dataset)

    assert registration_frames(dataset) is None


# The pack and its reader.


def _grid_sheets(position, grids=1, kinds=GRID_KINDS, number=1):
    return tuple(
        Preview(
            f"P-{number + index:04d}.png",
            kind,
            ((position, grid),),
            grids,
            qc_previews.png(np.zeros((2, 2), np.uint8)),
        )
        for index, (grid, kind) in enumerate(
            (grid, kind) for grid in range(grids) for kind in kinds
        )
    )


def _gridded(position, digest="3f" * 32):
    entry = _released(position)
    return InstanceEntry(
        entry.position,
        entry.source,
        entry.disposition,
        output=entry.output,
        source_sha256=entry.source_sha256,
        grid_sha256=digest,
    )


def test_a_pack_records_grids_digest_only_where_a_sheet_of_each_kind_shows_each():
    QcPack(REFERENCE, (_gridded(0),), previews=_grid_sheets(0))
    QcPack(REFERENCE, (_gridded(0),), previews=_grid_sheets(0, grids=2))
    QcPack(REFERENCE, (_gridded(0, NO_GRIDS_SHA256),))
    with pytest.raises(QcPackError, match="a sheet of each kind"):
        QcPack(REFERENCE, (_gridded(0),))
    with pytest.raises(QcPackError, match="a sheet of each kind"):
        QcPack(
            REFERENCE, (_gridded(0),), previews=_grid_sheets(0, kinds=GRID_KINDS[:-1])
        )
    with pytest.raises(QcPackError, match="a sheet of each kind"):
        QcPack(REFERENCE, (_gridded(0), _released(1)), previews=_grid_sheets(1))
    # Each of two grids, by every kind.
    with pytest.raises(QcPackError, match="a sheet of each kind"):
        QcPack(
            REFERENCE,
            (_gridded(0),),
            previews=tuple(p for p in _grid_sheets(0, grids=2) if p.frames[0][1] == 0),
        )


def test_a_grid_sheet_shows_one_grid_of_its_instance_once():
    one = _grid_sheets(0)
    with pytest.raises(QcPackError, match="one grid of one instance"):
        QcPack(
            REFERENCE,
            (_gridded(0),),
            previews=(
                Preview(one[0].name, one[0].kind, ((0, 0), (0, 1)), 2, one[0].png),
                *one[1:],
            ),
        )
    with pytest.raises(QcPackError, match="once for each kind"):
        QcPack(REFERENCE, (_gridded(0),), previews=(*one, *_grid_sheets(0, number=6)))
    with pytest.raises(QcPackError, match="once for each kind"):
        QcPack(
            REFERENCE,
            (_gridded(0),),
            previews=(
                Preview(one[0].name, one[0].kind, ((0, 1),), 1, one[0].png),
                *one[1:],
            ),
        )
    with pytest.raises(QcPackError, match="one count of grids"):
        QcPack(
            REFERENCE,
            (_gridded(0),),
            previews=(
                Preview(one[0].name, one[0].kind, ((0, 0),), 2, one[0].png),
                *one[1:],
            ),
        )


def test_a_pack_lists_grids_not_shown_without_a_sheet_or_a_digest():
    unshown = (NotPreviewedEntry(0, NotPreviewedReason.GRIDS_NOT_SHOWN),)
    QcPack(REFERENCE, (_gridded(0, None),), not_previewed=unshown)
    with pytest.raises(QcPackError, match="neither a grid sheet"):
        QcPack(
            REFERENCE,
            (_gridded(0, None),),
            previews=_grid_sheets(0),
            not_previewed=unshown,
        )
    with pytest.raises(QcPackError, match="neither a grid sheet"):
        QcPack(REFERENCE, (_gridded(0, NO_GRIDS_SHA256),), not_previewed=unshown)


def _document(grid_sha256="3f" * 32):
    return {
        "instances": [
            {
                "position": 0,
                "source_sha256": "0f" * 32,
                "pixel_sha256": None,
                "contour_sha256": None,
                "grid_sha256": grid_sha256,
                "reasons": [],
            }
        ],
        "series": [{"positions": [0]}],
        "previews": [],
        "not_previewed": [],
    }


def test_the_reader_takes_a_grids_digest_only_where_every_grid_sheet_shows_them():
    document = _document()
    with pytest.raises(QcPackError, match="not of its format"):
        face_review._series_files(json.dumps(document).encode("ascii"))
    document["previews"] = [
        {"kind": kind.value, "frames": [{"position": 0, "frame": 0}], "total_frames": 1}
        for kind in GRID_KINDS[:-1]
    ]
    with pytest.raises(QcPackError, match="not of its format"):
        face_review._series_files(json.dumps(document).encode("ascii"))
    # Nor where the sheets give no count of grids.
    document["previews"].append(
        {"kind": GRID_KINDS[-1].value, "frames": [{"position": 0, "frame": 0}]}
    )
    with pytest.raises(QcPackError, match="not of its format"):
        face_review._series_files(json.dumps(document).encode("ascii"))
    document["previews"][-1]["total_frames"] = 1
    (entry,) = face_review._series_files(json.dumps(document).encode("ascii"))[0]
    assert entry[6] == bytes.fromhex("3f" * 32) and not entry[3]
    # The digest of none needs no sheet.
    (entry,) = face_review._series_files(
        json.dumps(_document(NO_GRIDS_SHA256)).encode("ascii")
    )[0]
    assert entry[6] == NO_GRIDS


def test_the_reader_judges_no_file_by_grids_it_lists_as_not_shown():
    document = _document(None)
    document["not_previewed"] = [{"position": 0, "reason": "grids-not-shown"}]

    (entry,) = face_review._series_files(json.dumps(document).encode("ascii"))[0]

    assert entry[6] is None and entry[3]


# A verdict on a registration.

_PIXELS = bytes.fromhex(NO_PIXELS_SHA256)
_CONTOURS = bytes.fromhex(NO_CONTOURS_SHA256)


def _review(grids):
    source = hashlib.sha256(b"source").digest()
    return source, FaceReview(
        REFERENCE,
        frozenset({source}),
        frozenset(),
        absent_pixels=frozenset({(source, _PIXELS)}),
        absent_contours=frozenset({(source, _CONTOURS)}),
        absent_grids=grids(source),
    )


def test_a_verdict_covers_only_the_grids_that_the_pack_showed():
    shown = hashlib.sha256(b"shown").digest()
    source, review = _review(lambda source: frozenset({(source, shown)}))
    pixels, contours = _PIXELS, _CONTOURS

    assert review.hold_reason(source, pixels, contours, grids=shown) is None
    assert review.hold_reason(source, pixels, contours) is None
    other = VisualFeaturesReason.OTHER_GRIDS
    assert review.hold_reason(source, pixels, contours, grids=bytes(32)) is other
    assert review.hold_reason(source, pixels, contours, grids=None) is other
    # A review whose pack showed none of its grids covers only a file
    # without any.
    source, review = _review(lambda source: frozenset())
    assert review.hold_reason(source, pixels, contours, grids=shown) is other
    assert review.hold_reason(source, pixels, contours, grids=NO_GRIDS) is None


def test_a_review_s_grids_are_digests_of_files_marked_absent():
    source = hashlib.sha256(b"source").digest()
    with pytest.raises(QcPackError, match="contours, and grids"):
        FaceReview(
            REFERENCE,
            frozenset(),
            frozenset({source}),
            absent_grids=frozenset({(source, NO_GRIDS)}),
        )
    with pytest.raises(QcPackError, match="contours, and grids"):
        FaceReview(
            REFERENCE,
            frozenset({source}),
            frozenset(),
            absent_grids=frozenset({(source, b"short")}),
        )


def test_the_written_grids_digest_is_left_out_where_they_are_not_shown():
    data = files.registration([(np.ones((1, 2, 2, 3)), _ORIGIN, _RESOLUTION)])
    digests = run_qc._written_sha256

    shown = digests(data, False, False, True)
    assert shown["grid_sha256"] == grid_data_sha256(_read(data)).hex()
    assert shown["grid_sha256"] != NO_GRIDS_SHA256
    assert digests(data, False, False, False) == {**shown, "grid_sha256": None}


def _verdict_run(registration, changed=None):
    """Run a deformable registration alone under ``basic``, attest its series
    absent, and run it again, or ``changed`` in its place, under the option;
    return the first pack and the second run's outcome."""
    directory = Path(tempfile.mkdtemp(prefix="g"))
    try:
        (directory / "in").mkdir()
        (directory / "in" / "registration.dcm").write_bytes(registration)
        first = run.run(
            run.discover(directory / "in"),
            directory / "r1",
            InstanceTransform(compose_policy("basic"), KEY, unvalidated_policy=True),
            ReleaseGate(),
            qc_destination=directory / "qc1",
        )
        pack = json.loads(first.qc_pack.read_text("utf-8"))
        _attest(first.qc_pack.parent, {pack["series"][0]["positions"][0]: Face.ABSENT})
        if changed is not None:
            (directory / "in" / "registration.dcm").write_bytes(changed)
        transform = InstanceTransform(
            _policy(),
            KEY,
            face_review=read_face_review(first.qc_pack.parent),
            unvalidated_policy=True,
        )
        second = run.run(
            run.discover(directory / "in"),
            directory / "r2",
            transform,
            ReleaseGate(),
            qc_destination=directory / "qc2",
            reporter=transform.reporter,
        )
        return pack, second.outcomes[0], directory
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def _field():
    vectors = np.zeros((3, 4, 5, 3), np.float32)
    vectors[1, 1:3, 1:4] = (0.5, -1.0, 2.0)
    return vectors


@pytest.mark.deid_requirement("PS3.15-E.3.2-01", "PS3.15-E.3.2-02")
def test_a_verdict_releases_a_registration_whose_grids_were_shown():
    pack, outcome, _ = _verdict_run(
        files.registration([(_field(), _ORIGIN, _RESOLUTION)])
    )

    assert [p["kind"] for p in pack["previews"]] == [k.value for k in GRID_KINDS]
    (entry,) = pack["instances"]
    assert entry["grid_sha256"] not in (None, NO_GRIDS_SHA256)
    assert outcome.status.value == "released"
    assert not any(isinstance(r, HeldVisualFeatures) for r in outcome.reasons)


def test_a_verdict_does_not_release_a_registration_whose_grids_were_not_shown(
    monkeypatch,
):
    monkeypatch.setattr(qc_grids, "MAXIMUM_SHEET_PIXELS", 10)

    pack, outcome, _ = _verdict_run(
        files.registration([(_field(), _ORIGIN, _RESOLUTION)])
    )

    assert pack["previews"] == []
    assert pack["not_previewed"] == [{"position": 0, "reason": "grids-not-shown"}]
    assert pack["instances"][0]["grid_sha256"] is None
    # Its verdict was on none of its grids, so it gives none.
    assert HeldVisualFeatures(VisualFeaturesReason.NO_FACE_VERDICT) in outcome.reasons
    assert outcome.status.value != "released"


def test_a_verdict_does_not_release_grids_other_than_those_the_pack_showed(
    monkeypatch,
):
    # The run writes grids other than the reviewed run's, as a later
    # version might, of the same file.
    original = face_review.grid_data_sha256
    monkeypatch.setattr(
        "pymedphys._dicom.deidentify.instance_transform.grid_data_sha256",
        lambda dataset: hashlib.sha256(original(dataset)).digest(),
    )

    _, outcome, _ = _verdict_run(files.registration([(_field(), _ORIGIN, _RESOLUTION)]))

    assert HeldVisualFeatures(VisualFeaturesReason.OTHER_GRIDS) in outcome.reasons
    assert outcome.status.value != "released"
