"""DVH input bundle (RFC section 6.10)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy.typing as npt

from pymedphys._dvh._types._contour import ContourROI
from pymedphys._dvh._types._dose import DoseGrid
from pymedphys._dvh._types._grid_frame import GridFrame


@dataclass(frozen=True, slots=True)
class DVHInputs:
    """Typed input bundle for DVH computation.

    Use the named constructors to build inputs from DICOM paths
    or raw NumPy arrays.

    Parameters
    ----------
    dose : DoseGrid
        Dose distribution.
    structures : tuple[ContourROI, ...]
        ROI contour data.
    rtstruct_path : str, optional
        Path to DICOM RTSTRUCT file (for provenance).
    rtdose_path : str, optional
        Path to DICOM RTDOSE file (for provenance).
    """

    dose: DoseGrid
    structures: tuple[ContourROI, ...]
    rtstruct_path: str | None = None
    rtdose_path: str | None = None

    @classmethod
    def from_dicom(
        cls,
        rtstruct_path: str,
        rtdose_path: str,
        roi_names: list[str] | None = None,
        # TODO (Phase 4): policy should be PipelinePolicy, not object
        policy: object | None = None,
    ) -> DVHInputs:
        """Load from DICOM RTSTRUCT + RTDOSE files.

        Not yet implemented — requires Phase 4.
        """
        raise NotImplementedError(
            "DVHInputs.from_dicom() is not yet implemented (Phase 4)"
        )

    @classmethod
    def from_arrays(
        cls,
        # TODO (Phase 4): dose_gy should be npt.NDArray[np.float64]
        dose_gy: npt.ArrayLike,
        # TODO (Phase 4): structures should be dict[str, ContourROI]
        structures: dict[str, object],
        # TODO (Phase 4): frame should be GridFrame
        frame: GridFrame | object,
    ) -> DVHInputs:
        """Build from raw NumPy arrays.

        Not yet implemented — requires Phase 4.
        """
        raise NotImplementedError(
            "DVHInputs.from_arrays() is not yet implemented (Phase 4)"
        )
