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

"""Segmentations as indicators of a reconstructable face, and their segments
in the QC pack (D-015, D-017)."""

import copy
import io
import json

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import (
    pixel_risk,
    qc_attestation,
    qc_pack,
    qc_previews,
    qc_segments,
)
from pymedphys._dicom.deidentify.qc_pack import (
    NotPreviewedEntry,
    NotPreviewedReason,
    PreviewKind,
    RedactionEntry,
    pictured_frames,
)

from . import _synthetic_head as head
from . import _synthetic_head_dicom as files
from .test_deidentify_pixel_risk import (
    SENTINEL,
    TRANSFER_SYNTAXES,
    _read_back,
    _region,
    _series_found,
    _slice,
    _with_raw,
)
from .test_deidentify_qc_contours import _sheet_rows
from .test_deidentify_qc_previews import _decoded
from .test_deidentify_redaction_previews import (
    NOTHING_FOUND,
    _held,
    _pack,
    _redaction_images,
)

Indicator = pixel_risk.Indicator
_MAGENTA = (255, 0, 255)
# A head from 60 mm below its centre to above its top, in slices 2 mm
# apart, as the voxels that its segments are drawn on are.
_SCAN = head.axial(
    spacing=2.0, thickness=2.0, extent=((-100, 100), (-130, 110), (-60, 110))
)


def _mask(cut=False, value=-300.0):
    """The head's voxels at or above ``value``, without noise, cut ahead of
    y = -80 where ``cut``."""
    masks = []
    for index in range(len(_SCAN.positions)):
        points = _SCAN.points(index)
        inside = head.hounsfield(points) >= value
        if cut:
            inside &= points[..., 1] > -80
        masks.append(inside)
    return np.stack(masks)


def _brain():
    return _mask(value=head.BRAIN - 1) & (_mask(value=head.BONE - 1) == 0)


def _segmentation(*attributes, sop_class=files.SEGMENTATION_STORAGE, **values):
    dataset = pydicom.Dataset()
    dataset.SOPClassUID = sop_class
    dataset.SOPInstanceUID = "1.2.3.4.9"
    dataset.PatientName = SENTINEL
    dataset.NumberOfFrames = 2
    dataset.SegmentSequence = list(attributes)
    for keyword, value in values.items():
        setattr(dataset, keyword, value)
    return dataset


def _segment(**codes):
    segment = pydicom.Dataset()
    segment.SegmentNumber = 1
    segment.SegmentLabel = SENTINEL
    for keyword, (code, scheme) in codes.items():
        setattr(segment, keyword, [_region(code, scheme)])
    return segment


# Which Segmentations are indicators of a reconstructable face.


@pytest.mark.deid_requirement("MIDI-BP-15")
@TRANSFER_SYNTAXES
@pytest.mark.parametrize(
    "sop_class", [files.SEGMENTATION_STORAGE, files.LABEL_MAP_SEGMENTATION_STORAGE]
)
def test_every_segmentation_may_trace_a_face(transfer_syntax, sop_class):
    # Whatever its segment is labelled, a segment of the skin traces the face.
    series = [_segmentation(_segment(), sop_class=sop_class)]
    if transfer_syntax is not None:
        series = [_read_back(each, transfer_syntax) for each in series]
    findings = pixel_risk.assess_series(series)
    assert _series_found(findings) == {(Indicator.SEGMENTATION, (0,), None)}
    assert {f.risk for f in findings} == {pixel_risk.Risk.RECONSTRUCTABLE_FACE}


def test_a_segmentation_is_no_frame_of_a_volume():
    series = [_slice(0), _segmentation(_segment())]
    assert _series_found(pixel_risk.assess_series(series)) == {
        (Indicator.SEGMENTATION, (1,), None)
    }
    # A Surface Segmentation holds meshes, and is out of scope.
    surface = _segmentation(_segment(), sop_class="1.2.840.10008.5.1.4.1.1.66.5")
    assert not pixel_risk.assess_series([surface])


@pytest.mark.deid_requirement("MIDI-BP-15")
@TRANSFER_SYNTAXES
@pytest.mark.parametrize(
    "keyword, tag",
    [
        ("AnatomicRegionSequence", "(0008,2218)"),
        ("SegmentedPropertyTypeCodeSequence", "(0062,000F)"),
    ],
)
def test_a_segment_that_names_the_head_or_neck_says_so(transfer_syntax, keyword, tag):
    # The parotid gland, as a segment's anatomy or as what it is.
    named = _segment(**{keyword: ("45289007", "SCT")})
    named.SegmentNumber = 2
    series = [_segmentation(_segment(), named)]
    if transfer_syntax is not None:
        series = [_read_back(each, transfer_syntax) for each in series]
    assert _series_found(pixel_risk.assess_series(series)) == {
        (Indicator.SEGMENTATION, (0,), None),
        (Indicator.HEAD_OR_NECK, (0,), f"(0062,0002)[1] > {tag}[0] > (0008,0100)"),
    }


