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
"""Tests of the QC pack's renders of RT Structure Set contours.

Every name, UID, and contour here is invented.
"""

import json
import shutil
import tempfile
from pathlib import Path

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import (
    face_review,
    qc_contours,
    qc_previews,
    run,
    run_qc,
)
from pymedphys._dicom.deidentify.face_review import (
    contour_data_sha256,
    read_face_review,
)
from pymedphys._dicom.deidentify.instance_transform import (
    InstanceTransform,
    ReleaseGate,
)
from pymedphys._dicom.deidentify.policy import compose_policy
from pymedphys._dicom.deidentify.qc_attestation import Face
from pymedphys._dicom.deidentify.qc_pack import (
    NO_CONTOURS_SHA256,
    InstanceEntry,
    NotPreviewedEntry,
    NotPreviewedReason,
    Preview,
    PreviewKind,
    QcPack,
    QcPackError,
)
from pymedphys._dicom.deidentify.reasons import (
    HeldVisualFeatures,
    VisualFeaturesReason,
)

from . import _synthetic_head as head
from . import _synthetic_head_dicom as files
from .test_deidentify_qc_face_verdicts import REFERENCE, _released
from .test_deidentify_visual_features_option import KEY, _attest, _policy

_OTHER_SERIES = files.ROOT + ".6"
_MAGENTA = (255, 0, 255)


def _structure_set(rois, *, frame=files.FRAME, series=None, frames=None):
    """An RT Structure Set with an ROI for each list of contours, each as its
    Contour Geometric Type and its points, x, y, and z in rows, referencing
    the image series ``series``, with each ROI in ``frame`` or, where given,
    its own of ``frames``."""
    dataset = pydicom.dcmread(
        pydicom.filebase.DicomBytesIO(
            files.structure_set([("ORGAN", files.square((0, 0, 0)))] * len(rois))
        )
    )
    referenced = dataset.ReferencedFrameOfReferenceSequence[0]
    referenced.FrameOfReferenceUID = frame
    if series is not None:
        study = pydicom.Dataset()
        study.ReferencedSOPClassUID = "1.2.840.10008.3.1.2.3.1"
        study.ReferencedSOPInstanceUID = files.STUDY
        image_series = pydicom.Dataset()
        image_series.SeriesInstanceUID = series
        study.RTReferencedSeriesSequence = [image_series]
        referenced.RTReferencedStudySequence = [study]
    for roi, own in zip(dataset.StructureSetROISequence, frames or [frame] * len(rois)):
        roi.ReferencedFrameOfReferenceUID = own
    for item, contours in zip(dataset.ROIContourSequence, rois):
        item.ContourSequence = []
        for kind, points in contours:
            contour = pydicom.Dataset()
            contour.ContourGeometricType = kind
            contour.NumberOfContourPoints = len(points)
            contour.ContourData = [files._ds(v) for v in np.ravel(points)]
            item.ContourSequence.append(contour)
    return files.written(dataset)


def _read(data):
    return pydicom.dcmread(pydicom.filebase.DicomBytesIO(data))


def _closed(points):
    return ("CLOSED_PLANAR", points)


# A head of an ellipsoid's sections every 3 mm, with a nose ahead of it
# between 25 mm below and 15 mm above its centre, and the same head with
# everything ahead of y = -60 mm cut away between 40 mm below and above.
_HEIGHTS = np.arange(-99.0, 100.0, 3.0)


def _section(z, cut=False):
    angles = np.linspace(0, 2 * np.pi, 120, endpoint=False)
    scale = np.sqrt(max(0.0, 1 - (z / 110.0) ** 2))
    x, y = 75 * scale * np.cos(angles), 95 * scale * np.sin(angles)
    if -25 < z < 15:
        nose = 25 * np.exp(-(((angles - 1.5 * np.pi) / 0.18) ** 2))
        y = y - nose * (1 - abs(z + 5) / 20) * (y < 0)
    if cut and -40 <= z <= 40:
        y = np.maximum(y, -60.0)
    return np.column_stack([x, y, np.full(len(x), z)])


def _head(cut=False):
    return qc_contours.contours_of(
        _read(_structure_set([[_closed(_section(z, cut)) for z in _HEIGHTS]]))
    )


# Which contours a sheet can show.


def test_closed_open_and_point_contours_are_read_with_their_references():
    ring = files.circle((0.0, 0.0, 10.0), 20.0)
    line = np.array([[0.0, 0.0, 0.0], [10.0, 0.0, 5.0], [10.0, 10.0, 10.0]])
    found = qc_contours.contours_of(
        _read(
            _structure_set(
                [
                    [_closed(ring), ("CLOSEDPLANAR_XOR", ring)],
                    [("OPEN_PLANAR", line[:2]), ("OPEN_NONPLANAR", line)],
                    [("POINT", np.array([[1.0, 2.0, 3.0]])), _closed(ring[:2])],
                ],
                series=_OTHER_SERIES,
            )
        )
    )
    assert found is not None
    assert [len(roi.closed) for roi in found.rois] == [2, 0, 0]
    assert [len(roi.lines) for roi in found.rois] == [0, 2, 0]
    # A closed contour of fewer than three points bounds nothing, so its
    # points are drawn as marks.
    assert [len(roi.points) for roi in found.rois] == [0, 0, 3]
    assert found.frames == (files.FRAME,)
    assert found.series == {_OTHER_SERIES}
    assert repr(found) == "Contours(rois=3)"
    assert repr(found.rois[0]) == "RoiContours()"


def _sagittal():
    angles = np.linspace(0, 2 * np.pi, 24, endpoint=False)
    return np.column_stack([np.zeros(24), 30 * np.cos(angles), 40 * np.sin(angles)])


