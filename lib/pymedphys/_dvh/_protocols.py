"""Strategy protocols for the DVH engine (RFC section 6.11).

These are private extension points for algorithmic choices.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np
import numpy.typing as npt

from pymedphys._dvh._types._config import AlgorithmConfig
from pymedphys._dvh._types._contour import ContourROI
from pymedphys._dvh._types._dose import DoseGrid
from pymedphys._dvh._types._grid_frame import GridFrame
from pymedphys._dvh._types._occupancy import OccupancyField
from pymedphys._dvh._types._sdf import SDFField


@runtime_checkable
class StructureModelBuilder(Protocol):
    """Builds a continuous 3D structure model from a ContourROI."""

    def build(
        self,
        contour_roi: ContourROI,
        config: AlgorithmConfig,
    ) -> SDFField: ...


@runtime_checkable
class OccupancyComputer(Protocol):
    """Computes fractional voxel occupancy from a structure model."""

    def compute(
        self,
        structure_sdf: SDFField,
        target_frame: GridFrame,
        config: AlgorithmConfig,
    ) -> OccupancyField: ...


@runtime_checkable
class DoseInterpolator(Protocol):
    """Interpolates dose at arbitrary points."""

    def evaluate(
        self,
        dose: DoseGrid,
        points_xyz: npt.NDArray[np.float64],
    ) -> npt.NDArray[np.float64]: ...