def test_a_segmentation_that_names_the_head_by_body_part_says_so():
    series = [_segmentation(_segment(), BodyPartExamined="HEAD")]
    assert _series_found(pixel_risk.assess_series(series)) == {
        (Indicator.SEGMENTATION, (0,), None),
        (Indicator.HEAD_OR_NECK, (0,), "(0018,0015)"),
    }
    elsewhere = _segment(AnatomicRegionSequence=("51185008", "SCT"))
    assert _series_found(pixel_risk.assess_series([_segmentation(elsewhere)])) == {
        (Indicator.SEGMENTATION, (0,), None)
    }


@pytest.mark.parametrize(
    "where, tag, path",
    [
        ("dataset", 0x00620002, "(0062,0002)"),
        ("segment", 0x0062000F, "(0062,0002)[0] > (0062,000F)"),
    ],
)
def test_an_unreadable_segment_sequence_is_unreadable_evidence(where, tag, path):
    segment = _segment()
    dataset = _segmentation(segment)
    _with_raw(dataset if where == "dataset" else segment, tag, "LO", SENTINEL.encode())
    findings = pixel_risk.assess_series([dataset])
    assert _series_found(findings) == {
        (Indicator.SEGMENTATION, (0,), None),
        (Indicator.UNREADABLE, (0,), path),
    }
    assert SENTINEL not in repr(findings)


def test_the_series_evidence_keeps_the_segment_sequence():
    named = _segment(SegmentedPropertyTypeCodeSequence=("45289007", "SCT"))
    dataset = _read_back(_segmentation(named), files.EXPLICIT_VR_LITTLE_ENDIAN)
    evidence = pixel_risk.series_evidence(dataset)
    assert "PatientName" not in evidence
    assert pixel_risk.assess_series([evidence]) == pixel_risk.assess_series([dataset])
    assert any(
        f.indicator is Indicator.HEAD_OR_NECK
        for f in pixel_risk.assess_series([evidence])
    )


# Which Segmentations a sheet can show.


def _read(data):
    return pydicom.dcmread(io.BytesIO(data))


def _segments(data):
    return qc_segments.segments_of(_read(data))


@pytest.mark.parametrize("kind", ["BINARY", "LABELMAP"])
def test_binary_and_label_map_segmentations_are_read(kind):
    data = files.segmentation(_SCAN, [_mask(), _brain()], kind=kind)
    found = _segments(data)
    assert found is not None
    assert found.numbers == (1, 2)
    assert found.labelmap is (kind == "LABELMAP")
    # Axial slices: the normal along z, rows along y, and columns along x.
    assert found.axes == (2, 1, 0)
    assert found.signs == (1.0, 1.0)
    assert found.frame == files.FRAME
    assert found.series == {files.SERIES}
    assert repr(found).startswith("Segments(segments=2, frames=")
    assert qc_segments.is_segmentation(_read(data))


def test_a_segmentation_is_one_by_its_class_or_its_modality():
    dataset = _read(files.segmentation(_SCAN, [_mask()]))
    dataset.SOPClassUID = files.CT_IMAGE_STORAGE
    assert qc_segments.is_segmentation(dataset)
    dataset.Modality = "CT"
    assert not qc_segments.is_segmentation(dataset)


def _altered(data, change):
    dataset = _read(data)
    change(dataset)
    return dataset


def _first_frame(dataset):
    return dataset.PerFrameFunctionalGroupsSequence[0]