@pytest.mark.parametrize(
    "contour",
    [
        _closed(_sagittal()),
        # Tilted by more than COPLANAR across its width.
        _closed(
            files.circle((0.0, 0.0, 0.0), 20.0) * [1, 1, 0]
            + [0, 0, 0.4] * np.r_[np.zeros(12), np.ones(12)][:, np.newaxis]
        ),
        ("SURFACE", files.circle((0.0, 0.0, 0.0), 20.0)),
        ("", files.circle((0.0, 0.0, 0.0), 20.0)),
        _closed(np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [np.nan, 1.0, 0.0]])),
        _closed(np.array([[0.0, 0.0, 0.0], [2e6, 0.0, 0.0], [0.0, 1.0, 0.0]])),
    ],
    ids=["sagittal", "tilted", "unknown-type", "no-type", "not-finite", "too-far"],
)
def test_a_structure_set_with_a_contour_that_a_sheet_does_not_draw_is_not_shown(
    contour,
):
    data = _structure_set([[_closed(files.circle((0, 0, 0), 9.0))], [contour]])
    assert qc_contours.contours_of(_read(data)) is None
    assert qc_contours.has_contours(_read(data))


@pytest.mark.parametrize(
    "keyword, value",
    [
        ("ContourOffsetVector", [0.0, 0.0, 1.0]),
        ("ContourSlabThickness", 2.0),
        ("ContourData", [0.0, 1.0]),
        ("ContourData", None),
    ],
)
def test_a_contour_placed_elsewhere_given_depth_or_unreadable_is_not_drawn(
    keyword, value
):
    dataset = _read(_structure_set([[_closed(files.circle((0, 0, 0), 9.0))]]))
    setattr(dataset.ROIContourSequence[0].ContourSequence[0], keyword, value)
    assert qc_contours.contours_of(dataset) is None


def test_a_structure_set_without_a_contour_has_none_to_show():
    dataset = _read(_structure_set([[]]))
    del dataset.ROIContourSequence[0].ContourSequence
    assert not qc_contours.has_contours(dataset)
    found = qc_contours.contours_of(dataset)
    assert found is not None and found.empty
    assert not qc_contours.has_contours(pydicom.Dataset())


def test_each_roi_takes_its_frame_or_else_the_structure_set_s_only_one():
    other = files.ROOT + ".9"
    ring = [_closed(files.circle((0, 0, 0), 9.0))]
    dataset = _read(_structure_set([ring, ring, ring], frames=[other, "", files.FRAME]))
    found = qc_contours.contours_of(dataset)
    assert [roi.frame for roi in found.rois] == [other, files.FRAME, files.FRAME]
    assert found.frames == (other, files.FRAME)


def test_contours_of_a_frame_that_span_farther_than_a_patient_are_not_shown():
    near = [_closed(files.circle((0, 0, 0), 9.0))]
    far = [_closed(files.circle((qc_contours.LONGEST, 0, 0), 9.0))]
    assert qc_contours.contours_of(_read(_structure_set([near, far]))) is None
    # In frames of their own, each spans little.
    apart = _structure_set([near, far], frames=[files.FRAME, files.ROOT + ".9"])
    assert qc_contours.contours_of(_read(apart)) is not None


# What a sheet draws.


def _grid(low, high, voxel=1.0):
    return qc_contours._Grid(
        np.arange(high[2], low[2] - 1e-9, -voxel),
        np.arange(low[1], high[1] + 1e-9, voxel),
        np.arange(low[0], high[0] + 1e-9, voxel),
    )


def _roi(*contours):
    found = qc_contours.contours_of(_read(_structure_set([list(contours)])))
    return found.rois[0]


def _mask(grid, *rois):
    planes = [qc_contours._planes(roi) for roi in rois]
    return qc_contours._mask(rois, grid, planes)


def test_a_contour_within_another_of_its_roi_is_a_hole_whatever_its_type():
    grid = _grid((-15, -15, 0), (15, 15, 6), 1.0)
    for kind in ("CLOSED_PLANAR", "CLOSEDPLANAR_XOR"):
        rings = [(kind, files.square((0.0, 0.0, z), 10.0)) for z in (0.0, 3.0, 6.0)] + [
            (kind, files.square((0.0, 0.0, z), 4.0)) for z in (0.0, 3.0, 6.0)
        ]
        inside = _mask(grid, _roi(*rings))
        middle = len(grid.ys) // 2
        assert inside[:, middle, middle].sum() == 0
        assert inside[:, middle, middle + 7].all()


def test_the_planes_of_one_roi_never_empty_the_slices_of_another():
    grid = _grid((-15, -15, 0), (15, 15, 30), 1.0)
    every_third = _roi(
        *[_closed(files.square((0, 0, z), 10.0)) for z in range(0, 31, 3)]
    )
    offset = _roi(
        *[_closed(files.square((0, 0, z + 1.0), 2.0)) for z in range(0, 28, 3)]
    )
    alone = _mask(grid, every_third)
    assert alone[:, 15, 22].all()
    assert (_mask(grid, every_third, offset) == alone).all()


def test_a_gap_of_more_than_twice_the_planes_spacing_is_left_empty():
    grid = _grid((-15, -15, 0), (15, 15, 60), 1.0)
    planes = [0, 3, 6, 9, 51, 54, 57, 60]
    inside = _mask(
        grid, _roi(*[_closed(files.square((0, 0, z), 10.0)) for z in planes])
    )
    filled = inside[:, 15, 15][::-1]  # from inferior up
    assert filled[:11].all() and filled[50:].all()
    assert not filled[11:50].any()


def test_points_and_open_contours_are_drawn_as_marks():
    grid = _grid((-15, -15, 0), (15, 15, 10), 1.0)
    line = np.array([[-10.0, 0.0, 5.0], [10.0, 0.0, 5.0]])
    inside = _mask(
        grid,
        _roi(("POINT", np.array([[3.0, -4.0, 2.0]])), ("OPEN_PLANAR", line)),
    )
    assert inside[8, 11, 18]
    assert inside[5, 15, 5:26].all()
    assert inside.sum() == 1 + 21


