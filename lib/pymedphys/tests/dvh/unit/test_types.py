# tests/dvh/unit/test_types.py
import numpy as np

from pymedphys._dvh.types import DoseGrid, Structure3D, StructureContour


def test_dosegrid_index_to_world_roundtrip():
    # 2 frames, 2x3 grid; axial orientation; PS=(dy=2, dx=3); offsets=[0, 5]
    values = np.zeros((2, 2, 3), dtype=np.float32)
    ipp = np.array([10.0, 20.0, 30.0], dtype=float)
    # IOP row=(1,0,0), col=(0,1,0) → normal=(0,0,1)
    orient = np.column_stack(
        [np.array([1, 0, 0.0]), np.array([0, 1, 0.0]), np.array([0, 0, 1.0])]
    ).astype(float)
    spacing = (3.0, 2.0, 5.0)
    offsets = np.array([0.0, 5.0], dtype=float)

    dg = DoseGrid(
        values=values,
        origin_ipp_mm=ipp,
        orientation_matrix=orient,
        spacing_mm=spacing,
        frame_offsets_mm=offsets,
    )

    # (0,0,0) maps to IPP
    p000 = dg.index_to_world(0, 0, 0)
    assert np.allclose(p000, ipp)

    # +x increases 3 mm along row direction
    p001 = dg.index_to_world(0, 0, 1)
    assert np.allclose(p001, ipp + np.array([3.0, 0.0, 0.0]))

    # +y increases 2 mm along col direction
    p010 = dg.index_to_world(0, 1, 0)
    assert np.allclose(p010, ipp + np.array([0.0, 2.0, 0.0]))

    # Next frame: +5 mm along normal
    p100 = dg.index_to_world(1, 0, 0)
    assert np.allclose(p100, ipp + np.array([0.0, 0.0, 5.0]))

    # Round-trip a random world point inside the grid
    world = dg.index_to_world(1, 1, 2)
    frac_z, frac_y, frac_x = dg.world_to_index(world)
    assert np.isclose(frac_z, 1.0)
    assert np.isclose(frac_y, 1.0)
    assert np.isclose(frac_x, 2.0)


def test_structure3d_add_and_bbox():
    # Two squares on z=0 and z=5
    sq0 = np.array([[0, 0, 0], [10, 0, 0], [10, 10, 0], [0, 10, 0]], dtype=float)
    sq1 = np.array([[1, 1, 5], [9, 1, 5], [9, 9, 5], [1, 9, 5]], dtype=float)

    r0 = StructureContour.from_points(sq0)
    r1 = StructureContour.from_points(sq1)

    s = Structure3D(name="PTV66", number=1)
    s.add_ring(r0.z_mm, r0)
    s.add_ring(r1.z_mm, r1)

    zs = s.plane_zs()
    assert np.allclose(zs, [0.0, 5.0])
    assert s.num_contours() == 2

    bb_min, bb_max = s.bounding_box_mm()
    assert np.allclose(bb_min, [0.0, 0.0, 0.0])
    assert np.allclose(bb_max, [10.0, 10.0, 5.0])