@pytest.mark.parametrize(
    "change",
    [
        lambda d: setattr(d, "SegmentationType", "FRACTIONAL"),
        lambda d: setattr(d, "SegmentationType", "SURFACE"),
        lambda d: d.SegmentSequence[1].__setattr__("SegmentNumber", 1),
        lambda d: setattr(d, "NumberOfFrames", d.NumberOfFrames + 1),
        lambda d: delattr(_first_frame(d), "PlanePositionSequence"),
        lambda d: delattr(_first_frame(d), "SegmentIdentificationSequence"),
        lambda d: (
            _first_frame(d)
            .SegmentIdentificationSequence[0]
            .__setattr__("ReferencedSegmentNumber", 3)
        ),
        # A tilted plane, whose rows lie along no patient axis.
        lambda d: (
            d.SharedFunctionalGroupsSequence[0]
            .PlaneOrientationSequence[0]
            .__setattr__(
                "ImageOrientationPatient", [1, 0, 0, 0, 0.96592583, -0.25881905]
            )
        ),
        lambda d: (
            d.SharedFunctionalGroupsSequence[0]
            .PixelMeasuresSequence[0]
            .__setattr__("PixelSpacing", [0, 2])
        ),
        # One frame in another orientation.
        lambda d: _first_frame(d).__setattr__(
            "PlaneOrientationSequence",
            [
                pydicom.Dataset(
                    {
                        0x00200037: pydicom.DataElement(
                            0x00200037, "DS", [0, 1, 0, 0, 0, -1]
                        )
                    }
                )
            ],
        ),
        lambda d: (
            _first_frame(d)
            .PlanePositionSequence[0]
            .__setattr__("ImagePositionPatient", [0, 0, 2e6])
        ),
        # Frames spanning more than 2,000 mm.
        lambda d: (
            _first_frame(d)
            .PlanePositionSequence[0]
            .__setattr__("ImagePositionPatient", [-100, -130, 2100])
        ),
        lambda d: delattr(d, "SegmentSequence"),
    ],
)
def test_a_segmentation_that_a_sheet_cannot_show_is_refused(change):
    data = files.segmentation(_SCAN, [_mask(), _brain()])
    assert qc_segments.segments_of(_altered(data, change)) is None


def _two_times(kind="BINARY"):
    """A Segmentation of one segment in the same planes twice, as at two
    time points: the head, then a box that encloses it."""
    box = _box((1, 1, 1), tuple(count - 1 for count in _mask().shape))
    if kind == "BINARY":
        dataset = _read(files.segmentation(_SCAN, [_mask(), box]))
        for group in dataset.PerFrameFunctionalGroupsSequence:
            group.SegmentIdentificationSequence[0].ReferencedSegmentNumber = 1
        del dataset.SegmentSequence[1]
        return dataset
    dataset = _read(files.segmentation(_SCAN, [_mask()], kind="LABELMAP"))
    frames = dataset.NumberOfFrames
    size = dataset.Rows * dataset.Columns
    dataset.PerFrameFunctionalGroupsSequence.extend(
        copy.deepcopy(list(dataset.PerFrameFunctionalGroupsSequence))
    )
    dataset.NumberOfFrames = 2 * frames
    dataset.PixelData = dataset.PixelData[: frames * size] + bytes(box.astype(np.uint8))
    return dataset


@pytest.mark.parametrize("kind", ["BINARY", "LABELMAP"])
def test_a_segment_in_one_plane_twice_is_refused(kind):
    # The union of the two would show the box alone, hiding the head's face.
    assert qc_segments.segments_of(_two_times(kind)) is None
    # Frames of different segments in one plane are drawn, as ever.
    assert _segments(files.segmentation(_SCAN, [_mask(), _brain()])) is not None


def _shifted(*labels):
    """:func:`_two_times`'s BINARY Segmentation, with the box's frames 0.1 mm
    above the head's, and labelled by ``labels``: "organisation" as
    3D_TEMPORAL, and "temporal" or "stack" by distinct Temporal Position
    Indices or Stack IDs for the two."""
    dataset = _two_times()
    groups = dataset.PerFrameFunctionalGroupsSequence
    frames = len(groups) // 2
    for index, group in enumerate(groups):
        later = index >= frames
        if later:
            position = group.PlanePositionSequence[0]
            x, y, z = (float(value) for value in position.ImagePositionPatient)
            position.ImagePositionPatient = [x, y, round(z + 0.1, 3)]
        content = pydicom.Dataset()
        content.TemporalPositionIndex = 2 if later and "temporal" in labels else 1
        content.StackID = "2" if later and "stack" in labels else "1"
        group.FrameContentSequence = [content]
    if "organisation" in labels:
        dataset.DimensionOrganizationType = "3D_TEMPORAL"
    return dataset


@pytest.mark.parametrize(
    "labels",
    [
        ("organisation", "temporal", "stack"),
        ("organisation",),
        ("temporal",),
        ("stack",),
        (),
    ],
)
def test_frames_of_two_times_in_displaced_planes_are_refused(labels):
    # The box's planes lie between the head's, so none holds a segment
    # twice, but drawn together the box would again hide the head's face:
    # by its labels, or by its planes off the grid of the 2 mm step.
    assert qc_segments.segments_of(_shifted(*labels)) is None
    # One time point and one stack, labelled so, are drawn.
    dataset = _read(files.segmentation(_SCAN, [_mask(), _brain()]))
    for group in dataset.PerFrameFunctionalGroupsSequence:
        content = pydicom.Dataset()
        content.TemporalPositionIndex, content.StackID = 1, "1"
        group.FrameContentSequence = [content]
    dataset.DimensionOrganizationType = "3D"
    assert qc_segments.segments_of(dataset) is not None


