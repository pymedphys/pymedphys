# tests/dvh/unit/test_endcaps_and_geomtry.py
import numpy as np

from pymedphys._dvh.geometry import mask_volume_cc, voxelise_structure_right_prism
from pymedphys._dvh.types import DoseGrid, Structure3D, StructureContour


def _make_dose(nz=8, ny=80, nx=80, dx=0.5, dy=0.5, dz=0.5, ipp=(-20.0, -20.0, 0.0)):
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


def test_right_prism_uses_lower_plane_in_slab():
    # Two squares: big at z=0, small at z=2
    s = Structure3D(name="TEST", number=1)
    big = np.array([[-5, -5, 0], [5, -5, 0], [5, 5, 0], [-5, 5, 0]], dtype=float)
    small = np.array([[-2, -2, 2], [2, -2, 2], [2, 2, 2], [-2, 2, 2]], dtype=float)
    s.add_ring(0.0, StructureContour.from_points(big))
    s.add_ring(2.0, StructureContour.from_points(small))

    dose = _make_dose(nz=6, dz=1.0, ipp=(-20.0, -20.0, 0.0))  # z at 0,1,2,3,4,5 mm

    mask_trunc, meta = voxelise_structure_right_prism(s, dose, endcaps="truncate")
    # z in [0,2): frames 0 and 1 should use the big square
    area0 = mask_trunc[0].sum()
    area1 = mask_trunc[1].sum()
    area2 = mask_trunc[2].sum()  # slab [2,3) uses small square
    assert area0 == area1
    assert area2 < area1  # smaller


def test_half_slice_endcaps_nonuniform():
    # Three identical squares at z=0,1,3 -> spacings 1 and 2 mm => half-caps 0.5 and 1.0
    s = Structure3D(name="TEST", number=1)
    sq0 = np.array([[-5, -5, 0], [5, -5, 0], [5, 5, 0], [-5, 5, 0]], dtype=float)
    for z in (0.0, 1.0, 3.0):
        s.add_ring(z, StructureContour.from_points(sq0.copy()))

    dose = _make_dose(
        nz=8, dz=0.5, ipp=(-20.0, -20.0, 0.0)
    )  # fine z sampling; ROI fully inside grid

    mask_half, _ = voxelise_structure_right_prism(s, dose, endcaps="half_slice")
    vol_cc = mask_volume_cc(mask_half, dose)
    # Analytic volume: area * (slabs + caps)
    area = 10.0 * 10.0  # mm^2
    slabs_mm = 3.0  # [0,1) + [1,3) = 1 + 2
    caps_mm = 1.5  # inferior 0.5 + superior 1.0
    vol_true_cc = (area * (slabs_mm + caps_mm)) / 1000.0
    # Allow up to half a slice of area as tolerance (discrete sampling at 0.5 mm)
    assert abs(vol_cc - vol_true_cc) <= (0.5 * area) / 1000.0