def test_an_roi_alone_is_sampled_finely_and_as_if_it_were_alone():
    # 20 mm across in at most ROI_VOXELS voxels, but none under 0.5 mm.
    assert qc_contours._roi_voxel(20.0) == pytest.approx(0.5)
    # A large ROI is sampled no coarser than a volume of its extent is.
    assert qc_contours._roi_voxel(300.0) == pytest.approx(2.0)
    assert qc_contours._roi_voxel(600.0) == pytest.approx(
        qc_contours._united_voxel(600.0)
    )
    # A marker far from the outline coarsens the united row, not the
    # outline's own row.
    body = [_closed(files.ellipse((0, 0, z), (150, 120))) for z in range(-90, 91, 3)]
    far = [("POINT", np.array([[0.0, 900.0, 0.0]]))]
    alone = _sheet_rows(
        qc_contours.contour_sheet(
            qc_contours.contours_of(_read(_structure_set([body])))
        )
    )
    both = _sheet_rows(
        qc_contours.contour_sheet(
            qc_contours.contours_of(_read(_structure_set([body, far])))
        )
    )
    # Each row is padded with black to the sheet's width.
    width = min(both[1].shape[1], alone[1].shape[1])
    assert (both[1][:, :width] == alone[1][:, :width]).all()
    assert not both[1][:, width:].any() and not alone[1][:, width:].any()
    assert both[0].shape != alone[0].shape or (both[0] != alone[0]).any()


def _own_mask(roi):
    grid = qc_contours._grid([roi], qc_contours._roi_voxel)
    return grid, qc_contours._mask([roi], grid, [qc_contours._planes(roi)])


@pytest.mark.parametrize("seed", range(20))
def test_every_point_of_an_roi_is_drawn_in_its_own_row(seed):
    generator = np.random.default_rng(seed)
    points = generator.uniform(-75, 75, (generator.integers(2, 5), 3))
    _, inside = _own_mask(_roi(*[("POINT", point[np.newaxis]) for point in points]))
    assert inside.sum() == len(points)


def test_the_lowest_of_many_planes_and_an_open_contour_s_lower_end_are_drawn():
    rings = _roi(*[_closed(files.circle((0, 0, 2.5 * k), 30.0)) for k in range(104)])
    grid, _ = _own_mask(rings)
    planes = qc_contours._planes(rings)
    covered = qc_contours._covering(planes, grid.zs, grid.voxel)
    assert set(covered[covered >= 0]) == set(range(len(planes)))
    line = np.array([[0.0, 0.0, 0.0], [10.0, 0.0, 37.3]])
    grid, inside = _own_mask(_roi(("OPEN_NONPLANAR", line)))
    assert inside[-1].any() and grid.zs[-1] <= 0.0


@pytest.mark.parametrize(
    "ring",
    [
        np.array(
            [[0.0, 0.0, 0.0], [40.0, 0.0, 0.0], [0.0, 0.0, 0.0], [40.0, 0.0, 0.0]]
        ),
        np.column_stack([np.linspace(-30, 30, 24), np.zeros(24), np.zeros(24)]),
        # A square traversed twice, which the even-odd rule leaves empty.
        np.vstack([files.square((0.0, 0.0, 0.0), 15.0)] * 2),
    ],
    ids=["out-and-back", "collinear", "doubled"],
)
def test_a_closed_contour_that_bounds_no_area_is_drawn_as_its_line(ring):
    grid, inside = _own_mask(_roi(_closed(ring)))
    # Every voxel along its length, at most a voxel apart.
    length = float(np.ptp(ring[:, 0]))
    assert inside.sum() >= length / grid.voxel


def test_marks_are_taken_along_a_segment_a_whole_number_of_steps_long():
    # Sides of 3, 4, and 5 mm, at 0.25 mm: 12, 16, and 20 steps, and the
    # point that closes the ring.
    triangle = np.array([[0.0, 0.0], [3.0, 0.0], [3.0, 4.0]])
    marks = qc_contours.RoiContours(closed=((2.0, triangle),)).marks(0.25)
    assert marks.shape == (12 + 16 + 20 + 1, 3)
    assert (marks[:, 2] == 2.0).all()
    for vertex in triangle:
        assert (marks[:, :2] == vertex).all(axis=1).any()
    ordered = np.vstack([marks[1:], marks[:1]])
    assert np.linalg.norm(np.diff(ordered, axis=0), axis=1).max() <= 0.25 + 1e-12


def _sheet_rows(sheet):
    """Each row of a sheet between the grey gutters, from the top."""
    gutters = np.flatnonzero((sheet == (128, 128, 128)).all(axis=(1, 2)))
    edges = [-1, *gutters, len(sheet)]
    return [
        sheet[start + 1 : end]
        for start, end in zip(edges[:-1], edges[1:])
        if end - start > 1
    ]


def test_a_sheet_shows_the_face_that_the_written_contours_trace():
    whole, cut = _head(), _head(cut=True)
    sheet = qc_contours.contour_sheet(whole)
    assert sheet.dtype == np.uint8 and sheet.shape[2] == 3
    united, roi = _sheet_rows(sheet)
    cut_united, cut_roi = _sheet_rows(qc_contours.contour_sheet(cut))
    # The nose shows in the renders of the whole head, and not of the cut,
    # which spans less.
    for whole_row, cut_row in ((united, cut_united), (roi, cut_roi)):
        assert whole_row.shape != cut_row.shape or (whole_row != cut_row).any()
    # The same contours always give the same PNG.
    again = qc_contours.contour_sheet(_head())
    assert qc_previews.png(again) == qc_previews.png(sheet)