# The sheet of a Segmentation's segments.


def _frames(data):
    """Each frame, as the QC pack's previews decode them."""
    dataset = _read(data)
    pixels = pydicom.pixels.pixel_array(io.BytesIO(data)).astype(np.float32)
    pixels = pixels.reshape(-1, dataset.Rows, dataset.Columns)
    if "PixelPaddingValue" in dataset:
        pixels[pixels == dataset.PixelPaddingValue] = np.nan
    return list(pixels)


def _sheet(data, **arguments):
    return qc_segments.segment_sheet(_segments(data), _frames(data), **arguments)


@pytest.mark.deid_requirement("MIDI-BP-15")
@pytest.mark.parametrize("kind", ["BINARY", "LABELMAP"])
def test_a_sheet_shows_the_face_that_a_segment_traces(kind):
    whole = _sheet(files.segmentation(_SCAN, [_mask()], kind=kind))
    cut = _sheet(files.segmentation(_SCAN, [_mask(cut=True)], kind=kind))
    assert whole.dtype == np.uint8 and whole.shape[2] == 3
    united, segment = _sheet_rows(whole)[:2]
    cut_united, cut_segment = _sheet_rows(cut)[:2]
    # The nose shows in the renders of the whole head, and not of the cut,
    # which spans less.
    for whole_row, cut_row in ((united, cut_united), (segment, cut_segment)):
        assert whole_row.shape != cut_row.shape or (whole_row != cut_row).any()
    # One segment's own render is the united one.
    assert (united == segment).all()
    # The same segments always give the same PNG.
    again = _sheet(files.segmentation(_SCAN, [_mask()], kind=kind))
    assert qc_previews.png(again) == qc_previews.png(whole)


def _box(low, high):
    """A solid box of voxels, from ``low`` to ``high`` in each axis."""
    box = np.zeros_like(_mask())
    box[tuple(slice(a, b) for a, b in zip(low, high))] = True
    return box


def test_a_segment_within_another_has_a_row_of_its_own():
    outer = _box((10, 20, 20), (60, 100, 80))
    inner = _box((25, 40, 35), (45, 60, 65))
    alone = _sheet_rows(_sheet(files.segmentation(_SCAN, [outer])))
    both = _sheet_rows(_sheet(files.segmentation(_SCAN, [outer, inner])))
    # The outer box hides the inner one in the united render, which is the
    # same with it, and the inner box has a row of its own after the outer's.
    assert len(alone) == 2 and len(both) == 3
    assert (both[0] == alone[0]).all()
    assert (both[1] == alone[1]).all()
    assert both[2].shape[0] < both[1].shape[0]
    assert both[2].any()


def test_a_segment_that_hides_a_cavity_has_rows_of_what_it_hides():
    box = _box((10, 20, 20), (60, 100, 80))
    hollow = box.copy()
    hollow[25:45, 40:60, 35:65] = False
    solid = _sheet_rows(_sheet(files.segmentation(_SCAN, [box])))
    rows = _sheet_rows(_sheet(files.segmentation(_SCAN, [hollow])))
    assert len(solid) == 2
    # Its cavity, and each further crossing of its surface.
    assert len(rows) > 2


def test_a_segment_that_no_pixel_holds_has_a_black_strip():
    empty = np.zeros_like(_mask())
    box = _box((10, 20, 20), (60, 100, 80))
    rows = _sheet_rows(_sheet(files.segmentation(_SCAN, [empty, box])))
    assert len(rows) == 3
    assert not rows[1].any()
    assert rows[1].shape[0] == 8


def test_a_segment_is_empty_where_a_writer_left_out_its_frames():
    band = np.zeros_like(_mask())
    band[10:50, 20:100, 20:80] = True
    gapped = band.copy()
    gapped[25:35] = False
    whole = files.segmentation(_SCAN, [band, _mask()])
    left_out = files.segmentation(_SCAN, [gapped, _mask()])
    # The frames of the gap are left out, not written empty.
    assert _read(left_out).NumberOfFrames < _read(whole).NumberOfFrames
    whole_rows = _sheet_rows(_sheet(whole))
    gapped_rows = _sheet_rows(_sheet(left_out))
    assert (whole_rows[1] != gapped_rows[1]).any()
    # In the frontal view, rows of the gap are black in the band's own row.
    tile = gapped_rows[1][:, :, 0]
    assert (~tile.any(axis=1)).sum() >= 9


def test_a_sheet_is_drawn_with_a_volume_in_its_frame():
    cut = files.segmentation(_SCAN, [_mask(cut=True)])
    found = _segments(cut)
    inside = _mask().transpose(0, 1, 2)[::-1]
    guide = _guide(inside)
    rows = _sheet_rows(qc_segments.segment_sheet(found, _frames(cut), guide))
    assert len(rows) == 3
    # The segment's outline is drawn in magenta over the volume alone.
    assert [(row == _MAGENTA).all(axis=2).any() for row in rows] == [
        False,
        True,
        False,
    ]


