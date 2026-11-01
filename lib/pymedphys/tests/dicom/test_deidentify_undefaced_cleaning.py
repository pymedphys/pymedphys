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

"""Instances in a defaced frame that a run once held undefaced and now
cleans: in a frame of several defaced series, in a structure set naming
several frames, of a dose of differences, and of contours with slabs.
Every UID and value here is invented."""

# The cleaning's private geometry is tested directly.
# pylint: disable = protected-access

from __future__ import annotations

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest, shapely

from pymedphys._dicom.deidentify import contour_slabs, face_blocks, region_defacing
from pymedphys._dicom.deidentify.contour_slabs import (
    Slab,
    SlabRefused,
    SlabValues,
    slab_of,
    slab_values,
    spread,
)
from pymedphys._dicom.deidentify.defacing import FaceBlock
from pymedphys._dicom.deidentify.dose_defacing import (
    DoseBlock,
    FrameRegion,
    RtDoseDefacer,
    joined,
    structure_set_regions,
)
from pymedphys._dicom.deidentify.face_blocks import Defaced, KeptSlice
from pymedphys._dicom.deidentify.reasons import VisualFeaturesReason
from pymedphys._dicom.deidentify.references import InstanceRecord
from pymedphys._dicom.deidentify.region_defacing import (
    ContoursRefused,
    PetDefacer,
    cut_contours,
)
from pymedphys._dicom.deidentify.segmentation_defacing import SegmentationDefacer

from . import _synthetic_head_dicom as files

# The block holds the points with y below 0 and z above 0: anterior is -y.
_BLOCK = FaceBlock((0.0, 0.0, 0.0), (0.0, -1.0, 0.0), 0.0, ((0, 0, 0), (0, 0, 0)))
# Another series' block, holding the points with x above 5 and z above
# -10: anterior is +x.
_SIDE = FaceBlock((5.0, 0.0, 0.0), (1.0, 0.0, 0.0), -10.0, ((0, 0, 0), (0, 0, 0)))
_FRAME = files.FRAME
_OTHER = files.ROOT + ".71"
_UNDEFACED = files.ROOT + ".72"


def _kept_slice(z: float) -> KeptSlice:
    """An axial slice over x and y from -20 to 20 mm at 1 mm, whose kept
    pixels are those with x from -5 to 7 mm and y from -10 to -1 mm, above
    z = 15 mm."""
    x = np.arange(-20, 21)[None, :]
    y = np.arange(-20, 21)[:, None]
    kept = (x >= -5) & (x <= 7) & (y >= -10) & (y <= -1) & (z > 15)
    return KeptSlice((-20.0, -20.0, z), files.AXIAL, (1.0, 1.0), kept)


_SLICES = tuple(_kept_slice(z) for z in (10.0, 20.0, 30.0))


def _rectangle(x0, x1, y0, y1, z):
    return np.array([(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)], float)


def _contour(kind, points, **attributes):
    contour = pydicom.Dataset()
    contour.ContourGeometricType = kind
    contour.NumberOfContourPoints = len(points)
    contour.ContourData = [f"{v:.6g}" for v in np.ravel(points)]
    for keyword, value in attributes.items():
        setattr(contour, keyword, value)
    return contour


def _structure_set(*rois, declared=(_FRAME,)):
    """A structure set of one ROI for each (frame, contours) pair, each
    contour a data set, declaring the frames ``declared``."""
    dataset = pydicom.Dataset()
    dataset.ReferencedFrameOfReferenceSequence = []
    for frame in declared:
        use = pydicom.Dataset()
        use.FrameOfReferenceUID = frame
        dataset.ReferencedFrameOfReferenceSequence.append(use)
    dataset.StructureSetROISequence = []
    dataset.ROIContourSequence = []
    for number, (frame, contours) in enumerate(rois, start=1):
        roi = pydicom.Dataset()
        roi.ROINumber = number
        roi.ReferencedFrameOfReferenceUID = frame
        dataset.StructureSetROISequence.append(roi)
        item = pydicom.Dataset()
        item.ReferencedROINumber = number
        item.ContourSequence = list(contours)
        dataset.ROIContourSequence.append(item)
    return dataset


def _points(written):
    return np.array([float(v) for v in written.values]).reshape(-1, 3)


def _area(pieces):
    union = shapely.ops.unary_union(
        [shapely.geometry.Polygon(each[:, :2]) for each in pieces]
    )
    return union.area


# Where a slab may lie.


def _slab(points, **attributes):
    values = slab_values(_contour("CLOSED_PLANAR", points, **attributes))
    return None if values is None else slab_of(values, points)


def test_a_contour_without_a_slab_or_offset_has_none():
    square = _rectangle(0, 1, 0, 1, 5)

    assert _slab(square) is None
    assert _slab(square, ContourSlabThickness="0") is None
    assert _slab(square, ContourOffsetVector=["0", "0", "0"]) is None
    assert _slab(square, ContourSlabThickness="", ContourOffsetVector=[]) is None
    assert not contour_slabs.given(_contour("CLOSED_PLANAR", square))
    assert contour_slabs.given(
        _contour("CLOSED_PLANAR", square, ContourSlabThickness="0")
    )


