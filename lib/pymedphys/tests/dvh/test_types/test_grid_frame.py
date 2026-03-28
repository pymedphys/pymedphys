"""Tests for GridFrame (RFC section 6.2)."""

from __future__ import annotations

import numpy as np
import pytest

from pymedphys._dvh._types._grid_frame import GridFrame


class TestGridFrameFromUniform:
    """Tests for the from_uniform() convenience constructor."""

    def test_constructs_correct_affine(self) -> None:
        gf = GridFrame.from_uniform(
            shape_zyx=(10, 20, 30),
            spacing_xyz_mm=(2.5, 3.0, 1.5),
            origin_xyz_mm=(-10.0, -20.0, -30.0),
        )
        expected = np.array(
            [
                [0, 0, 2.5, -10.0],
                [0, 3.0, 0, -20.0],
                [1.5, 0, 0, -30.0],
                [0, 0, 0, 1],
            ],
            dtype=np.float64,
        )
        np.testing.assert_array_equal(gf.index_to_patient_mm, expected)

    def test_spacing_mm_returns_zyx_order(self) -> None:
        gf = GridFrame.from_uniform(
            shape_zyx=(10, 20, 30),
            spacing_xyz_mm=(2.5, 3.0, 1.5),
            origin_xyz_mm=(0.0, 0.0, 0.0),
        )
        dz, dy, dx = gf.spacing_mm
        assert dx == pytest.approx(2.5)
        assert dy == pytest.approx(3.0)
        assert dz == pytest.approx(1.5)

    def test_spacing_xyz_mm_returns_xyz_order(self) -> None:
        gf = GridFrame.from_uniform(
            shape_zyx=(10, 20, 30),
            spacing_xyz_mm=(2.5, 3.0, 1.5),
            origin_xyz_mm=(0.0, 0.0, 0.0),
        )
        dx, dy, dz = gf.spacing_xyz_mm
        assert dx == pytest.approx(2.5)
        assert dy == pytest.approx(3.0)
        assert dz == pytest.approx(1.5)

    def test_origin_mm_returns_xyz(self) -> None:
        gf = GridFrame.from_uniform(
            shape_zyx=(5, 5, 5),
            spacing_xyz_mm=(1.0, 1.0, 1.0),
            origin_xyz_mm=(-10.0, -20.0, -30.0),
        )
        ox, oy, oz = gf.origin_mm
        assert ox == pytest.approx(-10.0)
        assert oy == pytest.approx(-20.0)
        assert oz == pytest.approx(-30.0)

    def test_num_voxels(self) -> None:
        gf = GridFrame.from_uniform(
            shape_zyx=(10, 20, 30),
            spacing_xyz_mm=(1.0, 1.0, 1.0),
            origin_xyz_mm=(0.0, 0.0, 0.0),
        )
        assert gf.num_voxels == 10 * 20 * 30


class TestGridFrameValidation:
    """Tests for construction-time validation."""

    def test_rejects_zero_shape_element(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            GridFrame.from_uniform(
                shape_zyx=(0, 20, 30),
                spacing_xyz_mm=(1.0, 1.0, 1.0),
                origin_xyz_mm=(0.0, 0.0, 0.0),
            )

    def test_rejects_negative_shape_element(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            GridFrame.from_uniform(
                shape_zyx=(10, -5, 30),
                spacing_xyz_mm=(1.0, 1.0, 1.0),
                origin_xyz_mm=(0.0, 0.0, 0.0),
            )

    def test_rejects_non_4x4_affine(self) -> None:
        with pytest.raises(ValueError, match="4, 4"):
            GridFrame(
                shape_zyx=(10, 20, 30),
                index_to_patient_mm=np.eye(3),
            )

    def test_rejects_zero_spacing(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            GridFrame.from_uniform(
                shape_zyx=(10, 20, 30),
                spacing_xyz_mm=(0.0, 1.0, 1.0),
                origin_xyz_mm=(0.0, 0.0, 0.0),
            )


class TestGridFrameImmutability:
    """Tests for defensive copying and read-only arrays."""

    def test_affine_is_read_only(self) -> None:
        gf = GridFrame.from_uniform(
            shape_zyx=(5, 5, 5),
            spacing_xyz_mm=(1.0, 1.0, 1.0),
            origin_xyz_mm=(0.0, 0.0, 0.0),
        )
        with pytest.raises(ValueError, match="read-only"):
            gf.index_to_patient_mm[0, 0] = 999.0

    def test_affine_is_defensive_copy(self) -> None:
        aff = np.array(
            [
                [0, 0, 1.0, 0],
                [0, 1.0, 0, 0],
                [1.0, 0, 0, 0],
                [0, 0, 0, 1],
            ],
            dtype=np.float64,
        )
        gf = GridFrame(shape_zyx=(5, 5, 5), index_to_patient_mm=aff)
        aff[0, 0] = 999.0
        assert gf.index_to_patient_mm[0, 0] != 999.0


class TestGridFrameEquality:
    """Tests for __eq__ and __hash__."""

    def test_equal_frames_are_equal(self) -> None:
        gf1 = GridFrame.from_uniform(
            shape_zyx=(10, 20, 30),
            spacing_xyz_mm=(1.0, 2.0, 3.0),
            origin_xyz_mm=(0.0, 0.0, 0.0),
        )
        gf2 = GridFrame.from_uniform(
            shape_zyx=(10, 20, 30),
            spacing_xyz_mm=(1.0, 2.0, 3.0),
            origin_xyz_mm=(0.0, 0.0, 0.0),
        )
        assert gf1 == gf2

    def test_different_frames_are_not_equal(self) -> None:
        gf1 = GridFrame.from_uniform(
            shape_zyx=(10, 20, 30),
            spacing_xyz_mm=(1.0, 2.0, 3.0),
            origin_xyz_mm=(0.0, 0.0, 0.0),
        )
        gf2 = GridFrame.from_uniform(
            shape_zyx=(10, 20, 30),
            spacing_xyz_mm=(1.0, 2.0, 3.0),
            origin_xyz_mm=(1.0, 0.0, 0.0),
        )
        assert gf1 != gf2

    def test_hash_consistent_with_eq(self) -> None:
        gf1 = GridFrame.from_uniform(
            shape_zyx=(10, 20, 30),
            spacing_xyz_mm=(1.0, 2.0, 3.0),
            origin_xyz_mm=(0.0, 0.0, 0.0),
        )
        gf2 = GridFrame.from_uniform(
            shape_zyx=(10, 20, 30),
            spacing_xyz_mm=(1.0, 2.0, 3.0),
            origin_xyz_mm=(0.0, 0.0, 0.0),
        )
        assert hash(gf1) == hash(gf2)

    def test_can_be_used_in_set(self) -> None:
        gf1 = GridFrame.from_uniform(
            shape_zyx=(5, 5, 5),
            spacing_xyz_mm=(1.0, 1.0, 1.0),
            origin_xyz_mm=(0.0, 0.0, 0.0),
        )
        gf2 = GridFrame.from_uniform(
            shape_zyx=(5, 5, 5),
            spacing_xyz_mm=(1.0, 1.0, 1.0),
            origin_xyz_mm=(0.0, 0.0, 0.0),
        )
        assert len({gf1, gf2}) == 1