def _guide(inside):
    """The head's own surface on the scan's voxels, from superior."""
    from pymedphys._dicom.deidentify.qc_contours import Guide

    xs = -100.0 + 2.0 * np.arange(_SCAN.shape[1])
    ys = -130.0 + 2.0 * np.arange(_SCAN.shape[0])
    zs = np.array([position[2] for position in _SCAN.positions])[::-1]
    return Guide(inside, zs, ys, xs)


def test_a_pixel_in_no_segment_that_it_describes_is_not_shown():
    data = files.segmentation(_SCAN, [_mask(), _brain()], kind="LABELMAP")
    frames = _frames(data)
    frames[30][50, 50] = 7
    assert qc_segments.segment_sheet(_segments(data), frames) is None
    # Background, as Pixel Padding Value names it, is no segment's.
    assert _sheet(data) is not None


def test_a_sheet_needs_every_frame_and_no_more():
    data = files.segmentation(_SCAN, [_mask()])
    found, frames = _segments(data), _frames(data)
    assert qc_segments.segment_sheet(found, frames[:-1]) is None
    assert qc_segments.segment_sheet(found, [*frames, frames[0]]) is None
    assert qc_segments.segment_sheet(found, [frames[0][:-1], *frames[1:]]) is None


def test_a_sheet_over_its_tallest_is_not_drawn():
    data = files.segmentation(_SCAN, [_mask(), _brain()])
    sheet = _sheet(data)
    assert _sheet(data, tallest=sheet.shape[0]) is not None
    assert _sheet(data, tallest=sheet.shape[0] - 1) is None
    # Nor before any of it is drawn, where its rows cannot fit at least.
    assert _sheet(data, tallest=10) is None


# Where each pixel is drawn: at the voxel nearest the pixel's centre, which
# PS3.3 Section C.7.6.2.1.1 places at the frame's position plus the column
# index times the column spacing along the row direction plus the row
# index times the row spacing along the column direction.

_ORIENTATIONS = {
    "head first supine": (1.0, 0.0, 0.0, 0.0, 1.0, 0.0),
    "head first prone": (-1.0, 0.0, 0.0, 0.0, -1.0, 0.0),
    "feet first prone": (1.0, 0.0, 0.0, 0.0, -1.0, 0.0),
    "sagittal": (0.0, 1.0, 0.0, 0.0, 0.0, -1.0),
    "coronal": (1.0, 0.0, 0.0, 0.0, 0.0, -1.0),
}


@pytest.mark.parametrize("orientation", list(_ORIENTATIONS))
def test_each_pixel_is_drawn_at_the_voxel_nearest_it(orientation):
    cosines = np.array(_ORIENTATIONS[orientation])
    row, column = cosines[:3], cosines[3:]
    normal = np.cross(row, column)
    # Off centre, with rows 0.8 mm apart and columns 1.2 mm apart, and
    # frames 2 mm apart along the normal.
    origin = np.array([-37.3, 21.9, 113.7])
    scan = head.Scan(
        tuple(cosines),
        tuple(tuple(origin + 2.0 * k * normal) for k in range(5)),
        (0.8, 1.2),
        (40, 30),
    )
    masks = np.zeros((1, 5, 40, 30), bool)
    masks[0, 3, 17, 11] = True
    segments = qc_segments.segments_of(
        _read(files.segmentation(scan, list(masks), keep_empty=True))
    )
    lattice = qc_segments._own_lattice(segments)  # pylint: disable = protected-access
    placed = qc_segments._Placement(segments, lattice)  # pylint: disable = protected-access
    inside = np.zeros(lattice.shape, bool)
    for index, plane in enumerate(masks[0]):
        position = segments.origins[index]
        qc_segments._put(  # pylint: disable = protected-access
            inside,
            (0, 0, 0),
            segments.axes,
            placed.slices(position),
            (0, 0),
            placed.pooled(position, plane),
        )
    point = np.array(scan.positions[3]) + 11 * 1.2 * row + 17 * 0.8 * column
    expected = (
        int(np.abs(lattice.zs - point[2]).argmin()),
        int(np.abs(lattice.ys - point[1]).argmin()),
        int(np.abs(lattice.xs - point[0]).argmin()),
    )
    assert list(zip(*np.nonzero(inside))) == [expected]