@pytest.mark.parametrize(
    "attributes, near, far",
    [
        ({"ContourSlabThickness": "4"}, -2.0, 2.0),
        ({"ContourOffsetVector": ["0", "0", "3"]}, 0.0, 3.0),
        ({"ContourOffsetVector": ["0", "0", "-3"]}, -3.0, 0.0),
        # The slab's centre moved 5 mm, its faces 4 and 6 mm along, and the
        # Contour Data at 0, as a reader that ignores both places it.
        ({"ContourSlabThickness": "2", "ContourOffsetVector": ["0", "0", "5"]}, 0, 6),
        ({"ContourSlabThickness": "4", "ContourOffsetVector": ["0", "0", "1"]}, -1, 3),
    ],
)
def test_a_slab_spans_every_reading_of_its_thickness_and_offset(attributes, near, far):
    square = _rectangle(0, 1, 0, 1, 5)

    slab = _slab(square, **attributes)

    # The plane's normal is z, either way.
    sign = slab.direction[2]
    assert abs(sign) == pytest.approx(1)
    assert sorted([sign * slab.near, sign * slab.far]) == pytest.approx([near, far])
    assert repr(slab) == "Slab()"
    assert repr(SlabValues(1.0, (0.0, 0.0, 0.0))) == "SlabValues()"
    ends = spread(square, slab)[:, 2]
    assert ends.min() == pytest.approx(5 + near) and ends.max() == pytest.approx(
        5 + far
    )


def test_an_offset_moves_a_contour_without_a_plane_along_itself():
    point = np.array([[1.0, 2.0, 3.0]])
    values = SlabValues(0.0, (0.0, 3.0, 4.0))

    slab = slab_of(values, point)

    assert slab.direction == pytest.approx((0.0, 0.6, 0.8))
    assert (slab.near, slab.far) == pytest.approx((0.0, 5.0))
    assert spread(point, None) == pytest.approx(point)


@pytest.mark.parametrize(
    "values, points",
    [
        # A thickness has no direction without a plane.
        (SlabValues(2.0, (0.0, 0.0, 0.0)), np.array([[0.0, 0.0, 0.0]])),
        (SlabValues(2.0, (0.0, 0.0, 0.0)), np.array([[0, 0, 0], [1, 1, 1.0]])),
        # An offset is normal to the plane.
        (SlabValues(0.0, (0.0, 1.0, 1.0)), _rectangle(0, 1, 0, 1, 5)),
        # Points off one plane.
        (
            SlabValues(1.0, (0.0, 0.0, 0.0)),
            np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 1.0]]),
        ),
    ],
    ids=["point", "line", "tilted offset", "not planar"],
)
def test_a_slab_that_cannot_be_placed_is_refused(values, points):
    with pytest.raises(SlabRefused) as raised:
        slab_of(values, points)
    assert str(raised.value) == "the contour's slab cannot be placed"


def test_a_slab_whose_values_cannot_be_read_is_refused():
    contour = _contour("CLOSED_PLANAR", _rectangle(0, 1, 0, 1, 5))
    # As read from a file, converted only once read.
    tag = pydicom.tag.Tag(0x30060044)
    contour[tag] = pydicom.dataelem.RawDataElement(
        tag, "DS", 4, b"abc ", 0, False, True
    )

    with pytest.raises(SlabRefused):
        slab_values(contour)


# The points whose span meets the block.


@pytest.mark.parametrize("seed", range(6))
def test_a_shadow_holds_the_points_whose_span_meets_the_block(seed):
    rng = np.random.default_rng(seed)
    direction = rng.normal(size=3)
    if seed == 0:
        direction = np.array([0.0, 0.0, 1.0])  # along the axial plane's normal
    if seed == 1:
        direction = np.array([0.0, 1.0, 1.0])  # pulling the two planes apart
    direction /= np.linalg.norm(direction)
    near, far = -abs(rng.normal(scale=5)), abs(rng.normal(scale=5))
    slab = Slab(tuple(direction), near, far)
    halves = region_defacing._shadow(_BLOCK, slab)
    points = rng.uniform(-15, 15, size=(4000, 3))

    found = region_defacing._inside(halves, points)

    steps = np.linspace(near, far, 2001)
    moved = points[:, None, :] + steps[None, :, None] * direction
    expected = _BLOCK.contains(moved).any(axis=1)
    # Sampling the span misses only points within a step of its boundary.
    margin = (far - near) / 2000 + 1e-9
    near_boundary = np.zeros(len(points), dtype=bool)
    for normal, offset in halves:
        near_boundary |= np.abs(points @ normal - offset) <= margin * 2
    agree = found == expected
    assert agree[~near_boundary].all()
    assert agree.mean() > 0.99


