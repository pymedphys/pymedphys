"""Diagnostic issue types (RFC section 6.9)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class IssueLevel(str, Enum):
    """Severity level for diagnostic issues."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class IssueCode(str, Enum):
    """Machine-parseable issue codes."""

    STRUCTURE_VOLUME_SMALL = "STRUCTURE_VOLUME_SMALL"
    DOSE_GRID_COARSE = "DOSE_GRID_COARSE"
    SPARSE_CONTOUR_STACK = "SPARSE_CONTOUR_STACK"
    STEEP_GRADIENT_BOUNDARY = "STEEP_GRADIENT_BOUNDARY"
    CONVERGENCE_NOT_REACHED = "CONVERGENCE_NOT_REACHED"
    ENDCAP_LARGE_FRACTION = "ENDCAP_LARGE_FRACTION"
    DOSE_COVERAGE_INCOMPLETE = "DOSE_COVERAGE_INCOMPLETE"
    CONTOUR_REPAIRED = "CONTOUR_REPAIRED"
    CONTOUR_STAGE_BYPASSED = "CONTOUR_STAGE_BYPASSED"
    ROI_SKIPPED = "ROI_SKIPPED"
    ROI_FAILED = "ROI_FAILED"
    METRIC_UNAVAILABLE = "METRIC_UNAVAILABLE"
    Z_TOLERANCE_APPLIED = "Z_TOLERANCE_APPLIED"


@dataclass(frozen=True, slots=True)
class Issue:
    """A structured diagnostic issue with source path.

    Parameters
    ----------
    level : IssueLevel
        Severity level.
    code : IssueCode
        Machine-parseable code.
    message : str
        Human-readable description.
    path : tuple[str, ...]
        Identifies the source (e.g. ``("PTV60", "D95%")``).
    context : dict[str, Any], optional
        Structured context data.
    """

    level: IssueLevel
    code: IssueCode
    message: str
    path: tuple[str, ...] = ()
    context: Optional[dict[str, Any]] = None