def test_an_roi_that_another_encloses_has_a_row_of_its_own():
    box = [_closed(files.square((0, 0, z), 60.0)) for z in range(-30, 31, 3)]
    face = [_closed(files.circle((0, -40.0, z), 15.0)) for z in range(-15, 16, 3)]
    alone = qc_contours.contours_of(_read(_structure_set([box])))
    both = qc_contours.contours_of(_read(_structure_set([box, face])))
    (united, _) = _sheet_rows(qc_contours.contour_sheet(alone))
    rows = _sheet_rows(qc_contours.contour_sheet(both))
    # The box hides the face in the united render, which is the same with it
    # or without it, but the face has its own row.
    assert len(rows) == 3
    assert (rows[0] == united).all()
    assert rows[2].any()


# A cavity that an ROI's own contours bound: a box 50 by 64 mm across with,
# in one ROI, a head's sections, a quarter of its size, as contours within it.
_BOX_HEIGHTS = np.arange(-15.0, 16.0, 3.0)


def _box(z):
    return np.array([[-25, -32, z], [25, -32, z], [25, 32, z], [-25, 32, z]], float)


def _cavity(z, cut=False):
    section = _section(4 * z, cut)
    section[:, :2] /= 4
    section[:, 2] = z
    return section


def _hollow(cut=False, keyhole=False):
    return qc_contours.contours_of(_read(_hollow_set(cut, keyhole)))


def _hollow_set(cut=False, keyhole=False):
    """A box with a head-shaped cavity, by XOR contours or by keyhole
    contours that each trace the box and, by a cut, the cavity."""
    rings = []
    for z in _BOX_HEIGHTS:
        box = _box(z)
        if abs(z) > 10:
            rings.append(("CLOSEDPLANAR_XOR", box))
        elif keyhole:
            cavity = _cavity(z, cut)
            # Into the cavity from the box's front edge, around it the other
            # way, and back out.
            start = int(np.argmin(cavity[:, 1]))
            around = np.roll(cavity, -start, axis=0)[::-1]
            around = np.vstack([around[-1:], around[:-1]])
            entry = np.array([[around[0, 0], -32.0, z]])
            rings.append(
                (
                    "CLOSED_PLANAR",
                    np.vstack([entry, box[[0, 3, 2, 1]], entry, around, around[:1]]),
                )
            )
        else:
            rings.extend(
                [("CLOSEDPLANAR_XOR", box), ("CLOSEDPLANAR_XOR", _cavity(z, cut))]
            )
    return _structure_set([rings])


def _solid():
    rings = [("CLOSEDPLANAR_XOR", _box(z)) for z in _BOX_HEIGHTS]
    return qc_contours.contours_of(_read(_structure_set([rings])))


@pytest.mark.parametrize("keyhole", [False, True], ids=["xor", "keyhole"])
def test_a_cavity_that_an_roi_s_own_contours_bound_is_shown(keyhole):
    solid = _sheet_rows(qc_contours.contour_sheet(_solid()))
    hollow = _sheet_rows(qc_contours.contour_sheet(_hollow(keyhole=keyhole)))
    cut = _sheet_rows(qc_contours.contour_sheet(_hollow(cut=True, keyhole=keyhole)))
    # The box's own row hides the cavity, as it would alone.
    assert len(solid) == 2
    assert (hollow[1] == solid[1]).all()
    # A row of the cavity, whole, then a row for each further crossing of
    # the surface, along the views that look along an axis.
    assert len(hollow) > 3 and len(cut) == len(hollow)
    width = hollow[2].shape[1] // 5
    cavity = hollow[2][:, : width - 1]
    assert cavity.any() and (cavity != cut[2][:, : width - 1]).any()
    # The cavity's front shows in the frontal view of a further row, though
    # its own row were not drawn.
    assert any(
        (row[:, : width - 1] != other[:, : width - 1]).any()
        for row, other in zip(hollow[3:], cut[3:])
    )


def test_a_surface_that_an_roi_hides_behind_its_own_is_shown_without_a_cavity():
    # Two pieces of one ROI, one behind the other, enclose nothing between
    # them.
    rings = [
        _closed(files.circle((0, y, z), 8.0)) for y in (-15.0, 15.0) for z in (0, 3)
    ]
    rows = _sheet_rows(
        qc_contours.contour_sheet(
            qc_contours.contours_of(_read(_structure_set([rings])))
        )
    )
    # The united row, its own row, and the three further crossings of the
    # frontal view's rays: out of one piece, into the other, and out.
    assert len(rows) == 2 + 3


def _marked_box(*marks):
    rings = [("CLOSED_PLANAR", _box(z)) for z in _BOX_HEIGHTS]
    return qc_contours.contours_of(_read(_structure_set([rings + list(marks)])))


def _curve(bend):
    x = np.linspace(-12.0, 12.0, 25)
    return np.column_stack([x, bend * np.sin(x / 4), np.zeros_like(x)])


@pytest.mark.parametrize(
    "marks",
    [
        [("OPEN_PLANAR", _curve(4.0)), ("OPEN_PLANAR", _curve(-4.0))],
        [("POINT", np.array([[5.0, -6.0, 3.0]]))],
        # Just inside the box's front edge, where it fills the voxel.
        [("POINT", np.array([[5.0, -31.8, 3.0]]))],
        [_closed(np.vstack([files.square((0.0, 0.0, 0.0), 15.0)] * 2))],
        [_closed(files.square((0.0, 0.0, 0.0), 8.0))] * 2,
    ],
    ids=["open", "point", "edge", "doubled", "twins"],
)
def test_marks_within_their_own_roi_s_region_have_rows_of_their_own(marks):
    solid = _sheet_rows(qc_contours.contour_sheet(_solid()))
    rows = _sheet_rows(qc_contours.contour_sheet(_marked_box(*marks)))
    # The box's region hides the marks, so its rows are those of the box
    # alone, and the marks' rows follow them.
    assert len(solid) == 2 and len(rows) > 2
    assert all((row == other).all() for row, other in zip(rows[:2], solid))
    assert all(row.any() for row in rows[2:])