# Contours with slabs cut by the block.


def _cut_one(contour, region=None):
    region = DoseBlock(_BLOCK, _SLICES) if region is None else region
    cut = cut_contours({_FRAME: region}, _structure_set((_FRAME, [contour])))
    if not cut:
        return None
    assert len(cut) == 1
    return next(iter(cut.values()))


@pytest.mark.parametrize("seed", range(6))
def test_a_grown_shadow_holds_every_reading_within_its_margin(seed):
    rng = np.random.default_rng(seed)
    block = FaceBlock(
        (0.0, 0.0, 0.0),
        tuple(np.append(rng.normal(size=2), 0.0) / 1),
        float(rng.uniform(-5, 5)),
        ((0, 0, 0), (0, 0, 0)),
    )
    block = FaceBlock(
        block.origin,
        tuple(np.asarray(block.anterior) / np.linalg.norm(block.anterior)),
        block.inferior_limit,
        block.globes,
    )
    shared = Slab((0.0, 0.0, 1.0), -2.0, 3.0)
    # Readings tilted from the shared span, and reaching beyond it.
    owns = []
    for _ in range(3):
        tilt = np.append(rng.normal(scale=0.05, size=2), 1.0)
        tilt /= np.linalg.norm(tilt)
        owns.append(
            (
                Slab(tuple(tilt), float(rng.uniform(-3, 0)), float(rng.uniform(0, 4))),
                0.0,
            )
        )
    span, margin = region_defacing._enclosing(shared, owns)
    grown = region_defacing._shadow(block, span, margin)
    points = rng.uniform(-20, 20, size=(3000, 3))

    assert margin > 0
    for reading, _ in owns:
        direction = np.asarray(reading.direction)
        met = np.zeros(len(points), dtype=bool)
        for t in np.linspace(reading.near, reading.far, 81):
            met |= block.contains(points + t * direction)
        assert met.any()
        assert region_defacing._inside(grown, points[met]).all()


def test_contours_of_one_oblique_plane_are_cut_by_a_shadow_holding_each_reading():
    # A contour and its hole in a plane tilted about x, their points written
    # to 0.01 mm, so that the hole's own plane differs from theirs.
    angle = np.radians(20.0)

    def tilted(points):
        y, z = points[:, 1], points[:, 2]
        return np.round(
            np.column_stack(
                [
                    points[:, 0],
                    y * np.cos(angle) - z * np.sin(angle),
                    y * np.sin(angle) + z * np.cos(angle) + 10,
                ]
            ),
            2,
        )

    outer = tilted(_rectangle(-10, 10, -15, 15, 0.0))
    hole = tilted(_rectangle(-0.3, 0.3, 5, 5.2, 0.0))[::-1]
    slab = {"ContourSlabThickness": "4"}

    cut = cut_contours(
        {_FRAME: DoseBlock(_BLOCK, ())},
        _structure_set(
            (
                _FRAME,
                [
                    _contour("CLOSED_PLANAR", outer, **slab),
                    _contour("CLOSED_PLANAR", hole, **slab),
                ],
            )
        ),
    )

    assert len(cut) == 1
    pieces = next(iter(cut.values()))
    # Each piece, read along its own plane's normal from its points as
    # written, keeps every reading out of the block.
    assert any(piece.values is not None for piece in pieces)
    for piece in pieces:
        points = (
            (outer, hole)[piece.contour] if piece.values is None else _points(piece)
        )
        reading = slab_of(SlabValues(4.0, (0.0, 0.0, 0.0)), points)
        for t in np.linspace(reading.near, reading.far, 41):
            moved = points + t * np.asarray(reading.direction)
            assert not _BLOCK.contains(moved).any()


def test_a_slab_below_the_block_that_reaches_into_it_is_cut():
    plane = _rectangle(-10, 10, -15, 15, -1.0)

    assert _cut_one(_contour("CLOSED_PLANAR", plane)) is None
    (written,) = _cut_one(_contour("CLOSED_PLANAR", plane, ContourSlabThickness="4"))

    # Its slab reaches z = 1 mm, so its part ahead of the plane goes.
    got = _points(written)
    assert got[:, 2] == pytest.approx(-1.0)
    assert (got[:, 1] >= -1e-9).all()
    assert _area([got]) == pytest.approx(20 * 15)


@pytest.mark.parametrize("sign", [1, -1])
def test_an_offset_alone_moves_a_contour_into_the_block_and_is_cut(sign):
    plane = _rectangle(-10, 10, -15, 15, -5.0 * sign)
    contour = _contour(
        "CLOSED_PLANAR", plane, ContourOffsetVector=["0", "0", str(10.0 * sign)]
    )

    written = _cut_one(contour)

    # Moved up, it reaches the block; moved down, from z = 5 mm, it lay in
    # the block already, as a reader that ignores the offset places it.
    assert written is not None
    assert _area([_points(each) for each in written]) == pytest.approx(20 * 15)


