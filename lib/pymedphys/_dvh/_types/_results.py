"""Result types (RFC section 6.9)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import FrozenSet, Literal, Optional

import numpy as np
import numpy.typing as npt

from pymedphys._dvh._types._config import DVHConfig
from pymedphys._dvh._types._dose_ref import DoseReferenceSet
from pymedphys._dvh._types._grid_frame import GridFrame
from pymedphys._dvh._types._issues import Issue
from pymedphys._dvh._types._metrics import MetricSpec
from pymedphys._dvh._types._roi_ref import ROIRef


@dataclass(frozen=True, slots=True, eq=False)
class DVHBins:
    """Canonical DVH storage: dose bin edges + differential volume.

    ``dose_bin_edges_gy`` has length N+1 for N bins.
    ``differential_volume_cc`` has length N.

    Parameters
    ----------
    dose_bin_edges_gy : npt.NDArray[np.float64]
        Bin edges in Gy, length N+1.
    differential_volume_cc : npt.NDArray[np.float64]
        Differential volume per bin in cc, length N.
    total_volume_cc : float
        Total ROI volume in cc.
    """

    dose_bin_edges_gy: npt.NDArray[np.float64]
    differential_volume_cc: npt.NDArray[np.float64]
    total_volume_cc: float
    _cumulative_volume_cc: npt.NDArray[np.float64] = field(
        init=False, repr=False, compare=False
    )
    _cumulative_volume_pct: npt.NDArray[np.float64] = field(
        init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        edges = np.array(self.dose_bin_edges_gy, dtype=np.float64)
        dv = np.array(self.differential_volume_cc, dtype=np.float64)
        if len(edges) < 2:
            raise ValueError("DVHBins needs at least 2 bin edges (1 bin)")
        if len(dv) != len(edges) - 1:
            raise ValueError(
                f"differential_volume_cc length {len(dv)} != "
                f"dose_bin_edges_gy length {len(edges)} - 1"
            )
        edges.flags.writeable = False
        dv.flags.writeable = False
        object.__setattr__(self, "dose_bin_edges_gy", edges)
        object.__setattr__(self, "differential_volume_cc", dv)

        cum = np.concatenate([np.cumsum(dv[::-1])[::-1], [0.0]])
        cum.flags.writeable = False
        object.__setattr__(self, "_cumulative_volume_cc", cum)

        pct = cum / self.total_volume_cc * 100.0
        pct.flags.writeable = False
        object.__setattr__(self, "_cumulative_volume_pct", pct)

    @property
    def bin_width_gy(self) -> float:
        """Uniform bin width (assumes uniform spacing)."""
        return float(self.dose_bin_edges_gy[1] - self.dose_bin_edges_gy[0])

    @property
    def cumulative_volume_cc(self) -> npt.NDArray[np.float64]:
        """Cumulative DVH: V(D) at each bin edge (N+1 values).

        ``cumulative_volume_cc[j]`` = total volume receiving >=
        ``dose_bin_edges_gy[j]``.
        """
        return self._cumulative_volume_cc

    @property
    def cumulative_volume_pct(self) -> npt.NDArray[np.float64]:
        """Cumulative DVH as percentage of total volume."""
        return self._cumulative_volume_pct

    @property
    def min_dose_gy(self) -> float:
        """Minimum dose (lowest bin edge with nonzero volume)."""
        nonzero = np.nonzero(self.differential_volume_cc)[0]
        if len(nonzero) == 0:
            return 0.0
        return float(self.dose_bin_edges_gy[nonzero[0]])

    @property
    def max_dose_gy(self) -> float:
        """Maximum dose (upper edge of highest occupied bin)."""
        nonzero = np.nonzero(self.differential_volume_cc)[0]
        if len(nonzero) == 0:
            return 0.0
        return float(self.dose_bin_edges_gy[nonzero[-1] + 1])

    @property
    def mean_dose_gy(self) -> float:
        """Volume-weighted mean dose from bin centres."""
        bin_centres = (self.dose_bin_edges_gy[:-1] + self.dose_bin_edges_gy[1:]) / 2.0
        return float(
            np.sum(bin_centres * self.differential_volume_cc) / self.total_volume_cc
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, DVHBins):
            return NotImplemented
        return (
            np.array_equal(self.dose_bin_edges_gy, other.dose_bin_edges_gy)
            and np.array_equal(
                self.differential_volume_cc, other.differential_volume_cc
            )
            and self.total_volume_cc == other.total_volume_cc
        )

    def __hash__(self) -> int:
        return hash(self.dose_bin_edges_gy.tobytes())


@dataclass(frozen=True, slots=True)
class MetricResult:
    """Result for a single computed metric.

    Self-describing: carries its own MetricSpec.
    """

    spec: MetricSpec
    value: Optional[float]
    unit: str
    convergence_estimate: Optional[float] = None
    issues: tuple[Issue, ...] = ()


@dataclass(frozen=True, slots=True)
class ROIDiagnostics:
    """Per-ROI computation diagnostics."""

    effective_supersampling: Optional[int] = None
    boundary_voxel_count: Optional[int] = None
    interior_voxel_count: Optional[int] = None
    mean_boundary_gradient_gy_per_mm: Optional[float] = None
    contour_slice_count: int = 0
    endcap_volume_fraction: Optional[float] = None
    computation_time_s: Optional[float] = None


@dataclass(frozen=True, slots=True)
class ROIResult:
    """Complete result for a single ROI.

    Self-describing: carries its own ROIRef and explicit status.
    """

    roi: ROIRef
    status: Literal["ok", "skipped", "failed"]
    volume_cc: Optional[float] = None
    metrics: tuple[MetricResult, ...] = ()
    dvh: Optional[DVHBins] = None
    diagnostics: Optional[ROIDiagnostics] = None
    issues: tuple[Issue, ...] = ()


@dataclass(frozen=True, slots=True)
class InputMetadata:
    """Metadata about the computation inputs, for provenance."""

    rtstruct_file_sha256: Optional[str] = None
    rtdose_file_sha256: Optional[str] = None
    dose_grid_frame: Optional[GridFrame] = None


@dataclass(frozen=True, slots=True)
class PlatformInfo:
    """Platform and dependency version info, for reproducibility."""

    python_version: str = ""
    numpy_version: str = ""
    numba_version: str = ""
    os: str = ""


@dataclass(frozen=True, slots=True)
class ProvenanceRecord:
    """Complete provenance for a computation run."""

    pymedphys_version: str = ""
    timestamp_utc: str = ""
    config: DVHConfig = None  # type: ignore[assignment]
    input_metadata: InputMetadata = None  # type: ignore[assignment]
    platform: PlatformInfo = None  # type: ignore[assignment]


@dataclass(frozen=True, slots=True)
class DVHResultSet:
    """Top-level result object.

    Results are stored as a tuple of ``ROIResult`` (not a name-keyed
    dict), since ROI names may duplicate.
    """

    schema_version: str
    results: tuple[ROIResult, ...]
    provenance: ProvenanceRecord
    computation_time_s: float
    dose_refs: Optional[DoseReferenceSet] = None
    issues: tuple[Issue, ...] = ()

    def by_name(self, name: str) -> ROIResult:
        """Look up an ROIResult by name.

        Raises
        ------
        KeyError
            If no ROI with that name exists.
        ValueError
            If multiple ROIs share the name.
        """
        matches = [r for r in self.results if r.roi.name == name]
        if not matches:
            raise KeyError(f"No ROI named '{name}'")
        if len(matches) > 1:
            raise ValueError(
                f"Ambiguous ROI name '{name}' — {len(matches)} ROIs match. "
                f"Use by_ref() with an ROIRef including roi_number."
            )
        return matches[0]

    def by_ref(self, ref: ROIRef) -> ROIResult:
        """Look up an ROIResult by ROIRef (matches by number then name)."""
        for r in self.results:
            if r.roi.matches(ref):
                return r
        raise KeyError(f"No ROI matching {ref}")

    def __getitem__(self, key: str) -> ROIResult:
        """Convenience: ``result["PTV"]`` delegates to ``by_name``."""
        return self.by_name(key)

    @property
    def roi_names(self) -> FrozenSet[str]:
        """All ROI names in the result set."""
        return frozenset(r.roi.name for r in self.results)

    def all_issues(self) -> tuple[Issue, ...]:
        """Collect all issues across all levels.

        Returns issues in order: global, then per-ROI, then per-metric
        within each ROI.
        """
        all_i: list[Issue] = list(self.issues)
        for roi_result in self.results:
            all_i.extend(roi_result.issues)
            for metric_result in roi_result.metrics:
                all_i.extend(metric_result.issues)
        return tuple(all_i)
