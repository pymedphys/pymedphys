"""Tests for SDFField (RFC section 6.11)."""

from __future__ import annotations

import numpy as np
import pytest

from pymedphys._dvh._types._grid_frame import GridFrame
from pymedphys._dvh._types._roi_ref import ROIRef
from pymedphys._dvh._types._sdf import SDFField


class TestSDFFieldValidation:
    """A3: SDFField must reject non-finite values."""

    def _make_frame(self) -> GridFrame:
        return GridFrame.from_uniform(
            shape_zyx=(1, 1, 1),
            spacing_mm_xyz=(1.0, 1.0, 1.0),
        )

    def test_rejects_nan(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            SDFField(
                data=np.array([[[np.nan]]]),
                frame=self._make_frame(),
                roi=ROIRef(name="Test"),
            )

    def test_rejects_positive_inf(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            SDFField(
                data=np.array([[[np.inf]]]),
                frame=self._make_frame(),
                roi=ROIRef(name="Test"),
            )

    def test_rejects_negative_inf(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            SDFField(
                data=np.array([[[-np.inf]]]),
                frame=self._make_frame(),
                roi=ROIRef(name="Test"),
            )

    def test_accepts_finite_values(self) -> None:
        sdf = SDFField(
            data=np.array([[[-1.5]]]),
            frame=self._make_frame(),
            roi=ROIRef(name="Test"),
        )
        assert sdf.data[0, 0, 0] == -1.5