@pytest.mark.parametrize(
    "z, thickness",
    [(20.0, "1"), (22.0, "8")],
    ids=["one slice", "two slices"],
)
def test_a_slab_in_the_brain_that_each_slice_it_reaches_keeps_is_kept(z, thickness):
    in_brain = _rectangle(-4, 4, -9, -2, z)

    assert _cut_one(_contour("CLOSED_PLANAR", in_brain)) is None
    # Its span reaches the slices at 20 mm, or 20 and 30 mm, each of which
    # keeps the brain that it lies in.
    assert (
        _cut_one(_contour("CLOSED_PLANAR", in_brain, ContourSlabThickness=thickness))
        is None
    )


def test_a_slab_that_reaches_a_slice_keeping_no_brain_is_cut_by_the_whole_block():
    in_brain = _rectangle(-4, 4, -9, -2, 20.0)

    # From 14 to 26 mm, it reaches the slice at 10 mm, which keeps nothing,
    # so no pixel in the block is kept on each slice it reaches.
    assert (
        _cut_one(_contour("CLOSED_PLANAR", in_brain, ContourSlabThickness="12")) == ()
    )


def _narrower(z: float) -> KeptSlice:
    """:func:`_kept_slice`, keeping only the pixels with x up to 0 mm."""
    each = _kept_slice(z)
    kept = each.kept.copy()
    kept[:, 21:] = False
    return KeptSlice(each.position, each.orientation, each.spacing, kept)


def test_a_slab_keeps_only_the_brain_that_every_slice_it_reaches_keeps():
    region = DoseBlock(_BLOCK, (_kept_slice(10.0), _kept_slice(20.0), _narrower(30.0)))
    in_brain = _rectangle(-4, 4, -9, -2, 24.0)

    assert _cut_one(_contour("CLOSED_PLANAR", in_brain), region) is None
    # From 22 to 26 mm, it reaches the slices at 20 and 30 mm, and the one
    # at 30 mm writes the pixels from x = 1 mm as air, whose squares start
    # at 0.5 mm.
    (written,) = _cut_one(
        _contour("CLOSED_PLANAR", in_brain, ContourSlabThickness="4"), region
    )
    got = _points(written)
    assert got[:, 2] == pytest.approx(24.0)
    assert _area([got]) == pytest.approx(4.5 * 7)
    assert got[:, 0].max() == pytest.approx(0.5)


@pytest.mark.parametrize(
    "slices, z, thickness",
    [
        # Beyond the last slice's reach, at 35 mm.
        (_SLICES, 30.0, "20"),
        # Two slices at one height.
        ((_kept_slice(10.0), _kept_slice(20.0), _kept_slice(20.0)), 20.0, "2"),
        # Slices whose grids differ.
        (
            (
                _kept_slice(20.0),
                KeptSlice(
                    (-19.5, -20.0, 30.0),
                    files.AXIAL,
                    (1.0, 1.0),
                    _kept_slice(30.0).kept,
                ),
            ),
            25.0,
            "2",
        ),
        # Rows that are not along x.
        (
            (
                KeptSlice(
                    (-20.0, -20.0, 20.0),
                    (1.0, 0.0, 0.0, 0.0, 1 - 1e-6, 0.0014142),
                    (1.0, 1.0),
                    _kept_slice(20.0).kept,
                ),
            ),
            20.0,
            "1",
        ),
    ],
    ids=["beyond reach", "one height", "grids differ", "tilted"],
)
def test_a_slab_whose_slices_cannot_be_judged_together_is_cut_by_the_whole_block(
    slices, z, thickness
):
    in_brain = _rectangle(-4, 4, -9, -2, z)

    assert (
        _cut_one(
            _contour("CLOSED_PLANAR", in_brain, ContourSlabThickness=thickness),
            DoseBlock(_BLOCK, slices),
        )
        == ()
    )