def test_marks_within_their_own_roi_s_region_are_told_apart():
    one = _sheet_rows(
        qc_contours.contour_sheet(_marked_box(("OPEN_PLANAR", _curve(4.0))))
    )
    other = _sheet_rows(
        qc_contours.contour_sheet(_marked_box(("OPEN_PLANAR", _curve(-4.0))))
    )
    # The box's own rows are the same, and the marks' row is not.
    assert len(one) == len(other) > 2
    assert (one[1] == other[1]).all() and (one[2] != other[2]).any()


def _detoured(detour):
    # The box, its contour at 0 mm also running from its front edge along a
    # detour within it and back.
    rings = [("CLOSED_PLANAR", _box(z)) for z in _BOX_HEIGHTS if z != 0]
    box, entry = _box(0.0), np.array([[detour[0, 0], -32.0, 0.0]])
    path = np.vstack([box[:1], entry, detour, entry, box[1:]])
    return qc_contours.contours_of(
        _read(_structure_set([[*rings, ("CLOSED_PLANAR", path)]]))
    )


def _twice(loop):
    return np.vstack([loop, loop, loop[:1]])


def _spur(bend):
    # Into the box and back the same way, around a bulge 4 mm across.
    spur = np.array([[0.0, -20.0, 0.0], [bend, -10.0, 0.0], [0.0, 0.0, 0.0]])
    bulge = files.square((0.0, 2.0, 0.0), 2.0)
    return np.vstack([spur, bulge, bulge[:1], spur[::-1]])


@pytest.mark.parametrize(
    "detours",
    [
        [
            _twice(files.square((0.0, 0.0, 0.0), 12.0)),
            _twice(files.circle((0.0, 0.0, 0.0), 12.0)),
        ],
        [_spur(0.0), _spur(6.0)],
    ],
    ids=["retraced", "spur"],
)
def test_a_path_that_a_contour_retraces_within_its_region_has_rows_of_its_own(
    detours,
):
    solid = _sheet_rows(qc_contours.contour_sheet(_solid()))
    one, other = (
        _sheet_rows(qc_contours.contour_sheet(_detoured(each))) for each in detours
    )
    assert len(one) > 2 and len(other) > 2
    assert all((row == box).all() for row, box in zip(one[:2], solid))
    assert any(
        row.shape != then.shape or (row != then).any()
        for row, then in zip(one[2:], other[2:])
    )


def _plugged(hole):
    """The box with a hole at 0 mm, and a line across each row of the
    hole's voxels."""
    rings = [("CLOSED_PLANAR", _box(z)) for z in _BOX_HEIGHTS]
    rings.append(("CLOSED_PLANAR", hole))
    (roi,) = qc_contours.contours_of(_read(_structure_set([rings]))).rois
    grid = qc_contours._grid([roi], qc_contours._roi_voxel)
    filled = qc_contours._filled(roi, grid, qc_contours._planes(roi))
    near = (np.abs(grid.zs) <= 1.5)[:, None, None] & (np.abs(grid.xs) < 23)
    empty = ~filled & near & (np.abs(grid.ys) < 30)[:, None]
    lines = []
    for k, j in zip(*np.nonzero(empty.any(axis=2))):
        x = grid.xs[np.flatnonzero(empty[k, j])]
        ends = [[x[0], grid.ys[j], grid.zs[k]], [x[-1], grid.ys[j], grid.zs[k]]]
        lines.append(("OPEN_PLANAR", np.array(ends)))
    return qc_contours.contours_of(_read(_structure_set([rings + lines])))


def _rastered(curve):
    """The box with a curve within it at 0 mm, and a line back and forth
    over it along each row of voxels."""
    rings = [("CLOSED_PLANAR", _box(z)) for z in _BOX_HEIGHTS]
    (roi,) = qc_contours.contours_of(_read(_structure_set([rings]))).rois
    ys = qc_contours._grid([roi], qc_contours._roi_voxel).ys
    ys = ys[np.abs(ys) < 20]
    xs = np.where(np.arange(len(ys)) % 2, 15.0, -15.0)
    passes = np.column_stack([xs, ys, np.zeros_like(ys)])
    raster = np.repeat(passes, 2, axis=0)
    raster[1::2, 0] *= -1
    marks = [("OPEN_PLANAR", curve), ("OPEN_PLANAR", raster)]
    return qc_contours.contours_of(_read(_structure_set([rings + marks])))


@pytest.mark.parametrize(
    "contours",
    [
        lambda: _plugged(files.square((0.0, 0.0, 0.0), 12.0)),
        lambda: _rastered(_curve(4.0)),
    ],
    ids=["plugged", "rastered"],
)
def test_marks_that_hide_one_another_are_not_shown(contours):
    # The marks fill a patch, which would hide a hole's outline or a curve
    # in their own rows too.
    assert qc_contours.contour_sheet(contours()) is None


# A slab 240 by 200 mm across, of voxels near 2 mm, in planes 1 mm apart,
# some of which cover no slice of voxels.
_SLAB_HEIGHTS = np.arange(-10.0, 10.5, 1.0)


def _slab(*extra):
    rings = [
        _closed(
            np.array([[-120, -100, z], [120, -100, z], [120, 100, z], [-120, 100, z]])
        )
        for z in _SLAB_HEIGHTS
    ]
    return qc_contours.contours_of(_read(_structure_set([rings + list(extra)])))


def _slab_plane(covered):
    (roi,) = _slab().rois
    grid = qc_contours._grid([roi], qc_contours._roi_voxel)
    shown = set(qc_contours._covering(qc_contours._planes(roi), grid.zs, grid.voxel))
    return next(z for i, z in enumerate(_SLAB_HEIGHTS) if (i in shown) == covered)


