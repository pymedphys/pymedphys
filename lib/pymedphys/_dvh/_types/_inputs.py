"""DVH input bundle (RFC section 6.10)."""

from __future__ import annotations

from dataclasses import dataclass

from pymedphys._dvh._types._contour import ContourROI
from pymedphys._dvh._types._dose import DoseGrid


@dataclass(frozen=True, slots=True)
class DVHInputs:
    """Typed input bundle for DVH computation.

    Construction from DICOM files or raw arrays will be added in a
    later phase. For now, build instances directly.

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

    def __post_init__(self) -> None:
        if isinstance(self.structures, list):
            object.__setattr__(self, "structures", tuple(self.structures))
