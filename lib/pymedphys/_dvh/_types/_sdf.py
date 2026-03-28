"""Signed distance field type (RFC section 6.11)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from pymedphys._dvh._types._grid_frame import GridFrame
from pymedphys._dvh._types._roi_ref import ROIRef


@dataclass(frozen=True, slots=True, eq=False)
class SDFField:
    """A 3D signed distance field on a regular grid.

    Values represent the signed distance to the structure boundary:
    negative inside, positive outside, zero on the boundary.

    Shape is (nz, ny, nx) matching ``frame.shape_zyx``.

    Parameters
    ----------
    data : npt.NDArray[np.float64]
        SDF array, shape (nz, ny, nx). All values must be finite.
    frame : GridFrame
        Spatial frame.
    roi : ROIRef
        Which ROI this SDF represents.
    """

    data: npt.NDArray[np.float64]
    frame: GridFrame
    roi: ROIRef

    def __post_init__(self) -> None:
        expected = self.frame.shape_zyx
        if self.data.shape != expected:
            raise ValueError(f"SDF shape {self.data.shape} != frame shape {expected}")
        d = np.array(self.data, dtype=np.float64)
        d.flags.writeable = False
        object.__setattr__(self, "data", d)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SDFField):
            return NotImplemented
        return (
            self.frame == other.frame
            and self.roi == other.roi
            and np.array_equal(self.data, other.data)
        )

    def __hash__(self) -> int:
        return hash((self.frame, self.roi.name, self.data.tobytes()))
