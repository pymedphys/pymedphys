import numpy as np
import pytest
from pydicom.dataset import Dataset

from pymedphys._dvh.rtstruct_utils import rois_from_rtstruct, is_inside_polygon


def make_dummy_rtstruct():
    ds = Dataset()
    ds.Modality = "RTSTRUCT"

    # 1) StructureSetROISequence
    ssr = Dataset()
    ssr.ROINumber = 10
    ssr.ROIName = "ROI10"
    ds.StructureSetROISequence = [ssr]

    # 2) RTROIObservationsSequence
    obs = Dataset()
    obs.ReferencedROINumber = 10
    obs.RTROIInterpretedType = "ORGAN"
    ds.RTROIObservationsSequence = [obs]

    # 3) ROIContourSequence with one simple triangle at z=1.0
    rc = Dataset()
    rc.ReferencedROINumber = 10
    c = Dataset()
    c.ContourData = [0.0, 0.0, 1.0, 2.0, 0.0, 1.0, 0.0, 2.0, 1.0]
    rc.ContourSequence = [c]
    ds.ROIContourSequence = [rc]

    return ds


def test_rois_from_rtstruct_minimal():
    ds = make_dummy_rtstruct()
    rois = rois_from_rtstruct(ds)

    # Keyed by string ROI number
    assert "10" in rois

    roi = rois["10"]
    assert roi["Name"] == "ROI10"
    assert roi["Type"] == "ORGAN"
    assert roi["Colour"] == "Unspecified"

    # Check Contours dict
    contours = roi["Contours"]
    assert "1.0" in contours
    np.testing.assert_allclose(
        contours["1.0"], np.array([[0.0, 0.0], [2.0, 0.0], [0.0, 2.0]])
    )

    # Check Vertices stack
    verts = roi["Vertices"]
    assert verts.shape == (3, 3)
    np.testing.assert_allclose(
        verts, np.array([[0.0, 0.0, 1.0], [2.0, 0.0, 1.0], [0.0, 2.0, 1.0]])
    )


def inside(polygon, point, include_edges=True):
    """
    Helper to call the (potentially njit-decorated) function
    without JIT overhead in tests.
    """
    try:
        fn = is_inside_polygon.py_func
    except AttributeError:
        fn = is_inside_polygon
    return fn(np.array(polygon, dtype=float), point, include_edges)


#
# Define some canonical polygons (each closed by repeating the first vertex)
#
square = [(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)]
triangle = [(0, 0), (2, 0), (0, 2), (0, 0)]
concave = [(0, 0), (2, 1), (0, 2), (1, 1), (0, 0)]
horiz = [(0, 0), (2, 0), (2, 2), (0, 2), (0, 0)]
collinear = [(0, 0), (1, 0), (2, 0), (2, 2), (0, 2), (0, 0)]


#
# 1) Square
#
@pytest.mark.parametrize(
    "pt,edge_in,edge_out",
    [
        # strictly inside
        ((0.5, 0.5), True, True),
        # strictly outside
        ((-1, 0.5), False, False),
        ((1.5, 0.5), False, False),
        ((0.5, -0.1), False, False),
        ((0.5, 1.1), False, False),
        # on edges / vertices
        ((1, 0.5), True, False),  # right edge
        ((0.5, 0), True, False),  # bottom edge
        ((0, 1), True, False),  # top-left vertex
        ((0, 0), True, False),  # bottom-left vertex
    ],
)
def test_square(pt, edge_in, edge_out):
    assert inside(square, pt) == edge_in
    assert inside(square, pt, include_edges=False) == edge_out


#
# 2) Right triangle
#
@pytest.mark.parametrize(
    "pt, edge_in, edge_out",
    [
        ((0.5, 0.5), True, True),  # inside
        ((1, 0), True, False),  # on base midpoint
        ((1, 1), True, False),  # on hypotenuse
        ((0, 1), True, False),  # on left edge
        ((2, 1), False, False),  # outside
    ],
)
def test_triangle(pt, edge_in, edge_out):
    assert inside(triangle, pt) == edge_in
    assert inside(triangle, pt, include_edges=False) == edge_out


#
# 3) Concave “arrow” shape
#
@pytest.mark.parametrize(
    "pt, edge_in, edge_out",
    [
        ((0.5, 1), False, False),  # between wings
        ((1.5, 1), True, True),  # in arrow
        ((2, 1), True, False),  # on arrow tip
        ((1, 1.5), True, False),  # on top-edge
    ],
)
def test_concave(pt, edge_in, edge_out):
    assert inside(concave, pt) == edge_in
    assert inside(concave, pt, include_edges=False) == edge_out


#
# 4) Horizontal edges
#
@pytest.mark.parametrize(
    "pt,edge_in,edge_out",
    [
        ((1, 0), True, False),  # on bottom edge
        ((1, 2), True, False),  # on top edge
        ((-0.1, 0), False, False),
        ((2.1, 2), False, False),
    ],
)
def test_horizontal_edges(pt, edge_in, edge_out):
    assert inside(horiz, pt) == edge_in
    assert inside(horiz, pt, include_edges=False) == edge_out


#
# 5) Collinear‐vertex polygon
#
@pytest.mark.parametrize(
    "pt, edge_in, edge_out",
    [
        ((1.5, 0), True, False),  # on the bottom edge
        ((1.5, 1), True, True),  # strictly inside
        ((3, 0), False, False),  # outside
    ],
)
def test_collinear_vertices(pt, edge_in, edge_out):
    assert inside(collinear, pt) == edge_in
    assert inside(collinear, pt, include_edges=False) == edge_out


#
# 6) (Optional) Fuzzy compare against Shapely if you have it installed
#
def test_random_against_shapely():
    pytest.skip("Uncomment and install Shapely to run a randomized cross-check")
