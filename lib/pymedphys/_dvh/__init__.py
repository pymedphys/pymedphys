"""PyMedPhys DVH Calculator.

A transparent, configurable DVH calculator with analytical benchmarks
and comprehensive validation.

Public API
----------
compute_dvh : callable
    Single entry point for DVH computation (not yet implemented).

All domain types are available via ``pymedphys._dvh._types``.
"""

from pymedphys._dvh._types import (
    AlgorithmConfig,
    ContourROI,
    DVHBins,
    DVHConfig,
    DVHInputs,
    DVHResultSet,
    DoseGrid,
    DoseReference,
    DoseReferenceSet,
    GridFrame,
    MetricRequestSet,
    MetricResult,
    MetricSpec,
    ROIRef,
    ROIResult,
)

__all__ = [
    "AlgorithmConfig",
    "ContourROI",
    "DVHBins",
    "DVHConfig",
    "DVHInputs",
    "DVHResultSet",
    "DoseGrid",
    "DoseReference",
    "DoseReferenceSet",
    "GridFrame",
    "MetricRequestSet",
    "MetricResult",
    "MetricSpec",
    "ROIRef",
    "ROIResult",
]