@pytest.mark.parametrize("seed", range(8))
def test_no_reading_of_a_slab_cut_with_the_kept_brain_meets_air(seed):
    rng = np.random.default_rng(seed)
    region = DoseBlock(_BLOCK, (_kept_slice(10.0), _kept_slice(20.0), _narrower(30.0)))
    x0, y0 = rng.uniform(-12, 2), rng.uniform(-14, -4)
    plane = _rectangle(x0, x0 + rng.uniform(4, 12), y0, y0 + rng.uniform(4, 16), 24.0)
    thickness = rng.uniform(0.5, 5.0)
    offset = rng.uniform(-1.0, 1.0)
    contour = _contour(
        "CLOSED_PLANAR",
        plane,
        ContourSlabThickness=f"{thickness:.6g}",
        ContourOffsetVector=["0", "0", f"{offset:.6g}"],
    )

    written = _cut_one(contour, region)

    pieces = [] if written is None else [_points(each) for each in written]
    kept = (
        shapely.geometry.Polygon(plane[:, :2])
        if written is None
        else shapely.ops.unary_union(
            [shapely.geometry.Polygon(each[:, :2]) for each in pieces]
        )
    ).buffer(-1e-6)
    samples = rng.uniform(-20, 20, size=(4000, 2))
    inside = samples[[kept.contains(shapely.geometry.Point(*p)) for p in samples]]
    slab = slab_of(
        SlabValues(float(f"{thickness:.6g}"), (0, 0, float(f"{offset:.6g}"))), plane
    )
    for t in np.linspace(slab.near, slab.far, 41):
        points = np.column_stack([inside, np.full(len(inside), 24.0 + t)])
        assert not region_defacing._defaced(region, points).any(), t
    # It keeps more than the whole block would leave it, wherever the brain
    # is kept on each slice that it reaches.
    whole = shapely.geometry.Polygon(plane[:, :2]).intersection(
        shapely.geometry.box(-100, 0, 100, 100)
    )
    assert kept.area >= whole.area - 1e-3


def test_a_slab_behind_the_block_is_written_as_received():
    behind = _rectangle(-10, 10, 1, 15, 20.0)

    assert (
        _cut_one(_contour("CLOSED_PLANAR", behind, ContourSlabThickness="10")) is None
    )


def test_contours_of_one_region_share_its_slab_or_are_refused():
    outer = _rectangle(-10, 10, -15, 15, -1.0)
    hole = _rectangle(-5, 5, -5, 5, -1.0)[::-1]
    slab = {"ContourSlabThickness": "4"}

    written = _cut_one(_contour("CLOSED_PLANAR", outer, **slab))
    both = cut_contours(
        {_FRAME: DoseBlock(_BLOCK, _SLICES)},
        _structure_set(
            (
                _FRAME,
                [
                    _contour("CLOSED_PLANAR", outer, **slab),
                    _contour("CLOSED_PLANAR", hole, **slab),
                ],
            )
        ),
    )

    assert written is not None
    assert len(both) == 1
    pieces = next(iter(both.values()))
    # Each is cut by the same region, so the hole keeps its part behind.
    assert [piece.contour for piece in pieces] == [0, 1]
    assert _area([_points(pieces[1])]) == pytest.approx(10 * 5)
    with pytest.raises(ContoursRefused):
        cut_contours(
            {_FRAME: DoseBlock(_BLOCK, _SLICES)},
            _structure_set(
                (
                    _FRAME,
                    [
                        _contour("CLOSED_PLANAR", outer, **slab),
                        _contour("CLOSED_PLANAR", hole),
                    ],
                )
            ),
        )


def test_a_point_or_open_contour_with_a_slab_is_cut_where_its_span_meets_the_block():
    point = np.array([[0.0, -5.0, -5.0]])
    line = np.array([[0.0, 10.0, -1.0], [0.0, -10.0, -1.0], [5.0, -10.0, -1.0]])
    offset = {"ContourOffsetVector": ["0", "0", "10"]}

    assert _cut_one(_contour("POINT", point)) is None
    assert _cut_one(_contour("POINT", point, **offset)) == ()
    bent = np.array([[5.0, 10.0, -1.0], [0.0, 2.0, -1.0], [0.0, -10.0, -1.0]])

    assert _cut_one(_contour("OPEN_PLANAR", line)) is None
    (piece,) = _cut_one(_contour("OPEN_PLANAR", bent, ContourSlabThickness="4"))
    assert _points(piece) == pytest.approx(
        np.array([[5, 10, -1.0], [0, 2, -1.0], [0, 0, -1.0]])
    )
    # Cut to a straight piece, it would keep a thickness that no reader can
    # place, having no plane, so the set is refused.
    with pytest.raises(ContoursRefused):
        _cut_one(_contour("OPEN_PLANAR", line, ContourSlabThickness="4"))
    # A thickness without a plane cannot be placed.
    with pytest.raises(ContoursRefused):
        _cut_one(_contour("POINT", point, ContourSlabThickness="2"))


# A frame of several defaced series, cut and cleaned by each block in turn.


def test_a_contour_is_cut_by_each_series_block_in_turn():
    plane = _rectangle(-15, 15, -15, 15, 20.0)
    region = FrameRegion((DoseBlock(_BLOCK, ()), DoseBlock(_SIDE, ())))

    written = _cut_one(_contour("CLOSED_PLANAR", plane), region)

    # What is left lies behind the first block's plane and not beyond the
    # second's: y from 0 and x to 5 mm.
    pieces = [_points(each) for each in written]
    assert _area(pieces) == pytest.approx(20 * 15)
    for each in pieces:
        assert (each[:, 1] >= -1e-9).all() and (each[:, 0] <= 5 + 1e-9).all()
    assert [each.numbered for each in written] == [True] + [False] * (len(written) - 1)
    assert {each.contour for each in written} == {0}