def test_a_slit_or_a_hole_in_a_plane_that_no_slice_shows_has_rows_of_its_own():
    def sheet(*extra):
        return qc_contours.contour_sheet(_slab(*extra))

    def differ(one, other):
        return one.shape != other.shape or (one != other).any()

    z = _slab_plane(covered=True)
    straight = np.array([[-20, -0.9, z], [20, -0.9, z], [20, 0.9, z], [-20, 0.9, z]])
    slanted = straight.copy()
    slanted[[0, 3], 1] -= 10
    slab = sheet()
    # A slit a voxel wide, which its own marks fill.
    assert differ(sheet(_closed(straight)), slab)
    assert differ(sheet(_closed(straight)), sheet(_closed(slanted)))
    z = _slab_plane(covered=False)
    square = sheet(_closed(files.square((0.0, 0.0, z), 12.0)))
    assert differ(square, slab)
    assert differ(square, sheet(_closed(files.circle((0.0, 0.0, z), 12.0))))


def test_ordinary_outlines_hide_no_marks():
    for contours in (_head(), _solid(), _slab()):
        for roi in contours.rois:
            grid = qc_contours._grid([roi], qc_contours._roi_voxel)
            filled = qc_contours._filled(roi, grid, qc_contours._planes(roi))
            assert qc_contours._hidden(roi, grid, filled) is None


def test_marks_outside_their_own_roi_s_region_have_no_rows_of_their_own():
    # Above the box, where no ray meets the box too.
    outside = np.array([[-10.0, 0.0, 20.0], [10.0, 0.0, 20.0]])
    rows = _sheet_rows(qc_contours.contour_sheet(_marked_box(("OPEN_PLANAR", outside))))
    assert len(rows) == 2


def test_each_frame_has_its_own_united_row_and_each_item_its_own_row():
    ring = [_closed(files.circle((0, 0, z), 20.0)) for z in (0.0, 3.0)]
    contours = qc_contours.contours_of(
        _read(
            _structure_set(
                [ring, [], ring, ring],
                frames=[files.FRAME, files.FRAME, files.ROOT + ".9", files.FRAME],
            )
        )
    )
    rows = _sheet_rows(qc_contours.contour_sheet(contours))
    # Two frames' united rows, then a row per item: an item without
    # contours is a black strip.
    assert len(rows) == 2 + 4
    assert not rows[3].any() and rows[3].shape[0] == qc_contours.GUTTER_PIXELS
    # Items that are the same are drawn the same.
    assert (rows[2] == rows[5]).all() and (rows[2] == rows[4]).all()


def test_a_sheet_taller_than_its_tallest_is_not_given():
    ring = [_closed(files.circle((0, 0, z), 20.0)) for z in (0.0, 3.0)]
    far = [("POINT", np.array([[0.0, 900.0, 0.0]]))]
    sets = [
        _structure_set(
            [ring, [], ring, far],
            frames=[files.FRAME, files.FRAME, files.ROOT + ".9", files.FRAME],
        ),
    ]
    generator = np.random.default_rng(0)
    for _ in range(5):
        sets.append(
            _structure_set(
                [
                    [
                        _closed(files.circle((*centre[:2], z), radius))
                        for z in np.arange(centre[2], centre[2] + length, 2.5)
                    ]
                    for centre, radius, length in zip(
                        generator.uniform(-30, 30, (4, 3)),
                        generator.uniform(2, 12, 4),
                        generator.uniform(3, 20, 4),
                    )
                ]
            )
        )
    zs, ys, xs = (
        np.arange(60.0, -61.0, -4.0),
        np.arange(-80.0, 81.0, 4.0),
        np.arange(-70.0, 71.0, 4.0),
    )
    guide = qc_contours.Guide(np.ones((len(zs), len(ys), len(xs)), bool), zs, ys, xs)
    for data in sets:
        contours = qc_contours.contours_of(_read(data))
        for guides in ({}, {files.FRAME: guide}):
            sheet = qc_contours.contour_sheet(contours, guides)
            height = sheet.shape[0]
            fitted = qc_contours.contour_sheet(contours, guides, height)
            assert fitted is not None and (fitted == sheet).all()
            assert qc_contours.contour_sheet(contours, guides, height - 1) is None
            # Without rows of cavities or hidden surfaces, the height is found
            # without drawing the sheet.
            assert qc_contours._least_height(contours, guides) == height
    hollow = _hollow()
    assert (
        qc_contours._least_height(hollow, {})
        < qc_contours.contour_sheet(hollow).shape[0]
    )


def test_a_sheet_is_drawn_only_until_it_is_too_tall(monkeypatch):
    rings = [
        [_closed(files.circle((0, 0, z), radius)) for z in (0.0, 3.0)]
        for radius in (5.0, 6.0, 7.0)
    ]
    contours = qc_contours.contours_of(_read(_structure_set(rings)))
    drawn = []
    rows = qc_contours._roi_rows
    monkeypatch.setattr(
        qc_contours, "_roi_rows", lambda inside: drawn.append(1) or rows(inside)
    )
    assert qc_contours.contour_sheet(contours, tallest=1) is None
    assert not drawn
    # Drawn until it is too tall, where its rows without those of hidden
    # surfaces fit.
    height = qc_contours._least_height(contours, {})
    monkeypatch.setattr(
        qc_contours,
        "_roi_rows",
        lambda inside: drawn.append(1) or rows(inside) * 3,
    )
    assert qc_contours.contour_sheet(contours, tallest=height) is None
    assert len(drawn) < 3


def test_a_sheet_needs_a_contour():
    one = qc_contours.contours_of(_read(_structure_set([[]])))
    with pytest.raises(ValueError, match="needs a contour"):
        qc_contours.contour_sheet(one)


# The pack's previews of a structure set.

_SCAN = head.axial(
    spacing=5.0, thickness=5.0, extent=((-100, 100), (-130, 110), (-30, 110))
)


def _ct(series=files.SERIES, frame=files.FRAME):
    return files.ct_files(_SCAN, series=series, frame=frame)


def _outline(cut=False):
    """The head's outline on each of the scan's slices, cut ahead of y = -80
    where ``cut``."""
    rings = []
    for position in _SCAN.positions:
        z = position[2]
        factor = 1 - ((z - 10.0) / 130.0) ** 2
        if factor <= 0:
            continue
        ring = files.ellipse((0.0, 0.0, z), (75 * factor**0.5, 95 * factor**0.5))
        if cut:
            ring[:, 1] = np.maximum(ring[:, 1], -80.0)
        rings.append(_closed(ring))
    return rings


