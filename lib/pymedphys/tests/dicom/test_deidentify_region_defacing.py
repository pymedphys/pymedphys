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

"""RT Structure Set contours cut by, and PET images set to zero activity
in, a defaced CT series' face block. Every UID and value here is
invented."""

from __future__ import annotations

import math

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest, shapely

from pymedphys._dicom.deidentify.defacing import FaceBlock
from pymedphys._dicom.deidentify.dose_defacing import DoseBlock
from pymedphys._dicom.deidentify.face_blocks import KeptSlice
from pymedphys._dicom.deidentify.pixel_cleaning import PixelDataRefused
from pymedphys._dicom.deidentify.region_defacing import (
    ContoursRefused,
    PetDefacer,
    cut_contours,
)

from . import _synthetic_head_dicom as files

# The block holds the points with y below 0 and z above 0: anterior is -y.
_BLOCK = FaceBlock((0.0, 0.0, 0.0), (0.0, -1.0, 0.0), 0.0, ((0, 0, 0), (0, 0, 0)))
_CT_Z = (10.0, 20.0, 30.0)
_FRAME = files.FRAME


def _kept_slice(z: float) -> KeptSlice:
    """An axial slice over x and y from -20 to 20 mm at 1 mm, whose kept
    pixels are those in the block with x from -5 to 5 mm and y from -10 to
    -1 mm, above z = 15 mm."""
    x = np.arange(-20, 21)[None, :]
    y = np.arange(-20, 21)[:, None]
    kept = (np.abs(x) <= 5) & (y >= -10) & (y <= -1) & (z > 15)
    return KeptSlice((-20.0, -20.0, z), files.AXIAL, (1.0, 1.0), kept)


_REGION = DoseBlock(_BLOCK, tuple(_kept_slice(z) for z in _CT_Z))


def _rectangle(x0, x1, y0, y1, z):
    return np.array([(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)], float)


def _structure_set(*rois, frame=_FRAME):
    """A structure set of one ROI for each list of contours, each a
    (Contour Geometric Type, points) pair, in ``frame``."""
    dataset = pydicom.Dataset()
    dataset.StructureSetROISequence = []
    dataset.ROIContourSequence = []
    for number, contours in enumerate(rois, start=1):
        roi = pydicom.Dataset()
        roi.ROINumber = number
        roi.ReferencedFrameOfReferenceUID = frame
        dataset.StructureSetROISequence.append(roi)
        item = pydicom.Dataset()
        item.ReferencedROINumber = number
        item.ContourSequence = []
        for kind, points in contours:
            contour = pydicom.Dataset()
            contour.ContourGeometricType = kind
            contour.NumberOfContourPoints = len(points)
            contour.ContourData = [f"{v:.6g}" for v in np.ravel(points)]
            item.ContourSequence.append(contour)
        dataset.ROIContourSequence.append(item)
    return dataset


def _cut(kind, points):
    """The contours written of one contour of one ROI, as points, or None
    where it is written as received."""
    cut = cut_contours(_REGION, _structure_set([(kind, points)]), _FRAME)
    if not cut:
        return None
    ((index, written),) = list(cut.items())
    assert index == 0 and all(each.contour == 0 for each in written)
    return [
        np.array([float(v) for v in each.values]).reshape(-1, 3) for each in written
    ]


def _polygon(points):
    return shapely.geometry.Polygon(points[:, :2])


def _outside(points):
    """Where each point lies outside the open block, within rounding."""
    ahead = -points[:, 1]
    return (ahead <= 1e-9) | (points[:, 2] <= 1e-9)


# What is written as received.


@pytest.mark.parametrize(
    "points",
    [
        _rectangle(-10, 10, 1, 15, 20),  # behind the block
        _rectangle(-10, 10, -15, 15, -5),  # below it
        _rectangle(-4, 4, -9, -2, 20),  # in the kept cavity alone
        # Crossing into the block within the kept cavity alone, so that the
        # points just ahead of the plane, whose nearest pixels lie on it and
        # are not written as air, do not count.
        _rectangle(-4, 4, -8, 10, 20),
        _rectangle(-10, 10, 0, 15, 20),  # an edge on the plane
    ],
    ids=["behind", "below", "in the cavity", "into the cavity", "touching"],
)
def test_a_contour_that_reaches_no_pixel_written_as_air_is_kept_whole(points):
    assert _cut("CLOSED_PLANAR", points) is None


def test_a_contour_wholly_in_the_face_is_removed():
    # As an eye's is.
    assert _cut("CLOSED_PLANAR", _rectangle(8, 15, -15, -8, 20)) == []


