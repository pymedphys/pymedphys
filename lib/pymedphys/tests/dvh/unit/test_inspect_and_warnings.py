# tests/dvh/integration/test_inspect_and_warnings.py
"""
Integration tests:
- Frame reconciliation via voxelisation alignment spot checks.
- Small-volume and few-slice warnings surfaced by inspect_structure().
"""

import numpy as np
import pytest

from pymedphys._dvh.api import inspect_structure
from pymedphys._dvh.types import DoseGrid, Structure3D, StructureContour


def _dose(dx=1.0, dy=1.0, dz=1.0, nz=12, ny=80, nx=80, ipp=(0.0, 0.0, 0.0)):
    values = np.zeros((nz, ny, nx), dtype=np.float32)
    orient = np.column_stack(
        [np.array([1, 0, 0.0]), np.array([0, 1, 0.0]), np.array([0, 0, 1.0])]
    ).astype(float)
    offsets = np.arange(nz, dtype=float) * dz
    return DoseGrid(
        values=values,
        origin_ipp_mm=np.array(ipp),
        orientation_matrix=orient,
        spacing_mm=(dx, dy, dz),
        frame_offsets_mm=offsets,
    )


def _disc(cx, cy, r, z, n=64):
    ang = np.linspace(0, 2 * np.pi, n, endpoint=False)
    x = cx + r * np.cos(ang)
    y = cy + r * np.sin(ang)
    zc = np.full_like(x, z)
    return np.stack([x, y, zc], axis=1)


def test_inspect_structure_emits_expected_warnings(caplog):
    dose = _dose(dz=1.0)
    s = Structure3D(name="Tiny", number=1)
    # Build ~0.3 cc sphere-like stack: 6 slices, radius shrinking
    # Approx radius for 0.3 cc sphere ~ 4.1 mm; we model 6 discs of radius ~3-5 mm
    zs = [2, 3, 4, 5, 6, 7]
    radii = [3.0, 4.0, 4.5, 4.0, 3.0, 2.0]
    for z, r in zip(zs, radii):
        s.add_ring(
            float(z), StructureContour.from_points(_disc(40.0, 40.0, r, float(z)))
        )

    with pytest.warns(UserWarning) as rec:
        info = inspect_structure(dose, s, endcaps="half_slice")

    messages = "\n".join(str(w.message) for w in rec)
    assert "only 6 axial slice" in messages  # <= 7 slices
    assert "volume is" in messages and "< 1 cc" in messages
    assert info["endcaps"] == "half_slice"


def test_voxel_alignment_spot_check():
    dose = _dose(dx=2.0, dy=2.0, dz=1.0, ny=20, nx=20, nz=4, ipp=(10.0, 20.0, 30.0))
    # Single square at z=31 mm (dose frame 1)
    s = Structure3D(name="Align", number=1)
    sq = np.array([[14, 24, 31], [22, 24, 31], [22, 32, 31], [14, 32, 31]], dtype=float)
    s.add_ring(31.0, StructureContour.from_points(sq))
    from pymedphys._dvh.geometry import voxelise_structure_right_prism

    mask, _ = voxelise_structure_right_prism(s, dose, endcaps="truncate")
    # The square spans x:[14,22], y:[24,32] on a 2 mm grid starting at (10,20)
    xs = np.arange(10, 10 + 2.0 * dose.shape[2], 2.0)
    ys = np.arange(20, 20 + 2.0 * dose.shape[1], 2.0)
    inside_x = (xs >= 14) & (xs < 22)
    inside_y = (ys >= 24) & (ys < 32)
    area_expected = inside_x.sum() * inside_y.sum()
    area_mask = mask[1].sum()  # z=31 mm maps to frame 1
    assert area_mask == area_expected