@pytest.mark.parametrize("spacing", [0.5, 5.0])
def test_no_pixel_is_lost_and_no_voxel_missed(spacing):
    # A line one pixel wide of pixels finer than the voxels, and a block of
    # pixels coarser than them, in one axial plane.
    scan = head.Scan(
        (1.0, 0.0, 0.0, 0.0, 1.0, 0.0),
        tuple((0.0, 0.0, 2.0 * k) for k in range(3)),
        (spacing, spacing),
        (60, 60),
    )
    mask = np.zeros((3, 60, 60), bool)
    if spacing < 2:
        mask[1, 30, 5:55] = True
    else:
        mask[1, 20:23, 20:23] = True
    segments = qc_segments.segments_of(
        _read(files.segmentation(scan, [mask], keep_empty=True))
    )
    lattice = qc_segments._own_lattice(segments)  # pylint: disable = protected-access
    placed = qc_segments._Placement(segments, lattice)  # pylint: disable = protected-access
    plane = placed.pooled(segments.origins[1], mask[1])
    on = np.argwhere(plane)
    if spacing < 2:
        # One row of voxels, with no gap along the line's 25 mm.
        assert len(set(on[:, 0])) == 1
        columns = np.sort(on[:, 1])
        assert (np.diff(columns) == 1).all()
        assert len(columns) >= 49 * spacing / lattice.voxel
    else:
        # A solid block of voxels over the 15 mm that the pixels cover.
        rows, columns = np.ptp(on[:, 0]) + 1, np.ptp(on[:, 1]) + 1
        assert len(on) == rows * columns
        assert rows * lattice.voxel >= 3 * spacing - lattice.voxel


@pytest.mark.parametrize("fine", [0, 1])
def test_a_ribbon_finer_along_one_axis_and_coarser_along_the_other_is_whole(fine):
    # Pixels 0.5 mm apart along one axis and 5 mm along the other, with a
    # ribbon one pixel wide along the coarse axis, between the fine pixels
    # nearest the voxels.
    spacing = (0.5, 5.0) if fine == 0 else (5.0, 0.5)
    shape = (80, 12) if fine == 0 else (12, 80)
    scan = head.Scan(
        (1.0, 0.0, 0.0, 0.0, 1.0, 0.0),
        tuple((0.0, 0.0, 2.0 * k) for k in range(3)),
        spacing,
        shape,
    )
    mask = np.zeros((3, *shape), bool)
    ribbon = (1, 42, slice(2, 7)) if fine == 0 else (1, slice(2, 7), 42)
    mask[ribbon] = True
    segments = qc_segments.segments_of(
        _read(files.segmentation(scan, [mask], keep_empty=True))
    )
    lattice = qc_segments._own_lattice(segments)  # pylint: disable = protected-access
    placed = qc_segments._Placement(segments, lattice)  # pylint: disable = protected-access
    on = np.argwhere(placed.pooled(segments.origins[1], mask[1]))
    # One line of voxels across the fine axis, with no gap along the 25 mm
    # that the five coarse pixels cover, each 5 mm wide.
    assert len(set(on[:, fine])) == 1
    along = np.sort(on[:, 1 - fine])
    assert (np.diff(along) == 1).all()
    assert len(along) * lattice.voxel >= 25 - lattice.voxel


def _plates(keep_empty, apart=20, thickness=None):
    """A Segmentation of one segment, a plate at z = 0 and another ``apart``
    mm above, in frames 1 mm apart, of pixels 0.5 mm apart, with or without
    the empty frames between them, and of Slice Thickness ``thickness`` mm
    where given, or 1 mm."""
    scan = head.Scan(
        (1.0, 0.0, 0.0, 0.0, 1.0, 0.0),
        tuple((0.0, 0.0, float(k)) for k in range(apart + 1)),
        (0.5, 0.5),
        (40, 40),
    )
    mask = np.zeros((apart + 1, 40, 40), bool)
    mask[[0, apart], 10:30, 10:30] = True
    data = files.segmentation(scan, [mask], keep_empty=keep_empty)
    if thickness is None:
        return data
    dataset = _read(data)
    measures = dataset.SharedFunctionalGroupsSequence[0].PixelMeasuresSequence[0]
    measures.SliceThickness = thickness
    return files.written(dataset)


def test_a_writer_leaving_out_every_segment_s_empty_frames_changes_nothing():
    sparse, dense = _plates(False), _plates(True)
    assert _read(sparse).NumberOfFrames == 2
    assert _read(dense).NumberOfFrames == 21
    assert np.array_equal(_sheet(sparse), _sheet(dense))
    # Each plate is drawn in the one slice of voxels within its 1 mm cell,
    # not across the 20 mm between them.
    segments = _segments(sparse)
    lattice = qc_segments._own_lattice(segments)  # pylint: disable = protected-access
    placed = qc_segments._Placement(segments, lattice)  # pylint: disable = protected-access
    assert [len(placed.slices(origin)) for origin in segments.origins] == [1, 1]


