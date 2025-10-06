# lib/pymedphys/tests/dvh/test_polygons_with_holes.py
import numpy as np

from pymedphys._dvh.config import DVHConfig
from pymedphys._dvh.dicom_io import ROI, Contour2D, DoseGridGeom
from pymedphys._dvh.geometry.voxelise import voxelise_roi_to_mask


def _simple_geom(K=1, R=32, C=32, ps=1.0):
    ipp = np.array([0.0, 0.0, 0.0], dtype=float)
    u = np.array([1.0, 0.0, 0.0], dtype=float)  # row
    v = np.array([0.0, 1.0, 0.0], dtype=float)  # col
    w = np.array([0.0, 0.0, 1.0], dtype=float)  # slice
    gfo = np.array([0.0] if K == 1 else np.arange(K, dtype=float), dtype=float)
    return DoseGridGeom(
        ipp=ipp, u=u, v=v, w=w, ps_row=ps, ps_col=ps, gfo=gfo, shape=(K, R, C)
    )


def test_even_odd_holes_supported():
    geom = _simple_geom()
    # R = C = 64

    # One slice, outer square and inner square hole
    outer = np.array([[16, 16], [16, 48], [48, 48], [48, 16], [16, 16]], dtype=float)
    inner = np.array([[28, 28], [28, 36], [36, 36], [36, 28], [28, 28]], dtype=float)

    roi = ROI(
        name="outer_minus_inner",
        number=1,
        contours=[Contour2D(z_mm=0.0, points_rc=[outer, inner])],
    )

    cfg = DVHConfig(inplane_supersample=4)

    mask = voxelise_roi_to_mask(roi, geom, cfg)
    assert mask.shape == (1, geom.shape[1], geom.shape[2])

    # Centre should be in the hole => 0, corners inside outer => >0, outside => 0
    centre_rc = (32, 32)
    assert mask[0, centre_rc[0], centre_rc[1]] == 0.0

    corner_inside = (20, 20)
    assert mask[0, corner_inside[0], corner_inside[1]] > 0.0

    outside = (8, 8)
    assert mask[0, outside[0], outside[1]] == 0.0
