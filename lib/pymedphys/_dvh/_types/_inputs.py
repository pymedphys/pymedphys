"""DVH input bundle (RFC section 6.10)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from pymedphys._dvh._types._contour import ContourROI
from pymedphys._dvh._types._dose import DoseGrid


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
    rtstruct_path: Optional[str] = None
    rtdose_path: Optional[str] = None

    @classmethod
    def from_dicom(
        cls,
        rtstruct_path: str,
        rtdose_path: str,
        roi_names: Optional[list[str]] = None,
        policy: Optional[object] = None,
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
        dose_gy: object,
        structures: dict[str, object],
        frame: object,
    ) -> DVHInputs:
        """Build from raw NumPy arrays.

        Not yet implemented — requires Phase 4.
        """
        raise NotImplementedError(
            "DVHInputs.from_arrays() is not yet implemented (Phase 4)"
        )