def test_a_contour_that_only_the_second_block_reaches_is_cut_by_it():
    plane = _rectangle(0, 15, 1, 15, 20.0)
    region = FrameRegion((DoseBlock(_BLOCK, ()), DoseBlock(_SIDE, ())))

    (written,) = _cut_one(_contour("CLOSED_PLANAR", plane), region)

    assert _area([_points(written)]) == pytest.approx(5 * 14)
    assert (
        _cut_one(_contour("CLOSED_PLANAR", _rectangle(0, 4, 1, 15, 20.0)), region)
        is None
    )


def test_a_region_writes_where_any_series_writes_air():
    first = DoseBlock(_BLOCK, _SLICES)
    second = DoseBlock(_SIDE, ())
    region = FrameRegion((first, second))
    plane = ((-20.0, -20.0, 20.0), files.AXIAL, (1.0, 1.0), (41, 41))

    written = region.written(*plane)

    assert np.array_equal(written, first.written(*plane) | second.written(*plane))
    assert written.any() and not first.written(*plane).all()
    assert repr(region) == "FrameRegion(blocks=2)"


def _pet(stored):
    dataset = pydicom.dcmread(
        pydicom.filebase.DicomBytesIO(
            files.pet(stored, position=(-20.0, -20.0, 20.0), spacing=(1.0, 1.0))
        )
    )
    return dataset


def test_a_pet_image_and_a_segmentation_are_cleaned_in_each_block():
    first = DoseBlock(_BLOCK, _SLICES)
    second = DoseBlock(_SIDE, ())
    region = FrameRegion((first, second))
    plane = ((-20.0, -20.0, 20.0), files.AXIAL, (1.0, 1.0), (41, 41))
    stored = np.full((41, 41), 100, dtype=np.uint16)

    mask = PetDefacer(region, _pet(stored)).mask(0, stored)

    assert np.array_equal(mask.mask, region.written(*plane))
    assert mask.value == 0
    # A segmentation's pixels in a segment, likewise.
    segmentation = pydicom.Dataset()
    segmentation.file_meta = pydicom.dataset.FileMetaDataset()
    segmentation.file_meta.TransferSyntaxUID = files.EXPLICIT_VR_LITTLE_ENDIAN
    segmentation.SOPClassUID = files.SEGMENTATION_STORAGE
    segmentation.SegmentationType = "FRACTIONAL"
    segmentation.NumberOfFrames = 1
    segmentation.Rows = segmentation.Columns = 41
    segmentation.SamplesPerPixel = 1
    segmentation.PhotometricInterpretation = "MONOCHROME2"
    segmentation.BitsAllocated = segmentation.BitsStored = 8
    segmentation.HighBit = 7
    segmentation.PixelRepresentation = 0
    groups = pydicom.Dataset()
    for keyword, attribute, value in (
        ("PlanePositionSequence", "ImagePositionPatient", ["-20", "-20", "20"]),
        ("PlaneOrientationSequence", "ImageOrientationPatient", files.AXIAL),
        ("PixelMeasuresSequence", "PixelSpacing", ["1", "1"]),
    ):
        item = pydicom.Dataset()
        setattr(item, attribute, [str(v) for v in value])
        setattr(groups, keyword, [item])
    segmentation.SharedFunctionalGroupsSequence = [groups]
    segmentation.PerFrameFunctionalGroupsSequence = [pydicom.Dataset()]
    segments = np.full((41, 41), 255, dtype=np.uint8)
    segmentation.PixelData = segments.tobytes()

    mask = SegmentationDefacer(region, segmentation).mask(0, segments)

    assert np.array_equal(mask.mask, region.written(*plane))


def _grid(stored, kind="PHYSICAL"):
    dataset = pydicom.dcmread(
        pydicom.filebase.DicomBytesIO(
            files.dose(
                stored, position=(-20.0, -20.0, 20.0), spacing=(1.0, 1.0), offsets=None
            )
        )
    )
    dataset.DoseType = kind
    return dataset


def test_a_dose_is_set_to_zero_where_any_series_writes_air():
    region = FrameRegion((DoseBlock(_BLOCK, _SLICES), DoseBlock(_SIDE, ())))
    plane = ((-20.0, -20.0, 20.0), files.AXIAL, (1.0, 1.0), (41, 41))
    stored = np.full((1, 41, 41), 100, dtype=np.uint32)
    stored[0, 30:, :20] = 10_000  # behind the one block and aside the other

    defacer = RtDoseDefacer(region, _grid(stored))
    mask = defacer.mask(0, stored[0])

    assert np.array_equal(mask.mask, region.written(*plane))
    # The dose set to zero is 1% of the grid's greatest.
    assert defacer.held is None


# A dose of differences.


