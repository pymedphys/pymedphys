"""PyMedPhys DVH Calculator — domain types and configuration.

Provides the domain type system for DVH computation: grid frames,
dose grids, ROI references, contour geometry, metric specifications,
configuration profiles, and result types.

The ``compute_dvh`` entry point and DICOM I/O are not yet
implemented; they are planned for later phases. Currently only
the type model, metric grammar, serialisation, and analytical
benchmark volume formulas are available.
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
    MetricSpec,
    ROIRef,
)
from pymedphys._dvh._types._results import MetricResult, ROIResult

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