def test_a_point_kept_whole_or_removed_by_where_it_lies():
    assert _cut("POINT", np.array([[0.0, -5.0, 20.0]])) is None  # cavity
    assert _cut("POINT", np.array([[0.0, 5.0, 20.0]])) is None  # behind
    assert _cut("POINT", np.array([[15.0, -5.0, 20.0]])) == []  # face


# What is cut.


@pytest.mark.parametrize("kind", ["CLOSED_PLANAR", "CLOSEDPLANAR_XOR"])
def test_a_contour_that_reaches_the_face_is_cut_by_the_whole_block(kind):
    # It reaches beyond the kept cavity, so its part ahead of the plane,
    # the cavity's included, is cut away.
    points = _rectangle(-10, 10, -15, 10, 20)

    (written,) = _cut(kind, points)

    assert _polygon(written).equals(_polygon(_rectangle(-10, 10, 0, 10, 20)))
    assert _outside(written).all()


def test_a_contour_below_the_cavity_floor_is_cut_where_it_enters_the_block():
    # On the slice at 10 mm, defacing keeps nothing.
    (written,) = _cut("CLOSED_PLANAR", _rectangle(-4, 4, -8, 10, 10))

    assert _polygon(written).equals(_polygon(_rectangle(-4, 4, 0, 10, 10)))


def test_a_contour_beyond_the_slices_is_cut_where_it_lies_in_the_block():
    # No slice lies within half their spacing of 50 mm, so each point counts
    # where it is in the block.
    (written,) = _cut("CLOSED_PLANAR", _rectangle(-4, 4, -8, 10, 50))

    assert _polygon(written).equals(_polygon(_rectangle(-4, 4, 0, 10, 50)))


def test_an_edge_that_crosses_the_block_between_its_vertices_is_cut():
    # In the plane x = 0, no vertex is in the block, but the edge from the
    # first, behind the plane and above 0 mm, to the second, ahead of it
    # and below, crosses the block's corner.
    points = np.array([(0, 2, 8), (0, -8, -2), (0, 10, -10)], float)

    written = _cut("CLOSED_PLANAR", points)

    def polygon(each):
        return shapely.geometry.Polygon(each[:, 1:])

    expected = polygon(points).difference(shapely.geometry.box(-100, 0, 0, 100))
    assert expected.area < polygon(points).area
    got = shapely.ops.unary_union([polygon(piece) for piece in written])
    assert got.symmetric_difference(expected).area < 1e-9
    assert all(_outside(piece).all() for piece in written)


def test_a_contour_cut_in_two_is_written_as_two_numbered_once():
    # A U whose base is in the block leaves its two arms behind the plane.
    points = np.array(
        [
            (-15, -15, 20),
            (15, -15, 20),
            (15, 10, 20),
            (8, 10, 20),
            (8, -8, 20),
            (-8, -8, 20),
            (-8, 10, 20),
            (-15, 10, 20),
        ],
        float,
    )
    structure_set = _structure_set([("CLOSED_PLANAR", points)])

    for reverse in (False, True):
        each = points[::-1] if reverse else points
        structure_set.ROIContourSequence[0].ContourSequence[0].ContourData = [
            f"{v:.6g}" for v in each.ravel()
        ]
        ((_, written),) = list(cut_contours(_REGION, structure_set, _FRAME).items())
        assert [piece.numbered for piece in written] == [True, False]
        areas = sorted(
            _polygon(np.array([float(v) for v in piece.values]).reshape(-1, 3)).area
            for piece in written
        )
        assert areas == [70.0, 70.0]


def test_a_polygon_that_crosses_itself_is_written_outside_the_block():
    # A bow tie, whose crossings along the plane cannot be paired as a
    # simple polygon's are.
    points = np.array(
        [(-10, -10, 20), (10, 10, 20), (10, -10, 20), (-10, 10, 20)], float
    )

    written = _cut("CLOSED_PLANAR", points)

    assert written
    assert all(_outside(piece).all() for piece in written)


