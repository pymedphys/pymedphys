"""DVH input bundle (RFC section 6.10)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from pymedphys._dvh._types._contour import ContourROI
from pymedphys._dvh._types._dose import DoseGrid


@dataclass(frozen=True, slots=True)
class DVHInputs:
    """Typed input bundle for DVH computation.

    Construct directly by providing a ``DoseGrid`` and
    ``ContourROI`` tuple. Named constructors for DICOM and
    raw-array input pathways are planned for later phases.

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