def test_a_dose_of_differences_is_set_to_zero_by_its_magnitudes():
    region = DoseBlock(_BLOCK, _SLICES)
    stored = np.full((1, 41, 41), 0, dtype=np.int32)
    stored[0, 30:, :] = -10_000  # behind the block
    stored[0, :5, :] = 400  # ahead of it

    error = RtDoseDefacer(region, _grid(stored, "ERROR"))
    error.mask(0, stored[0])
    physical = RtDoseDefacer(region, _grid(stored))
    physical.mask(0, stored[0])

    assert error.held is None
    assert physical.held is VisualFeaturesReason.UNDEFACED_IN_DEFACED_FRAME
    assert error.compared(np.array([-3, 2])) == pytest.approx([3, 2])
    assert physical.compared(np.array([-3, 2])) == pytest.approx([-3, 2])
    # A difference greater than the fraction, of either sign, holds it.
    for value in (-1000, 1000):
        stored[0, :5, :] = value
        held = RtDoseDefacer(region, _grid(stored, " error "))
        held.mask(0, stored[0])
        assert held.held is VisualFeaturesReason.DOSE_IN_FACE_BLOCK


# A structure set that names several frames.


def _square(z=20.0):
    return _contour("CLOSED_PLANAR", _rectangle(-10, 10, -15, 15, z))


def test_each_frame_of_a_structure_set_is_cut_by_its_own_blocks():
    regions = {_FRAME: DoseBlock(_BLOCK, ()), _OTHER: DoseBlock(_SIDE, ())}
    structure_set = _structure_set(
        (_FRAME, [_square()]),
        (_OTHER, [_square()]),
        (_UNDEFACED, [_square()]),
        declared=(_FRAME, _OTHER, _UNDEFACED),
    )

    cut = cut_contours(regions, structure_set, (_FRAME, _OTHER))

    # The first by the block of y below 0, the second by that of x above 5
    # mm, and the third, in a frame that the run does not deface, as
    # received.
    assert sorted(cut) == [0, 1]
    ((first,), (second,)) = cut[0], cut[1]
    assert (_points(first)[:, 1] >= -1e-9).all()
    assert (_points(second)[:, 0] <= 5 + 1e-9).all()


@pytest.mark.parametrize(
    "rois, declared, defaced",
    [
        # An ROI in a frame that the set does not declare could be drawn on
        # the defaced images by a reader that places it by the set's own.
        ([(_UNDEFACED, [_square()])], (_FRAME,), (_FRAME,)),
        # A defaced frame without a region.
        ([(_OTHER, [_square()])], (_FRAME, _OTHER), (_FRAME, _OTHER)),
        # No frame.
        ([("", [_square()])], (_FRAME,), (_FRAME,)),
    ],
    ids=["undeclared", "defaced without a region", "no frame"],
)
def test_an_roi_that_cannot_be_left_or_cut_refuses_the_set(rois, declared, defaced):
    structure_set = _structure_set((_FRAME, [_square()]), *rois, declared=declared)

    with pytest.raises(ContoursRefused):
        cut_contours({_FRAME: DoseBlock(_BLOCK, ())}, structure_set, defaced)


def test_an_roi_left_as_received_is_still_read():
    unreadable = _contour("CLOSED_PLANAR", _rectangle(0, 1, 0, 1, 5))
    unreadable.ContourGeometricType = "CURVED"
    structure_set = _structure_set(
        (_FRAME, [_square()]),
        (_UNDEFACED, [unreadable]),
        declared=(_FRAME, _UNDEFACED),
    )

    with pytest.raises(ContoursRefused):
        cut_contours({_FRAME: DoseBlock(_BLOCK, ())}, structure_set, (_FRAME,))


def _drawn_on(contour, instance):
    image = pydicom.Dataset()
    image.ReferencedSOPInstanceUID = instance
    contour.ContourImageSequence = [image]
    return contour


def test_a_contour_drawn_on_a_defaced_slice_of_another_frame_refuses_the_set():
    mine, theirs = files.ROOT + ".81", files.ROOT + ".82"
    regions = {
        _FRAME: DoseBlock(_BLOCK, (), frozenset({mine})),
        _OTHER: DoseBlock(_SIDE, (), frozenset({theirs})),
    }
    declared = (_FRAME, _OTHER, _UNDEFACED)

    def cut(*rois):
        return cut_contours(
            regions, _structure_set(*rois, declared=declared), (_FRAME, _OTHER)
        )

    # On its own frame's slice, or an undefaced one, it is cut.
    assert cut((_FRAME, [_drawn_on(_square(), mine)]))
    assert cut((_FRAME, [_drawn_on(_square(), files.ROOT + ".9")]))
    for frame, instance in ((_FRAME, theirs), (_OTHER, mine), (_UNDEFACED, mine)):
        with pytest.raises(ContoursRefused):
            cut((frame, [_drawn_on(_square(), instance)]))
    # So does a frame's own list of contour images.
    structure_set = _structure_set((_FRAME, [_square()]), declared=declared)
    series = pydicom.Dataset()
    series.ContourImageSequence = _drawn_on(
        pydicom.Dataset(), mine
    ).ContourImageSequence
    study = pydicom.Dataset()
    study.RTReferencedSeriesSequence = [series]
    structure_set.ReferencedFrameOfReferenceSequence[2].RTReferencedStudySequence = [
        study
    ]
    with pytest.raises(ContoursRefused):
        cut_contours(regions, structure_set, (_FRAME, _OTHER))