def test_random_simple_polygons_lose_exactly_their_part_in_the_block():
    # Star-shaped polygons about points near the plane, which are simple.
    rng = np.random.default_rng(20261019)
    block = shapely.geometry.box(-1000, -1000, 1000, 0)
    cut = kept_whole = 0
    for _ in range(200):
        count = int(rng.integers(3, 30))
        angles = np.sort(rng.uniform(0, 2 * np.pi, count))
        radii = rng.uniform(2, 15, count)
        centre = rng.uniform(-8, 8, 2)
        points = np.column_stack(
            [
                centre[0] + radii * np.cos(angles),
                centre[1] + radii * np.sin(angles),
                np.full(count, 10.0),
            ]
        )
        points = np.round(points, 4)
        source = _polygon(points)
        if not source.is_valid:
            continue
        written = _cut("CLOSED_PLANAR", points)
        expected = source.difference(block)
        if written is None:
            # On the slice at 10 mm, defacing keeps nothing, so only a
            # contour that enters the block no farther than its nearest
            # pixels, whose centres lie on the plane, is kept whole.
            deep = shapely.geometry.box(-1000, -1000, 1000, -1)
            assert source.intersection(deep).area == 0
            kept_whole += 1
            continue
        assert all(_outside(piece).all() for piece in written)
        got = shapely.ops.unary_union([_polygon(piece) for piece in written])
        assert got.symmetric_difference(expected).area < 1e-3 * max(expected.area, 1)
        cut += 1
    assert cut > 100, (cut, kept_whole)


def test_a_sagittal_contour_is_cut_by_both_planes():
    # In the plane x = 0, from y = -20 to 20 mm and z = -10 to 10 mm: the
    # block takes its quarter ahead of the plane and above 0 mm.
    points = np.array([(0, -20, -10), (0, 20, -10), (0, 20, 10), (0, -20, 10)], float)

    written = _cut("CLOSED_PLANAR", points)

    assert all(_outside(piece).all() for piece in written)
    areas = [shapely.geometry.Polygon(piece[:, 1:]).area for piece in written]
    assert math.isclose(sum(areas), 40 * 20 - 20 * 10)


def test_an_open_contour_is_written_as_its_pieces_outside_the_block():
    line = np.array([(-10, 10, 20), (-10, -15, 20), (10, -15, 20), (10, 10, 20)], float)

    written = _cut("OPEN_PLANAR", line)

    assert [piece.tolist() for piece in written] == [
        [[-10, 10, 20], [-10, 0, 20]],
        [[10, 0, 20], [10, 10, 20]],
    ]


def test_contours_that_are_cut_are_written_in_their_rois_order():
    structure_set = _structure_set(
        [("CLOSED_PLANAR", _rectangle(-10, 10, 1, 15, 20))],
        [
            ("CLOSED_PLANAR", _rectangle(-10, 10, 1, 15, 20)),
            ("POINT", np.array([[15.0, -5.0, 20.0]])),
            ("CLOSED_PLANAR", _rectangle(-10, 10, -15, 10, 20)),
        ],
    )

    cut = cut_contours(_REGION, structure_set, _FRAME)

    # The first ROI is unchanged; the second keeps its first contour as
    # received, loses its point, and has its third cut.
    assert list(cut) == [1]
    assert [(each.contour, each.values is None) for each in cut[1]] == [
        (0, True),
        (2, False),
    ]


# What is refused, so that the structure set stays held.


@pytest.mark.parametrize(
    "change",
    [
        lambda ds: setattr(
            ds.StructureSetROISequence[0], "ReferencedFrameOfReferenceUID", "1.2.3"
        ),
        lambda ds: delattr(
            ds.StructureSetROISequence[0], "ReferencedFrameOfReferenceUID"
        ),
        lambda ds: setattr(ds.ROIContourSequence[0], "ReferencedROINumber", 9),
        lambda ds: setattr(_contour(ds), "ContourGeometricType", "CURVED"),
        lambda ds: setattr(_contour(ds), "ContourData", ["1", "2"]),
        lambda ds: setattr(_contour(ds), "ContourData", ["nan", "0", "0"]),
        lambda ds: setattr(_contour(ds), "ContourData", ["1e7", "0", "0"]),
        lambda ds: setattr(_contour(ds), "ContourOffsetVector", ["0", "0", "1"]),
        lambda ds: setattr(_contour(ds), "ContourSlabThickness", "2"),
    ],
    ids=[
        "another frame",
        "no frame",
        "undeclared ROI",
        "unknown type",
        "not in threes",
        "not finite",
        "too far",
        "offset",
        "slab",
    ],
)
def test_a_structure_set_that_cannot_be_cut_is_refused(change):
    structure_set = _structure_set([("CLOSED_PLANAR", _rectangle(-10, 10, 1, 15, 20))])
    change(structure_set)

    with pytest.raises(ContoursRefused) as raised:
        cut_contours(_REGION, structure_set, _FRAME)
    assert str(raised.value) == "the contours cannot be cut by the block"