def test_a_structure_set_is_previewed_with_the_ct_series_that_it_references():
    other, ct = _ct(series=_OTHER_SERIES), _ct()
    written = _structure_set([_outline(cut=True)], series=files.SERIES)
    files_written = {
        **dict(enumerate(other)),
        **{len(other) + i: data for i, data in enumerate(ct)},
    }
    position = len(files_written)
    files_written[position] = written
    found = qc_previews.previews_of(files_written, {position})
    assert found.contours_shown == {position}
    assert not found.not_previewed
    (sheet,) = [
        p for p in found.previews if p.kind is PreviewKind.STRUCTURE_SET_CONTOURS
    ]
    # Drawn with the series that it references, not the other in its frame.
    ct_positions = tuple((len(other) + i, 0) for i in range(len(ct)))
    assert sheet.frames == ((position, 0), *ct_positions)
    assert sheet.total_frames == len(sheet.frames)
    rows = _sheet_rows(_decoded(sheet.png))
    assert len(rows) == 3
    # The outline is drawn in magenta in the CT's row alone.
    assert [(row == _MAGENTA).all(axis=2).any() for row in rows] == [
        False,
        True,
        False,
    ]
    # Contour sheets follow the series' previews.
    kinds = [preview.kind for preview in found.previews]
    assert kinds[-1] is PreviewKind.STRUCTURE_SET_CONTOURS


def test_a_structure_set_without_an_image_series_in_its_frame_has_no_ct_row():
    written = _structure_set([_outline()])
    found = qc_previews.previews_of(
        {0: _ct(frame=files.ROOT + ".9")[0], 1: written}, set()
    )
    (sheet,) = [
        p for p in found.previews if p.kind is PreviewKind.STRUCTURE_SET_CONTOURS
    ]
    assert sheet.frames == ((1, 0),)
    assert len(_sheet_rows(_decoded(sheet.png))) == 2


def test_every_structure_set_with_contours_is_previewed_whatever_its_risk():
    written = _structure_set([[_closed(files.circle((0, 0, 0), 9.0))]])
    found = qc_previews.previews_of({3: written}, set())
    assert [p.kind for p in found.previews] == [PreviewKind.STRUCTURE_SET_CONTOURS]
    assert found.contours_shown == {3}


def test_a_sheet_taller_than_any_shown_is_not_shown(monkeypatch):
    written = _structure_set([[_closed(files.circle((0, 0, 0), 9.0))]] * 3)
    (sheet,) = qc_previews.previews_of({3: written}, {3}).previews
    height = int.from_bytes(sheet.png[20:24], "big")
    monkeypatch.setattr(qc_contours, "MAXIMUM_SHEET_PIXELS", height - 1)
    found = qc_previews.previews_of({3: written}, {3})
    assert not found.previews
    assert found.contours_shown == frozenset()
    assert found.not_previewed == (
        NotPreviewedEntry(3, NotPreviewedReason.CONTOURS_NOT_SHOWN),
    )


def test_a_sheet_too_tall_only_by_the_rows_of_a_cavity_is_not_shown(monkeypatch):
    written = _hollow_set()
    (sheet,) = qc_previews.previews_of({3: written}, {3}).previews
    rows = _sheet_rows(_decoded(sheet.png))
    height = int.from_bytes(sheet.png[20:24], "big")
    monkeypatch.setattr(qc_contours, "MAXIMUM_SHEET_PIXELS", height - 1)
    # Its united row and its own row fit.
    assert rows[0].shape[0] + qc_contours.GUTTER_PIXELS + rows[1].shape[0] < height - 1
    found = qc_previews.previews_of({3: written}, {3})
    assert not found.previews
    assert found.contours_shown == frozenset()
    assert found.not_previewed == (
        NotPreviewedEntry(3, NotPreviewedReason.CONTOURS_NOT_SHOWN),
    )


def test_contours_that_a_sheet_does_not_draw_are_not_shown():
    written = _structure_set([[_closed(_sagittal())]])
    found = qc_previews.previews_of({3: written}, {3})
    assert not found.previews
    assert found.contours_shown == frozenset()
    assert found.not_previewed == (
        NotPreviewedEntry(3, NotPreviewedReason.CONTOURS_NOT_SHOWN),
    )


def test_a_high_risk_structure_set_without_contours_still_has_no_pixel_data():
    dataset = _read(_structure_set([[]]))
    del dataset.ROIContourSequence[0].ContourSequence
    written = files.written(dataset)
    found = qc_previews.previews_of({0: written}, {0})
    assert found.not_previewed == (
        NotPreviewedEntry(0, NotPreviewedReason.NO_PIXEL_DATA),
    )
    # It has no contour to show, so its contours' digest, of none, stands.
    assert found.contours_shown == frozenset()
    assert run_qc._written_sha256(written, False)["contour_sha256"] == (
        NO_CONTOURS_SHA256
    )


def test_the_digest_of_contours_that_are_not_shown_is_left_out():
    written = _structure_set([[_closed(files.circle((0, 0, 0), 9.0))]])
    shown = run_qc._written_sha256(written, True)
    assert shown["contour_sha256"] not in (None, NO_CONTOURS_SHA256)
    assert run_qc._written_sha256(written, False) == {**shown, "contour_sha256": None}


@pytest.mark.parametrize(
    "keyword, value",
    [("ContourOffsetVector", [0.0, 0.0, 1.0]), ("ContourSlabThickness", 2.0)],
)
def test_the_contours_digest_covers_their_offset_and_their_depth(keyword, value):
    dataset = _read(_structure_set([[_closed(files.circle((0, 0, 0), 9.0))]]))
    before = contour_data_sha256(dataset)
    setattr(dataset.ROIContourSequence[0].ContourSequence[0], keyword, value)
    assert contour_data_sha256(dataset) != before