def _record(frames, roi_frames=(), references=()):
    dataset = pydicom.dcmread(
        pydicom.filebase.DicomBytesIO(
            files.structure_set([("ORGAN", _rectangle(0, 1, 0, 1, 5))], frame=frames[0])
        )
    )
    dataset.ReferencedFrameOfReferenceSequence = []
    for frame in frames:
        use = pydicom.Dataset()
        use.FrameOfReferenceUID = frame
        dataset.ReferencedFrameOfReferenceSequence.append(use)
    for number, frame in enumerate(roi_frames, start=2):
        roi = pydicom.Dataset()
        roi.ROINumber = number
        roi.ReferencedFrameOfReferenceUID = frame
        dataset.StructureSetROISequence.append(roi)
    if references:
        images = []
        for instance in references:
            image = pydicom.Dataset()
            image.ReferencedSOPClassUID = files.CT_IMAGE_STORAGE
            image.ReferencedSOPInstanceUID = instance
            images.append(image)
        dataset.ROIContourSequence[0].ContourSequence[0].ContourImageSequence = images
    return InstanceRecord.from_file(files.written(dataset))


def test_a_structure_set_is_cut_in_each_defaced_frame_it_names_with_a_region():
    defaced = Defaced(frozenset({_FRAME, _OTHER}), frozenset({files.ROOT + ".81"}))
    one = FrameRegion((DoseBlock(_BLOCK, (), frozenset({files.ROOT + ".81"})),))
    regions = {_FRAME: one}

    assert structure_set_regions(_record((_FRAME,)), regions, defaced) == {_FRAME: one}
    assert structure_set_regions(_record((_FRAME, _UNDEFACED)), regions, defaced) == {
        _FRAME: one
    }
    # A defaced frame without a region, or no defaced frame named.
    assert structure_set_regions(_record((_FRAME, _OTHER)), regions, defaced) is None
    assert structure_set_regions(_record((_UNDEFACED,)), regions, defaced) is None
    # Held where it refers to a defaced slice of a frame it is not cut in.
    other = files.ROOT + ".82"
    both = Defaced(defaced.frames, frozenset({files.ROOT + ".81", other}))
    joined_ = joined({_FRAME: one})
    assert not joined_.holds(both, _record((_FRAME,), references=(files.ROOT + ".81",)))
    assert joined_.holds(both, _record((_FRAME,), references=(other,)))


# Targets and eyes with slabs.


def _with_slab(structure_set, **attributes):
    dataset = pydicom.dcmread(pydicom.filebase.DicomBytesIO(structure_set))
    for keyword, value in attributes.items():
        setattr(dataset.ROIContourSequence[0].ContourSequence[0], keyword, value)
    return dataset


def test_a_target_whose_slab_reaches_the_block_reaches_it():
    below = files.structure_set([("PTV", _rectangle(-10, 10, -15, 15, -1.0))])

    assert not face_blocks._targets_reach(_with_slab(below), _FRAME, set(), _BLOCK)
    assert face_blocks._targets_reach(
        _with_slab(below, ContourSlabThickness="4"), _FRAME, set(), _BLOCK
    )
    assert face_blocks._targets_reach(
        _with_slab(below, ContourOffsetVector=["0", "0", "2"]), _FRAME, set(), _BLOCK
    )
    # A slab that cannot be placed may reach it.
    assert face_blocks._targets_reach(
        _with_slab(below, ContourOffsetVector=["1", "0", "0"]), _FRAME, set(), _BLOCK
    )


def test_an_eye_whose_slab_moves_it_from_the_globes_disagrees():
    block = FaceBlock(
        (0.0, 0.0, 0.0), (0.0, -1.0, 0.0), 0.0, ((-30, -60, 0), (30, -60, 0))
    )
    eye = files.structure_set(
        [("ORGAN", files.circle((30.0, -60.0, 0.0), 10.0))], names=["Eye_L"]
    )

    assert not face_blocks._eyes_far(_with_slab(eye), _FRAME, block)
    assert not face_blocks._eyes_far(
        _with_slab(eye, ContourSlabThickness="4"), _FRAME, block
    )
    assert face_blocks._eyes_far(
        _with_slab(eye, ContourOffsetVector=["0", "0", "40"]), _FRAME, block
    )
    assert face_blocks._eyes_far(
        _with_slab(eye, ContourOffsetVector=["0", "40", "0"]), _FRAME, block
    )
