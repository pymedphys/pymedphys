"""PyMedPhys DVH Module — Phase 0: Type Layer.

Provides typed domain objects, metric/request grammar, configuration,
serialisation, and result containers for DVH computation.

Computation entry points will be added in later phases.
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