def _contour(dataset):
    return dataset.ROIContourSequence[0].ContourSequence[0]


# PET.


def _pet(stored=None, *, slope="1", intercept="0", **changes):
    """A PET slice at z = 20 mm over x and y from -20 to 20 mm at 2 mm, of
    100 everywhere by default."""
    dataset = pydicom.Dataset()
    dataset.ImagePositionPatient = ["-20", "-20", "20"]
    dataset.ImageOrientationPatient = [str(v) for v in files.AXIAL]
    dataset.PixelSpacing = ["2", "2"]
    dataset.Rows = dataset.Columns = 21
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = "MONOCHROME2"
    dataset.BitsAllocated = dataset.BitsStored = 16
    dataset.HighBit = 15
    dataset.PixelRepresentation = 0
    dataset.RescaleSlope = slope
    dataset.RescaleIntercept = intercept
    if stored is None:
        stored = np.full((21, 21), 100, dtype=np.uint16)
    dataset.PixelData = stored.astype("<u2").tobytes()
    meta = pydicom.dataset.FileMetaDataset()
    meta.TransferSyntaxUID = files.EXPLICIT_VR_LITTLE_ENDIAN
    dataset.file_meta = meta
    for keyword, value in changes.items():
        setattr(dataset, keyword, value)
    return dataset


def _pet_points():
    x = -20 + 2 * np.arange(21)[None, :]
    y = -20 + 2 * np.arange(21)[:, None]
    return np.broadcast_arrays(x, y)


def test_pet_is_set_to_zero_activity_in_the_block_less_the_kept_cavity():
    dataset = _pet()

    mask = PetDefacer(_REGION, dataset).mask(0, dataset.pixel_array)

    x, y = _pet_points()
    kept = (np.abs(x) <= 5) & (y >= -10) & (y <= -1)
    assert mask.frame == 0 and mask.value == 0
    assert np.array_equal(mask.mask, (y < 0) & ~kept)


def test_pet_background_is_the_stored_value_of_zero_activity_and_padding_is_kept():
    stored = np.full((21, 21), 100, dtype=np.uint16)
    stored[0, :] = 7
    dataset = _pet(stored, slope="2", intercept="-100", PixelPaddingValue=7)
    dataset["PixelPaddingValue"].VR = "US"

    mask = PetDefacer(_REGION, dataset).mask(0, dataset.pixel_array)

    assert mask.value == 50
    assert not mask.mask[0].any() and mask.mask[1].any()


def test_a_pet_slice_behind_or_below_the_block_has_no_mask():
    behind = _pet(ImagePositionPatient=["-20", "1", "20"])
    below = _pet(ImagePositionPatient=["-20", "-20", "-5"])

    for dataset in (behind, below):
        assert PetDefacer(_REGION, dataset).mask(0, dataset.pixel_array) is None


@pytest.mark.parametrize(
    "changes",
    [
        {"slope": "0"},
        {"slope": "1e-300", "intercept": "-1"},
        # Zero activity would need a stored value below 0.
        {"intercept": "100"},
        {"ImageOrientationPatient": ["2", "0", "0", "0", "1", "0"]},
        {"PixelSpacing": ["0", "2"]},
        {"ImagePositionPatient": ["1e300", "0", "0"]},
        {"NumberOfFrames": 2},
    ],
    ids=repr,
)
def test_a_pet_slice_that_cannot_be_placed_or_cleaned_is_refused(changes):
    dataset = _pet(**changes)

    with pytest.raises(PixelDataRefused):
        PetDefacer(_REGION, dataset)


def test_compressed_pet_is_refused():
    dataset = _pet()
    dataset.file_meta.TransferSyntaxUID = "1.2.840.10008.1.2.5"

    with pytest.raises(PixelDataRefused):
        PetDefacer(_REGION, dataset)


def test_a_pet_defacer_shows_nothing_and_holds_nothing():
    defacer = PetDefacer(_REGION, _pet())

    assert repr(defacer) == "PetDefacer()"
    assert defacer.held is None


def test_contour_values_are_written_as_decimal_strings_of_sixteen_characters():
    points = _rectangle(-10, 10, -15, 10, 20) + 1 / 3

    ((_, (written,)),) = list(
        cut_contours(
            _REGION, _structure_set([("CLOSED_PLANAR", points)]), _FRAME
        ).items()
    )

    assert all(len(value) <= 16 for value in written.values)
    assert len(written.values) % 3 == 0
    assert repr(written) == "WrittenContour()"