def test_a_slice_thickness_above_the_spacing_bridges_no_left_out_frames():
    # Plates 4 mm apart, of 5 mm Slice Thickness and 1 mm Spacing Between
    # Slices: written, the empty frames between them keep the slice of
    # voxels between them empty, and left out, they still do.
    sparse, dense = _plates(False, 4, 5), _plates(True, 4, 5)
    assert _read(sparse).NumberOfFrames == 2
    assert _read(dense).NumberOfFrames == 5
    assert np.array_equal(_sheet(sparse), _sheet(dense))
    segments = _segments(sparse)
    assert segments.step == 1.0
    lattice = qc_segments._own_lattice(segments)  # pylint: disable = protected-access
    placed = qc_segments._Placement(segments, lattice)  # pylint: disable = protected-access
    drawn = np.union1d(*(placed.slices(origin) for origin in segments.origins))
    between = np.flatnonzero((lattice.zs > 0.5) & (lattice.zs < 3.5))
    assert between.size and not np.intersect1d(drawn, between).size


@pytest.mark.parametrize(
    "measures",
    [
        {},
        {"SliceThickness": "0"},
        {"SliceThickness": "1", "SpacingBetweenSlices": "-1"},
        {"SpacingBetweenSlices": "nan"},
    ],
)
def test_frames_in_two_planes_need_a_step_to_be_placed(measures):
    dataset = _read(_plates(False))
    shared = dataset.SharedFunctionalGroupsSequence[0].PixelMeasuresSequence[0]
    del shared.SliceThickness, shared.SpacingBetweenSlices
    for keyword, value in measures.items():
        setattr(shared, keyword, value)
    assert qc_segments.segments_of(dataset) is None
    # Frames in one plane need none.
    one = _read(files.segmentation(_SCAN, [_box((40, 20, 20), (41, 100, 80))]))
    measured = one.SharedFunctionalGroupsSequence[0].PixelMeasuresSequence[0]
    del measured.SliceThickness, measured.SpacingBetweenSlices
    assert qc_segments.segments_of(one) is not None
    # The spacing is the step, or the thickness where there is no spacing.
    shared.SliceThickness, shared.SpacingBetweenSlices = "5", "1"
    assert qc_segments.segments_of(dataset).step == 1.0
    del shared.SpacingBetweenSlices
    shared.SliceThickness = "2"
    assert qc_segments.segments_of(dataset).step == 2.0


@pytest.mark.parametrize(
    "apart, keep_empty, measures",
    [
        # Plates 20 mm apart, on no grid of 3 mm.
        (20, False, {"SpacingBetweenSlices": "3"}),
        (20, True, {"SpacingBetweenSlices": "3"}),
        # Of 5 mm Slice Thickness and no spacing, frames 1 mm apart, and
        # plates 4 mm apart, as with their empty frames left out.
        (4, True, {"SliceThickness": "5"}),
        (4, False, {"SliceThickness": "5"}),
    ],
)
def test_planes_off_the_grid_of_their_step_are_refused(apart, keep_empty, measures):
    # The step cannot then tell which planes a writer left out.
    dataset = _read(_plates(keep_empty, apart))
    shared = dataset.SharedFunctionalGroupsSequence[0].PixelMeasuresSequence[0]
    del shared.SliceThickness, shared.SpacingBetweenSlices
    for keyword, value in measures.items():
        setattr(shared, keyword, value)
    assert qc_segments.segments_of(dataset) is None


# A Segmentation's previews in the QC pack.


def _ct():
    return files.ct_files(_SCAN)


def test_a_segmentation_is_previewed_by_its_segments_with_its_ct():
    ct = _ct()
    written = dict(enumerate(ct))
    position = len(written)
    written[position] = files.segmentation(_SCAN, [_mask(cut=True), _brain()])
    found = qc_previews.previews_of(written, {position})
    assert not found.not_previewed
    assert position in found.pixels_shown
    (sheet,) = [
        p for p in found.previews if p.kind is PreviewKind.SEGMENTATION_SEGMENTS
    ]
    frames = _read(written[position]).NumberOfFrames
    assert sheet.frames == (
        *((position, frame) for frame in range(frames)),
        *((index, 0) for index in range(len(ct))),
    )
    rows = _sheet_rows(_decoded(sheet.png))
    # The united row, the guide row, and a row or more for each segment.
    assert len(rows) >= 4
    magenta = [(row == _MAGENTA).all(axis=2).any() for row in rows]
    assert magenta == [False, True] + [False] * (len(rows) - 2)
    # Segments sheets follow the series' previews; its cine strip and its
    # preview at full resolution, as a high-risk instance, are kept.
    kinds = [preview.kind for preview in found.previews]
    assert kinds.index(PreviewKind.SEGMENTATION_SEGMENTS) > kinds.index(
        PreviewKind.SERIES_SURFACE
    )
    assert PreviewKind.INSTANCE in kinds