def _decoded(data):
    """A PNG of qc_previews.png as an RGB array."""
    import zlib  # pylint: disable = import-outside-toplevel

    width, height = (
        int.from_bytes(data[16:20], "big"),
        int.from_bytes(data[20:24], "big"),
    )
    start = data.index(b"IDAT") + 4
    length = int.from_bytes(data[start - 8 : start - 4], "big")
    raw = np.frombuffer(zlib.decompress(data[start : start + length]), np.uint8)
    return raw.reshape(height, 1 + width * 3)[:, 1:].reshape(height, width, 3)


# What the pack and its reader accept.


def _sheet(position, number=1):
    return Preview(
        f"P-{number:04d}.png",
        PreviewKind.STRUCTURE_SET_CONTOURS,
        ((position, 0),),
        1,
        qc_previews.png(np.zeros((2, 2), np.uint8)),
    )


def _contoured(position, digest="2f" * 32):
    entry = _released(position)
    return InstanceEntry(
        entry.position,
        entry.source,
        entry.disposition,
        output=entry.output,
        source_sha256=entry.source_sha256,
        contour_sha256=digest,
    )


def test_a_pack_records_contours_digest_only_where_a_sheet_shows_them():
    QcPack(REFERENCE, (_contoured(0),), previews=(_sheet(0),))
    QcPack(REFERENCE, (_contoured(0, NO_CONTOURS_SHA256),))
    with pytest.raises(QcPackError, match="contour sheet that shows them"):
        QcPack(REFERENCE, (_contoured(0), _released(1)), previews=(_sheet(1),))


def test_a_pack_lists_contours_not_shown_without_a_sheet_or_a_digest():
    unshown = (NotPreviewedEntry(0, NotPreviewedReason.CONTOURS_NOT_SHOWN),)
    QcPack(REFERENCE, (_contoured(0, None),), not_previewed=unshown)
    with pytest.raises(QcPackError, match="neither a contour sheet"):
        QcPack(
            REFERENCE,
            (_contoured(0),),
            previews=(_sheet(0),),
            not_previewed=unshown,
        )
    with pytest.raises(QcPackError, match="neither a contour sheet"):
        QcPack(REFERENCE, (_contoured(0, NO_CONTOURS_SHA256),), not_previewed=unshown)


def test_the_reader_takes_a_contours_digest_only_where_a_sheet_shows_them():
    document = {
        "instances": [
            {
                "position": 0,
                "source_sha256": "0f" * 32,
                "pixel_sha256": None,
                "contour_sha256": "2f" * 32,
                "reasons": [],
            }
        ],
        "series": [{"positions": [0]}],
        "previews": [],
        "not_previewed": [],
    }
    with pytest.raises(QcPackError, match="not of its format"):
        face_review._series_files(json.dumps(document).encode("ascii"))
    document["previews"] = [
        {"kind": "structure-set-contours", "frames": [{"position": 0, "frame": 0}]}
    ]
    files_of = face_review._series_files(json.dumps(document).encode("ascii"))
    (entry,) = files_of[0]
    assert entry[2] == bytes.fromhex("2f" * 32) and not entry[3]


# A run's verdict on a structure set.


def _verdict_run(structure_set):
    """Run a structure set alone under ``basic``, attest its series absent,
    and run it again under the option; return the first pack's entry and
    the second run's outcome."""
    directory = Path(tempfile.mkdtemp(prefix="c"))
    try:
        (directory / "in").mkdir()
        (directory / "in" / "rtstruct.dcm").write_bytes(structure_set)
        first = run.run(
            run.discover(directory / "in"),
            directory / "r1",
            InstanceTransform(compose_policy("basic"), KEY, unvalidated_policy=True),
            ReleaseGate(),
            qc_destination=directory / "qc1",
        )
        pack = json.loads(first.qc_pack.read_text("utf-8"))
        _attest(first.qc_pack.parent, {pack["series"][0]["positions"][0]: Face.ABSENT})
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
        return pack, second.outcomes[0]
    finally:
        shutil.rmtree(directory, ignore_errors=True)


@pytest.mark.deid_requirement("PS3.15-E.3.2-01")
def test_a_verdict_releases_a_structure_set_only_where_its_contours_were_shown():
    shown = _structure_set([[_closed(files.circle((0, 0, z), 30.0)) for z in (0, 3)]])
    pack, outcome = _verdict_run(shown)
    assert [p["kind"] for p in pack["previews"]] == ["structure-set-contours"]
    assert pack["instances"][0]["contour_sha256"] is not None
    assert outcome.status.value == "released"

    unshown = _structure_set(
        [[_closed(files.circle((0, 0, 0), 30.0))], [_closed(_sagittal())]]
    )
    pack, outcome = _verdict_run(unshown)
    assert pack["previews"] == []
    assert pack["not_previewed"] == [{"position": 0, "reason": "contours-not-shown"}]
    assert pack["instances"][0]["contour_sha256"] is None
    # Its verdict was on none of its contours, so it gives none.
    assert HeldVisualFeatures(VisualFeaturesReason.NO_FACE_VERDICT) in outcome.reasons


def test_a_verdict_does_not_release_a_structure_set_whose_sheet_is_too_tall(
    monkeypatch,
):
    written = _structure_set([[_closed(files.circle((0, 0, z), 30.0)) for z in (0, 3)]])
    monkeypatch.setattr(qc_contours, "MAXIMUM_SHEET_PIXELS", 1)
    pack, outcome = _verdict_run(written)
    assert pack["previews"] == []
    assert pack["not_previewed"] == [{"position": 0, "reason": "contours-not-shown"}]
    assert pack["instances"][0]["contour_sha256"] is None
    assert HeldVisualFeatures(VisualFeaturesReason.NO_FACE_VERDICT) in outcome.reasons
    assert outcome.status.value != "released"
