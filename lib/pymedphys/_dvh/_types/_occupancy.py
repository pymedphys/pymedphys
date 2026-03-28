"""Occupancy field type (RFC section 6.8)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from pymedphys._dvh._types._grid_frame import GridFrame
from pymedphys._dvh._types._roi_ref import ROIRef


@dataclass(frozen=True, slots=True, eq=False)
class OccupancyField:
    """A 3D float array representing fractional voxel occupancy.

    Values are in [0.0, 1.0]. Shape is (nz, ny, nx) matching
    ``frame.shape_zyx``.

    Parameters
    ----------
    data : npt.NDArray[np.float64]
        Occupancy array, shape (nz, ny, nx).
    frame : GridFrame
        Spatial frame.
    roi : ROIRef
        Which ROI this occupancy field represents.
    """

    data: npt.NDArray[np.float64]
    frame: GridFrame
    roi: ROIRef

    def __post_init__(self) -> None:
        expected = self.frame.shape_zyx
        if self.data.shape != expected:
            raise ValueError(
                f"Occupancy shape {self.data.shape} != frame shape {expected}"
            )
        d = np.array(self.data, dtype=np.float64)
        d.flags.writeable = False
        object.__setattr__(self, "data", d)

    @property
    def volume_cc(self) -> float:
        """Total structure volume in cc (mm^3 / 1000)."""
        dz, dy, dx = self.frame.spacing_mm
        voxel_volume_mm3 = dx * dy * dz
        return float(np.sum(self.data)) * voxel_volume_mm3 / 1000.0

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, OccupancyField):
            return NotImplemented
        return (
            self.frame == other.frame
            and self.roi == other.roi
            and np.array_equal(self.data, other.data)
        )

    def __hash__(self) -> int:
        return hash((self.frame, self.roi.name, self.data.tobytes()))
