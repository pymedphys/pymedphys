import numpy as np

from pymedphys._dvh.raster import polygon_to_mask


def test_polygon_to_mask_center_pixel_only():
    # a triangle that only covers the center pixel of a 3×3 grid
    poly = np.array([[0.5, 0.5], [2.5, 0.5], [0.5, 2.5], [0.5, 0.5]], dtype=np.float64)

    shape = (3, 3)
    origin = (0.0, 0.0)
    spacing = (1.0, 1.0)

    mask_edge_excluded = polygon_to_mask(
        poly, shape, origin, spacing, include_edges=False
    )
    mask_edge_included = polygon_to_mask(
        poly, shape, origin, spacing, include_edges=True
    )
    assert mask_edge_excluded.shape == shape
    assert mask_edge_included.shape == shape

    for j in range(3):
        for i in range(3):
            if (i, j) == (1, 1):
                assert mask_edge_excluded[
                    j, i
                ], f"Expected center pixel inside at {(i,j)}"
            elif (i, j) in ((2, 1), (1, 2)):
                assert not mask_edge_excluded[j, i], f"Expected {(i,j)} outside"
                assert mask_edge_included[j, i], f"Expected {(i,j)} outside"
            else:
                assert not mask_edge_excluded[j, i], f"Expected {(i,j)} outside"
                assert not mask_edge_included[j, i], f"Expected {(i,j)} outside"
