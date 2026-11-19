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

# pylint: disable = protected-access

"""The QC pack's surfaces sheet, and the face verdicts that it binds (D-017)."""

import hashlib
import io
import json

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest, scipy

from pymedphys._dicom.deidentify import (
    face_blocks,
    face_review,
    qc_meshes,
    qc_previews,
    qc_surfaces,
    run_qc,
)
from pymedphys._dicom.deidentify.face_review import (
    NO_SURFACES,
    FaceReview,
    surface_data_sha256,
)
from pymedphys._dicom.deidentify.instance_transform import InstanceTransform
from pymedphys._dicom.deidentify.iods import load_iod_tables
from pymedphys._dicom.deidentify.policy import compose_policy
from pymedphys._dicom.deidentify.qc_pack import (
    NO_CONTOURS_SHA256,
    NO_PIXELS_SHA256,
    NO_SURFACES_SHA256,
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
from pymedphys._dicom.deidentify.references import InstanceRecord
from pymedphys._dicom.deidentify.synthetic_corpus import SURFACE_SEGMENTATION_STORAGE

from . import _synthetic_head_dicom as files
from .test_deidentify_qc_face_verdicts import REFERENCE, _released
from .test_deidentify_visual_features_option import KEY

# A tetrahedron about the origin, 20 mm across, by its triangles' indices
# from 0, its normals outward.
_CORNERS = ((-10, -10, -10), (10, -10, -10), (-10, 10, -10), (-10, -10, 10))
_FACES = ((0, 2, 1), (0, 1, 3), (1, 2, 3), (2, 0, 3))


def _points(points=_CORNERS):
    item = pydicom.Dataset()
    item.NumberOfSurfacePoints = len(points)
    item.PointCoordinatesData = np.asarray(points, "<f4").tobytes()
    return item


def _indices(indices, vr="OL"):
    """Indices from 0 as an index list's value, from 1."""
    kind = "<u4" if vr == "OL" else "<u2"
    return (np.asarray(indices, np.int64) + 1).astype(kind).tobytes()


def _surface(points=_CORNERS, triangles=_FACES, **lists):
    """A Surface Sequence item of ``points``, with ``triangles`` and each
    of ``lists``, an index list's or a primitive sequence's keyword, given
    its indices from 0, or for a sequence, a list of each item's."""
    surface = pydicom.Dataset()
    surface.SurfaceNumber = 1
    surface.SurfacePointsSequence = [_points(points)]
    primitives = pydicom.Dataset()
    primitives.LongTrianglePointIndexList = _indices(np.ravel(triangles))
    for keyword, indices in lists.items():
        if keyword.endswith("Sequence"):
            items = []
            for each in indices:
                item = pydicom.Dataset()
                item.LongPrimitivePointIndexList = _indices(each)
                items.append(item)
            setattr(primitives, keyword, items)
        else:
            setattr(primitives, keyword, _indices(indices))
    surface.SurfaceMeshPrimitivesSequence = [primitives]
    return surface


def _meshes(*surfaces):
    dataset = pydicom.Dataset()
    dataset.SurfaceSequence = list(surfaces) or [_surface()]
    return dataset


def _segmentation(*surfaces, frame=files.FRAME):
    """A Surface Segmentation file of ``surfaces``, by default the
    tetrahedron, in ``frame``."""
    dataset = _meshes(*surfaces)
    dataset.PatientName = "Head^Analytic"
    dataset.PatientID = "H1"
    dataset.StudyInstanceUID = files.STUDY
    dataset.SeriesInstanceUID = files.ROOT + ".55"
    dataset.Modality = "SEG"
    dataset.FrameOfReferenceUID = frame
    dataset.SOPClassUID = SURFACE_SEGMENTATION_STORAGE
    dataset.SOPInstanceUID = files.ROOT + ".55.1"
    meta = pydicom.dataset.FileMetaDataset()
    meta.MediaStorageSOPClassUID = SURFACE_SEGMENTATION_STORAGE
    meta.MediaStorageSOPInstanceUID = dataset.SOPInstanceUID
    meta.TransferSyntaxUID = pydicom.uid.ExplicitVRLittleEndian
    dataset.file_meta = meta
    return files.written(dataset)


def _read(data):
    return pydicom.dcmread(io.BytesIO(data))


# Reading the meshes.


def test_each_primitive_is_drawn_as_its_edges_and_triangles():
    (mesh,) = qc_meshes.meshes_of(
        _meshes(
            _surface(
                triangles=[(0, 1, 2)],
                LongEdgePointIndexList=[0, 3],
                LongVertexPointIndexList=[3],
                TriangleStripSequence=[[0, 1, 2, 3]],
                TriangleFanSequence=[[3, 0, 1, 2]],
                LineSequence=[[0, 1, 2]],
                FacetSequence=[[0, 1, 2]],
            )
        )
    )

    assert mesh.points.tolist() == [list(map(float, each)) for each in _CORNERS]
    # The edge, the line's two, and the facet's outline, closed.
    assert mesh.edges.tolist() == [
        [0, 3],
        [0, 1],
        [1, 2],
        [0, 1],
        [1, 2],
        [2, 0],
    ]
    # The triangle, the strip's two, the fan's two about its first point,
    # and the facet's, which it fills.
    assert mesh.triangles.tolist() == [
        [0, 1, 2],
        [0, 1, 2],
        [1, 2, 3],
        [3, 0, 1],
        [3, 1, 2],
        [0, 1, 2],
    ]


def test_the_retired_16_bit_index_lists_are_drawn_as_their_replacements():
    surface = _surface(triangles=np.zeros((0, 3), int))
    (primitives,) = surface.SurfaceMeshPrimitivesSequence
    primitives.TrianglePointIndexList = _indices([0, 1, 2], "OW")
    strip = pydicom.Dataset()
    strip.PrimitivePointIndexList = _indices([1, 2, 3], "OW")
    primitives.TriangleStripSequence = [strip]

    (mesh,) = qc_meshes.meshes_of(_meshes(surface))

    assert mesh.triangles.tolist() == [[0, 1, 2], [1, 2, 3]]


def test_a_data_set_without_a_surface_sequence_holds_no_mesh():
    assert qc_meshes.meshes_of(pydicom.Dataset()) == ()


def _corrupted(change):
    surface = _surface()
    change(surface)
    return _meshes(surface)


def _set_list(keyword, indices):
    def change(surface):
        (primitives,) = surface.SurfaceMeshPrimitivesSequence
        setattr(primitives, keyword, _indices(indices))

    return change


def _set_points(points):
    def change(surface):
        (item,) = surface.SurfacePointsSequence
        item.PointCoordinatesData = np.asarray(points, "<f4").tobytes()

    return change


def _two_lists(surface):
    (primitives,) = surface.SurfaceMeshPrimitivesSequence
    item = pydicom.Dataset()
    item.LongPrimitivePointIndexList = _indices([0, 1, 2])
    item.PrimitivePointIndexList = _indices([0, 1, 2], "OW")
    primitives.LineSequence = [item]


def _double_points(surface):
    (item,) = surface.SurfacePointsSequence
    item.add_new(0x00660022, "OD", np.zeros(12, "<f8").tobytes())


def _two_point_items(surface):
    surface.SurfacePointsSequence = [_points(), _points()]


def _no_points(surface):
    (item,) = surface.SurfacePointsSequence
    item.PointCoordinatesData = b""


@pytest.mark.parametrize(
    "change",
    [
        # Indices are from 1 (PS3.3 C.27.2.1.1), so 0 is none, and each is
        # at most the count of the points.
        _set_list("LongTrianglePointIndexList", [-1, 0, 1]),
        _set_list("LongTrianglePointIndexList", [0, 1, 4]),
        _set_list("LongEdgePointIndexList", [0, 1, 2]),
        _set_list("LongTrianglePointIndexList", [0, 1, 2, 3]),
        _set_points([(0, 0, np.nan)]),
        _set_points([(0, 0, 2e6)]),
        _two_lists,
        _double_points,
        _two_point_items,
        _no_points,
    ],
)
def test_a_mesh_that_cannot_be_read_is_not_drawn(change):
    assert qc_meshes.meshes_of(_corrupted(change)) is None


@pytest.mark.parametrize(
    "sequence, count", [("TriangleStripSequence", 2), ("TriangleFanSequence", 2)]
)
def test_a_strip_or_fan_of_too_few_points_is_not_drawn(sequence, count):
    meshes = _meshes(_surface(**{sequence: [list(range(count))]}))

    assert qc_meshes.meshes_of(meshes) is None


def test_meshes_too_long_or_too_wide_are_not_drawn():
    along = qc_surfaces.LONGEST
    across = qc_surfaces.WIDEST
    assert qc_meshes.meshes_of(_meshes(_surface([(0, 0, 0), (0, 0, along)], [])))
    assert (
        qc_meshes.meshes_of(_meshes(_surface([(0, 0, 0), (0, 0, along + 2)], [])))
        is None
    )
    assert (
        qc_meshes.meshes_of(
            _meshes(_surface([(0, 0, 0)], []), _surface([(across + 2, 0, 0)], []))
        )
        is None
    )


def test_meshes_with_too_many_samples_are_not_drawn(monkeypatch):
    meshes = _meshes()
    assert qc_meshes.meshes_of(meshes) is not None
    monkeypatch.setattr(qc_meshes, "MOST_SAMPLES", 10)
    assert qc_meshes.meshes_of(meshes) is None


def test_meshes_read_in_big_endian_are_not_drawn():
    meshes = _meshes()
    meshes.set_original_encoding(False, False)

    assert qc_meshes.meshes_of(meshes) is None


def test_an_empty_surface_sequence_is_not_drawn():
    meshes = pydicom.Dataset()
    meshes.SurfaceSequence = []

    assert qc_meshes.meshes_of(meshes) is None


# The sheet.


def test_the_sheet_draws_every_mesh_united_then_each_alone():
    inner = _surface(np.asarray(_CORNERS) / 4)
    meshes = qc_meshes.meshes_of(_meshes(_surface(), inner))
    assert meshes is not None

    sheet = qc_meshes.mesh_sheet(meshes)

    assert sheet is not None and sheet.dtype == np.uint8 and sheet.shape[2] == 3
    # The union's row and the outer mesh's row are as tall as the 20 mm
    # tetrahedron's voxels, with one more on each side; the inner's, of 5
    # mm, is shorter.
    rows = _rows(sheet)
    voxels = round(20 / qc_surfaces.MINIMUM_VOXEL) + 3
    assert rows[0] == rows[1] == voxels
    assert rows[-1] < voxels


def test_a_point_is_drawn_where_it_lies_and_a_triangle_across_its_area():
    # One triangle, lying in the coronal plane y = 0, 40 mm across and 40 mm
    # tall, seen face on from the front.
    points = [(-20, 0, 0), (20, 0, 0), (-20, 0, 40)]
    (mesh,) = qc_meshes.meshes_of(_meshes(_surface(points, [(0, 1, 2)])))
    front = qc_surfaces.views(_drawn(mesh))[0]
    drawn = front > 0

    # Half of the bounding square, less the edge voxels' share.
    voxels = round(40 / qc_surfaces.MINIMUM_VOXEL) + 1
    assert drawn.sum() == pytest.approx(voxels * (voxels + 1) / 2, rel=0.1)
    # A point alone, too, is drawn.
    (mesh,) = qc_meshes.meshes_of(_meshes(_surface([(5, 5, 5)], [])))
    assert _drawn(mesh).sum() == 1


# A concave facet in the coronal plane, of 2,000 square millimetres, whose
# convex hull, of 5,000, a fan from its first point fills.
_CONCAVE = ((100, 0, 0), (20, 0, 20), (0, 0, 100), (0, 0, 0))


def _area(mesh):
    corners = mesh.points[mesh.triangles]
    sides = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
    return np.linalg.norm(sides, axis=1).sum() / 2


@pytest.mark.parametrize("start", range(4))
def test_a_concave_facet_is_filled_exactly_from_whichever_point_it_starts(start):
    order = np.roll(np.arange(4), -start).tolist()
    (mesh,) = qc_meshes.meshes_of(
        _meshes(_surface(_CONCAVE, np.zeros((0, 3), int), FacetSequence=[order]))
    )
    lattice = qc_meshes._Lattice.of([mesh])
    drawn = _drawn(mesh)

    def is_drawn(x, z):
        voxel = lattice.voxels(np.array([[x, 0.0, z]]))
        return bool(drawn[tuple(int(each[0]) for each in voxel)])

    # Its outline, closed, and triangles of its own area, not its hull's.
    assert len(mesh.edges) == 4
    assert _area(mesh) == pytest.approx(2000)
    # Well inside its indentation, some 24 mm from its outline, nothing is
    # drawn; well inside the polygon, it is.
    assert not is_drawn(40, 40)
    assert not is_drawn(60, 25)
    assert is_drawn(10, 10)
    assert is_drawn(50, 6)


def test_a_star_shaped_facet_is_filled_exactly_wherever_it_lies():
    angles = np.arange(10) * np.pi / 5
    radii = np.where(np.arange(10) % 2, 20.0, 50.0)
    flat = np.stack([radii * np.cos(angles), radii * np.sin(angles), np.zeros(10)], 1)
    rotation = np.linalg.qr(np.random.default_rng(3).normal(size=(3, 3)))[0]
    points = flat @ rotation.T + 7
    star = 5 * 50.0 * 20.0 * np.sin(np.pi / 5)

    for start in range(10):
        order = np.roll(np.arange(10), -start).tolist()
        (mesh,) = qc_meshes.meshes_of(
            _meshes(_surface(points, np.zeros((0, 3), int), FacetSequence=[order]))
        )
        assert _area(mesh) == pytest.approx(star), start


@pytest.mark.parametrize(
    "points",
    [
        # Its points off one plane by more than a quarter of a voxel.
        ((0, 0, 0), (20, 0, 0), (20, 20, 0), (0, 20, 4)),
        # An outline that crosses itself.
        ((0, 0, 0), (20, 20, 0), (20, 0, 0), (0, 20, 0)),
        # One that doubles back along a side.
        ((0, 0, 0), (20, 0, 0), (10, 0, 0), (10, 20, 0)),
        # One that touches itself.
        ((0, 0, 0), (20, 0, 0), (20, 20, 0), (10, 0, 0), (0, 20, 0)),
    ],
)
def test_a_facet_that_is_not_a_simple_planar_polygon_is_not_drawn(points):
    order = list(range(len(points)))
    facet = _meshes(_surface(points, np.zeros((0, 3), int), FacetSequence=[order]))

    assert qc_meshes.meshes_of(facet) is None


def test_a_facet_that_encloses_nothing_is_drawn_by_its_outline():
    points = ((0, 0, 0), (10, 0, 0), (20, 0, 0), (0, 10, 0))
    # Its points on one line, and one repeated.
    for order in ([0, 1, 2], [0, 1, 1, 0]):
        (mesh,) = qc_meshes.meshes_of(
            _meshes(_surface(points, np.zeros((0, 3), int), FacetSequence=[order]))
        )
        assert len(mesh.edges) == len(order)
        assert len(mesh.triangles) == 0
    # A facet with a point on a side is filled as without it.
    square = ((0, 0, 0), (10, 0, 0), (20, 0, 0), (20, 20, 0), (0, 20, 0))
    (mesh,) = qc_meshes.meshes_of(
        _meshes(_surface(square, np.zeros((0, 3), int), FacetSequence=[range(5)]))
    )
    assert _area(mesh) == pytest.approx(400)


def test_a_facet_of_too_many_points_is_not_drawn():
    count = qc_meshes.MOST_FACET_POINTS + 1
    angles = np.linspace(0, 2 * np.pi, count, endpoint=False)
    points = np.stack([np.cos(angles) * 50, np.sin(angles) * 50, np.zeros(count)], 1)
    facet = _surface(points, np.zeros((0, 3), int), FacetSequence=[range(count)])

    assert qc_meshes.meshes_of(_meshes(facet)) is None


def test_a_triangle_seen_face_on_has_no_gap():
    # A tilted triangle, sampled at a quarter of a voxel, covers each ray
    # that crosses it, so its frontal view has no hole within it.
    points = [(-30, -10, -30), (30, 10, -30), (0, 0, 30)]
    (mesh,) = qc_meshes.meshes_of(_meshes(_surface(points, [(0, 1, 2)])))
    drawn = qc_surfaces.views(_drawn(mesh))[0] > 0
    filled = scipy.ndimage.binary_fill_holes(drawn)

    assert (filled == drawn).all()


def _drawn(mesh):
    lattice = qc_meshes._Lattice.of([mesh])
    return qc_meshes._drawn(mesh, lattice, (0, 0, 0), lattice.shape)


def _rows(sheet):
    """The heights of a sheet's rows, between its grey gutters."""
    grey = (sheet == sheet[:, :1]).all(axis=(1, 2)) & (sheet[:, 0, 0] > 0)
    heights, height = [], 0
    for is_gutter in grey:
        if is_gutter:
            if height:
                heights.append(height)
            height = 0
        else:
            height += 1
    return [*heights, height]


def test_a_sheet_taller_than_its_bound_is_not_drawn():
    meshes = qc_meshes.meshes_of(_meshes(_surface(), _surface()))
    assert meshes is not None
    sheet = qc_meshes.mesh_sheet(meshes)
    assert sheet is not None

    assert qc_meshes.mesh_sheet(meshes, tallest=sheet.shape[0]) is not None
    assert qc_meshes.mesh_sheet(meshes, tallest=sheet.shape[0] - 1) is None
    assert qc_meshes.mesh_sheet(meshes, tallest=10) is None


def test_the_previews_give_one_surfaces_sheet_of_each_instance_with_meshes():
    data = _segmentation(_surface(), _surface(np.asarray(_CORNERS) / 2))
    found = qc_previews.previews_of({3: data}, ())

    (sheet,) = found.previews
    assert sheet.kind is PreviewKind.SURFACE_MESHES
    assert sheet.frames == ((3, 0), (3, 1))
    assert sheet.total_frames == 2
    assert found.surfaces_shown == {3}
    assert not found.not_previewed
    # A sheet lists meshes, not frames of pixel data.
    assert not pictured_frames([(sheet.kind.value, sheet.frames)], ())


def test_the_previews_list_an_instance_whose_meshes_cannot_be_drawn():
    data = _segmentation(_surface(triangles=[(0, 1, 4)]))
    found = qc_previews.previews_of({3: data}, (3,))

    assert not found.previews
    assert found.not_previewed == (
        NotPreviewedEntry(3, NotPreviewedReason.SURFACES_NOT_SHOWN),
    )
    assert not found.surfaces_shown


# The digest.


def _changed_points(dataset):
    (surface,) = dataset.SurfaceSequence
    (item,) = surface.SurfacePointsSequence
    values = bytearray(item.PointCoordinatesData)
    values[0] ^= 1
    item.PointCoordinatesData = bytes(values)


def _moved_list(dataset):
    (surface,) = dataset.SurfaceSequence
    (primitives,) = surface.SurfaceMeshPrimitivesSequence
    primitives.LongEdgePointIndexList = primitives.LongTrianglePointIndexList
    del primitives.LongTrianglePointIndexList


def _split_mesh(dataset):
    dataset.SurfaceSequence = [_surface(), _surface(triangles=[])]


def _strip(dataset):
    (surface,) = dataset.SurfaceSequence
    (primitives,) = surface.SurfaceMeshPrimitivesSequence
    item = pydicom.Dataset()
    item.LongPrimitivePointIndexList = _indices([0, 1, 2])
    primitives.TriangleStripSequence = [item]


def _double(dataset):
    _double_points(dataset.SurfaceSequence[0])


@pytest.mark.parametrize(
    "change", [_changed_points, _moved_list, _split_mesh, _strip, _double]
)
def test_the_surfaces_digest_covers_every_point_and_primitive(change):
    dataset = _meshes()
    before = surface_data_sha256(dataset)
    change(dataset)

    assert surface_data_sha256(dataset) != before


def test_the_surfaces_digest_does_not_follow_what_draws_nothing():
    dataset = _meshes()
    before = surface_data_sha256(dataset)
    (surface,) = dataset.SurfaceSequence
    surface.SurfaceComments = "drawn by hand"
    surface.RecommendedDisplayGrayscaleValue = 0
    (primitives,) = surface.SurfaceMeshPrimitivesSequence
    # An empty list or sequence draws what an absent one does.
    primitives.LongEdgePointIndexList = b""
    primitives.LineSequence = []

    assert surface_data_sha256(dataset) == before


def test_no_meshes_have_one_digest():
    assert surface_data_sha256(pydicom.Dataset()) == NO_SURFACES
    assert NO_SURFACES.hex() == NO_SURFACES_SHA256
    empty = pydicom.Dataset()
    empty.SurfaceSequence = []
    assert surface_data_sha256(empty) == NO_SURFACES


def test_meshes_that_cannot_be_read_have_no_digest():
    dataset = _meshes()
    (surface,) = dataset.SurfaceSequence
    (item,) = surface.SurfacePointsSequence
    item.add_new(0x00660016, "OF", [1.0])
    item[0x00660016]._value = [1.0]

    with pytest.raises(ValueError, match="surface meshes cannot be read"):
        surface_data_sha256(dataset)


def test_the_written_surfaces_digest_is_left_out_where_they_are_not_shown():
    data = _segmentation()
    digests = run_qc._written_sha256

    shown = digests(data, False, False, False, True)
    assert shown["surface_sha256"] == surface_data_sha256(_read(data)).hex()
    assert shown["surface_sha256"] != NO_SURFACES_SHA256
    assert digests(data, False, False, False, False) == {
        **shown,
        "surface_sha256": None,
    }


# The pack and its reader.


def _sheet(position, meshes=1, listed=None, number=1):
    return Preview(
        f"P-{number:04d}.png",
        PreviewKind.SURFACE_MESHES,
        tuple(
            (position, mesh) for mesh in (range(meshes) if listed is None else listed)
        ),
        meshes,
        qc_previews.png(np.zeros((2, 2), np.uint8)),
    )


def _surfaced(position, digest="3f" * 32):
    entry = _released(position)
    return InstanceEntry(
        entry.position,
        entry.source,
        entry.disposition,
        output=entry.output,
        source_sha256=entry.source_sha256,
        surface_sha256=digest,
    )


def test_a_pack_records_surfaces_digest_only_where_a_sheet_shows_each_mesh():
    QcPack(REFERENCE, (_surfaced(0),), previews=(_sheet(0),))
    QcPack(REFERENCE, (_surfaced(0),), previews=(_sheet(0, meshes=2),))
    QcPack(REFERENCE, (_surfaced(0, NO_SURFACES_SHA256),))
    with pytest.raises(QcPackError, match="surfaces sheet that shows each mesh"):
        QcPack(REFERENCE, (_surfaced(0),))
    with pytest.raises(QcPackError, match="surfaces sheet that shows each mesh"):
        QcPack(REFERENCE, (_surfaced(0), _released(1)), previews=(_sheet(1),))


def test_a_surfaces_sheet_shows_each_mesh_of_one_instance_once():
    with pytest.raises(QcPackError, match="each mesh of one instance once"):
        QcPack(REFERENCE, (_surfaced(0),), previews=(_sheet(0, 2, [0]),))
    with pytest.raises(QcPackError, match="each mesh of one instance once"):
        QcPack(REFERENCE, (_surfaced(0),), previews=(_sheet(0, 2, [1, 2]),))
    with pytest.raises(QcPackError, match="each mesh of one instance once"):
        QcPack(
            REFERENCE,
            (_surfaced(0), _surfaced(1)),
            previews=(
                Preview(
                    "P-0001.png",
                    PreviewKind.SURFACE_MESHES,
                    ((0, 0), (1, 1)),
                    2,
                    qc_previews.png(np.zeros((2, 2), np.uint8)),
                ),
            ),
        )
    with pytest.raises(QcPackError, match="at most one surfaces sheet"):
        QcPack(REFERENCE, (_surfaced(0),), previews=(_sheet(0), _sheet(0, number=2)))


def test_a_pack_lists_surfaces_not_shown_without_a_sheet_or_a_digest():
    unshown = (NotPreviewedEntry(0, NotPreviewedReason.SURFACES_NOT_SHOWN),)
    QcPack(REFERENCE, (_surfaced(0, None),), not_previewed=unshown)
    with pytest.raises(QcPackError, match="neither a surfaces sheet"):
        QcPack(
            REFERENCE,
            (_surfaced(0, None),),
            previews=(_sheet(0),),
            not_previewed=unshown,
        )
    with pytest.raises(QcPackError, match="neither a surfaces sheet"):
        QcPack(REFERENCE, (_surfaced(0, NO_SURFACES_SHA256),), not_previewed=unshown)


def _document(surface_sha256="3f" * 32):
    return {
        "instances": [
            {
                "position": 0,
                "source_sha256": "0f" * 32,
                "pixel_sha256": None,
                "contour_sha256": None,
                "grid_sha256": None,
                "surface_sha256": surface_sha256,
                "reasons": [],
            }
        ],
        "series": [{"positions": [0]}],
        "previews": [],
        "not_previewed": [],
    }


def _files(document):
    return face_review._series_files(json.dumps(document).encode("ascii"))[0]


def test_the_reader_takes_a_surfaces_digest_only_where_a_sheet_shows_each_mesh():
    document = _document()
    with pytest.raises(QcPackError, match="not of its format"):
        _files(document)
    sheet = {
        "kind": PreviewKind.SURFACE_MESHES.value,
        "frames": [{"position": 0, "frame": 0}],
        "total_frames": 2,
    }
    document["previews"] = [sheet]
    with pytest.raises(QcPackError, match="not of its format"):
        _files(document)
    sheet["frames"].append({"position": 0, "frame": 1})
    ((entry,),) = tuple(_files(document).values())
    assert entry[8] == bytes.fromhex("3f" * 32) and not entry[3]
    # The digest of none needs no sheet.
    ((entry,),) = tuple(_files(_document(NO_SURFACES_SHA256)).values())
    assert entry[8] == NO_SURFACES


def test_the_reader_judges_no_file_by_meshes_it_lists_as_not_shown():
    document = _document(None)
    document["not_previewed"] = [{"position": 0, "reason": "surfaces-not-shown"}]

    ((entry,),) = tuple(_files(document).values())

    assert entry[8] is None and entry[3]


# A verdict on a Surface Segmentation.

_PIXELS = bytes.fromhex(NO_PIXELS_SHA256)
_CONTOURS = bytes.fromhex(NO_CONTOURS_SHA256)


def _review(surfaces):
    source = hashlib.sha256(b"source").digest()
    return source, FaceReview(
        REFERENCE,
        frozenset({source}),
        frozenset(),
        absent_pixels=frozenset({(source, _PIXELS)}),
        absent_contours=frozenset({(source, _CONTOURS)}),
        absent_surfaces=surfaces(source),
    )


def test_a_verdict_covers_only_the_meshes_that_the_pack_showed():
    shown = hashlib.sha256(b"shown").digest()
    source, review = _review(lambda source: frozenset({(source, shown)}))
    pixels, contours = _PIXELS, _CONTOURS

    assert review.hold_reason(source, pixels, contours, surfaces=shown) is None
    assert review.hold_reason(source, pixels, contours) is None
    other = VisualFeaturesReason.OTHER_SURFACES
    assert review.hold_reason(source, pixels, contours, surfaces=bytes(32)) is other
    assert review.hold_reason(source, pixels, contours, surfaces=None) is other
    # A review whose pack showed none of its meshes covers only a file
    # without any.
    source, review = _review(lambda source: frozenset())
    assert review.hold_reason(source, pixels, contours, surfaces=shown) is other
    assert review.hold_reason(source, pixels, contours, surfaces=NO_SURFACES) is None


def test_a_review_s_meshes_are_digests_of_files_marked_absent():
    source = hashlib.sha256(b"source").digest()
    with pytest.raises(QcPackError, match="grids, and surfaces"):
        FaceReview(
            REFERENCE,
            frozenset(),
            frozenset({source}),
            absent_surfaces=frozenset({(source, NO_SURFACES)}),
        )


# In a defaced CT series' Frame of Reference.


@pytest.mark.parametrize("iod", ["Surface Segmentation", "CT Image"])
def test_an_instance_with_meshes_in_a_defaced_frame_is_held_for_it(iod):
    transform = InstanceTransform(compose_policy("basic"), KEY, unvalidated_policy=True)
    data = _segmentation()
    record = InstanceRecord.from_file(data)
    iods = load_iod_tables().iods
    transform._defaced = face_blocks.Defaced(frozenset({files.FRAME}))

    held = transform._frame_hold(iods[iod], record, _read(data), None)

    assert held == HeldVisualFeatures(VisualFeaturesReason.UNDEFACED_IN_DEFACED_FRAME)
    # Nor is one in another frame held for it.
    elsewhere = _segmentation(frame=files.ROOT + ".8")
    assert (
        transform._frame_hold(
            iods[iod], InstanceRecord.from_file(elsewhere), _read(elsewhere), None
        )
        is None
    )
    assert "Surface Segmentation" in face_blocks.UNDEFACED_IODS
