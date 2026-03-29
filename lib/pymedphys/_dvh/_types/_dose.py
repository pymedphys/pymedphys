"""Dose grid type (RFC section 6.8)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from pymedphys._dvh._types._grid_frame import GridFrame
from pymedphys._dvh._types._validators import validate_finite_array


@dataclass(frozen=True, slots=True, eq=False)
class DoseGrid:
    """A 3D dose array on a regular grid with explicit axis contract.

    The array ``dose_gy`` has shape (nz, ny, nx) matching
    ``frame.shape_zyx``. Values are in Gy.

    Parameters
    ----------
    dose_gy : npt.NDArray[np.float64]
        3D dose array, shape (nz, ny, nx).
    frame : GridFrame
        Spatial frame defining grid coordinates.
    uncertainty_gy : npt.NDArray[np.float64], optional
        Per-voxel dose uncertainty (same shape as dose_gy).
    """

    dose_gy: npt.NDArray[np.float64]
    frame: GridFrame
    uncertainty_gy: npt.NDArray[np.float64] | None = None

    def __post_init__(self) -> None:
        expected = self.frame.shape_zyx
        if self.dose_gy.shape != expected:
            raise ValueError(
                f"Dose shape {self.dose_gy.shape} != frame shape {expected}"
            )
        d = np.array(self.dose_gy, dtype=np.float64)
        validate_finite_array("DoseGrid.dose_gy", d, ndim=3)
        d.flags.writeable = False
        object.__setattr__(self, "dose_gy", d)
        if self.uncertainty_gy is not None:
            if self.uncertainty_gy.shape != expected:
                raise ValueError("Uncertainty shape must match dose shape")
            u = np.array(self.uncertainty_gy, dtype=np.float64)
            validate_finite_array("DoseGrid.uncertainty_gy", u, ndim=3)
            u.flags.writeable = False
            object.__setattr__(self, "uncertainty_gy", u)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, DoseGrid):
            return NotImplemented
        return self.frame == other.frame and np.array_equal(self.dose_gy, other.dose_gy)

    def __hash__(self) -> int:
        return hash((self.frame, self.dose_gy.tobytes()))
