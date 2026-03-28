"""Tests for OccupancyField (RFC section 6.8)."""

from __future__ import annotations

import numpy as np
import pytest

from pymedphys._dvh._types._grid_frame import GridFrame
from pymedphys._dvh._types._occupancy import OccupancyField
from pymedphys._dvh._types._roi_ref import ROIRef


class TestOccupancyFieldVolume:
    """D3: Numerical correctness of volume_cc."""

    def test_single_voxel_full_occupancy(self) -> None:
        """A 1 mm³ voxel with occupancy=1.0 should return 0.001 cc."""
        gf = GridFrame.from_uniform(
            shape_zyx=(1, 1, 1),
            spacing_mm_xyz=(1.0, 1.0, 1.0),
            origin_xyz_mm=(0.0, 0.0, 0.0),
        )
        data = np.ones((1, 1, 1), dtype=np.float64)
        occ = OccupancyField(data=data, frame=gf, roi=ROIRef(name="Test"))
        assert occ.volume_cc == pytest.approx(0.001)

    def test_single_voxel_half_occupancy(self) -> None:
        """A 1 mm³ voxel with occupancy=0.5 should return 0.0005 cc."""
        gf = GridFrame.from_uniform(
            shape_zyx=(1, 1, 1),
            spacing_mm_xyz=(1.0, 1.0, 1.0),
            origin_xyz_mm=(0.0, 0.0, 0.0),
        )
        data = np.full((1, 1, 1), 0.5, dtype=np.float64)
        occ = OccupancyField(data=data, frame=gf, roi=ROIRef(name="Test"))
        assert occ.volume_cc == pytest.approx(0.0005)

    def test_2mm_cube_full_occupancy(self) -> None:
        """A single 2×2×2 mm voxel = 8 mm³ = 0.008 cc."""
        gf = GridFrame.from_uniform(
            shape_zyx=(1, 1, 1),
            spacing_mm_xyz=(2.0, 2.0, 2.0),
            origin_xyz_mm=(0.0, 0.0, 0.0),
        )
        data = np.ones((1, 1, 1), dtype=np.float64)
        occ = OccupancyField(data=data, frame=gf, roi=ROIRef(name="Test"))
        assert occ.volume_cc == pytest.approx(0.008)

    def test_anisotropic_spacing(self) -> None:
        """2×3×5 mm voxel = 30 mm³ = 0.030 cc."""
        gf = GridFrame.from_uniform(
            shape_zyx=(1, 1, 1),
            spacing_mm_xyz=(2.0, 3.0, 5.0),
            origin_xyz_mm=(0.0, 0.0, 0.0),
        )
        data = np.ones((1, 1, 1), dtype=np.float64)
        occ = OccupancyField(data=data, frame=gf, roi=ROIRef(name="Test"))
        assert occ.volume_cc == pytest.approx(0.030)

    def test_multiple_voxels(self) -> None:
        """2×2×2 grid of 1mm³ voxels, all occupied = 8 × 0.001 = 0.008 cc."""
        gf = GridFrame.from_uniform(
            shape_zyx=(2, 2, 2),
            spacing_mm_xyz=(1.0, 1.0, 1.0),
            origin_xyz_mm=(0.0, 0.0, 0.0),
        )
        data = np.ones((2, 2, 2), dtype=np.float64)
        occ = OccupancyField(data=data, frame=gf, roi=ROIRef(name="Test"))
        assert occ.volume_cc == pytest.approx(0.008)