@pytest.mark.parametrize(
    "why", ["fractional", "unlisted", "too tall", "two times", "displaced"]
)
def test_a_segmentation_that_no_sheet_shows_is_held(monkeypatch, why):
    masks = [_mask(), _brain()]
    if why == "fractional":
        data = files.segmentation(_SCAN, masks, kind="FRACTIONAL")
    elif why == "unlisted":
        dataset = _read(files.segmentation(_SCAN, masks, kind="LABELMAP"))
        del dataset.SegmentSequence[1]
        data = files.written(dataset)
    elif why == "two times":
        data = files.written(_two_times())
    elif why == "displaced":
        data = files.written(_shifted("organisation", "temporal", "stack"))
    else:
        data = files.segmentation(_SCAN, masks)
        monkeypatch.setattr(qc_previews.qc_contours, "MAXIMUM_SHEET_PIXELS", 100)
    found = qc_previews.previews_of({0: data}, ())
    assert found.not_previewed == (
        NotPreviewedEntry(0, NotPreviewedReason.SEGMENTS_NOT_SHOWN),
    )
    assert not found.pixels_shown
    # Its cine strip is kept, though it shows no more than 16 frames.
    assert [p.kind for p in found.previews] == [PreviewKind.SERIES_CINE]


def test_only_a_segments_sheet_shows_a_segmentation_as_it_could_show_a_face():
    # Of no more than 16 frames, which a cine strip shows each of.
    masks = np.zeros((1, *_mask().shape), bool)
    masks[0, 30:40] = _mask()[30:40]
    dataset = _read(files.segmentation(_SCAN, list(masks)))
    dataset.SegmentationType = "FRACTIONAL"
    found = qc_previews.previews_of({0: files.written(dataset)}, ())
    (cine,) = found.previews
    assert len(cine.frames) == dataset.NumberOfFrames
    assert not found.pixels_shown
    assert pictured_frames([(cine.kind.value, cine.frames)], (), None) == {0: 10}


def test_a_segments_sheet_counts_its_frames_only_for_its_segmentation():
    listed = [(PreviewKind.SEGMENTATION_SEGMENTS.value, [(5, 0), (5, 1), (0, 0)])]
    assert pictured_frames(listed, ()) == {5: 2}


def test_frames_of_one_bit_not_whole_bytes_are_decoded_one_at_a_time():
    # 121 by 101 pixels, so each frame after the first starts within a byte,
    # which pydicom 3.0 does not decode one frame at a time.
    scan = head.axial(
        spacing=2.0, thickness=2.0, extent=((-100, 100), (-130, 110), (-20, 20))
    )
    masks = np.stack([head.hounsfield(scan.points(i)) > -300 for i in range(21)])
    data = files.segmentation(scan, [masks])
    assert (121 * 101) % 8
    instance = qc_previews._instance(0, data)  # pylint: disable = protected-access
    assert instance.packed
    decoded = list(qc_previews._packed_frames(instance, range(21)))  # pylint: disable = protected-access
    assert np.array_equal(np.stack(decoded).astype(bool), masks)
    found = qc_previews.previews_of({0: data}, {0})
    assert not found.not_previewed
    assert found.pixels_shown == {0}


def test_a_cleaned_segmentation_whose_segments_are_not_shown_keeps_its_redaction_previews():
    dataset = _read(files.segmentation(_SCAN, [_mask()]))
    dataset.SegmentationType = "FRACTIONAL"
    dataset.BitsAllocated = dataset.BitsStored = 8
    dataset.HighBit = 7
    frames = dataset.NumberOfFrames
    dataset.PixelData = np.zeros((frames, *_SCAN.shape), np.uint8).tobytes()
    data = files.written(dataset)
    entry = RedactionEntry(0, NOTHING_FOUND, frames, *_SCAN.shape, ())
    previews = qc_previews.previews_of({0: data}, (), {0: (data, entry)})
    assert previews.not_previewed == (
        NotPreviewedEntry(0, NotPreviewedReason.SEGMENTS_NOT_SHOWN),
    )
    assert [preview.frames for preview, _ in _redaction_images(previews)] == [
        ((0, frame),) for frame in range(frames)
    ]
    pack = _pack(
        instances=(_held(),),
        redactions=(entry,),
        previews=previews.previews,
        not_previewed=previews.not_previewed,
    )
    document = json.dumps(qc_pack.pack_document(pack)).encode("ascii")
    assert list(qc_attestation.previewed_redactions(document)) == [0]
