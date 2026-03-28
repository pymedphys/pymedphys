"""Result types (RFC section 6.9)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

import numpy as np
import numpy.typing as npt

from pymedphys._dvh._types._config import DVHConfig
from pymedphys._dvh._types._dose_ref import DoseReferenceSet
from pymedphys._dvh._types._grid_frame import GridFrame
from pymedphys._dvh._types._issues import Issue
from pymedphys._dvh._types._metrics import MetricSpec
from pymedphys._dvh._types._roi_ref import ROIRef


class ROIStatus(str, Enum):
    """Status of an ROI computation result."""

    OK = "ok"
    SKIPPED = "skipped"
    FAILED = "failed"


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
        # A1: Bin edges must be strictly increasing
        diffs = np.diff(edges)
        if not np.all(diffs > 0):
            raise ValueError("dose_bin_edges_gy must be strictly increasing")
        # A2: Uniform bin spacing required (non-uniform may be supported later)
        widths = diffs
        if not np.allclose(widths, widths[0]):
            raise ValueError(
                "dose_bin_edges_gy must have uniform spacing. "
                "Non-uniform bin widths are not yet supported."
            )
        # A1: Differential volumes must be non-negative
        if np.any(dv < 0):
            raise ValueError("differential_volume_cc values must be non-negative")
        # A1: Total volume must be strictly positive
        if self.total_volume_cc <= 0:
            raise ValueError(
                f"total_volume_cc must be strictly positive, got {self.total_volume_cc}"
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
        """Uniform bin width in Gy (uniform spacing is enforced at construction)."""
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

    def to_dict(self) -> dict:
        """Serialise to a plain dict. Cumulative values are NOT included."""
        return {
            "dose_bin_edges_gy": self.dose_bin_edges_gy.tolist(),
            "differential_volume_cc": self.differential_volume_cc.tolist(),
            "total_volume_cc": self.total_volume_cc,
        }

    @classmethod
    def from_dict(cls, d: dict) -> DVHBins:
        """Deserialise from a plain dict."""
        return cls(
            dose_bin_edges_gy=np.array(d["dose_bin_edges_gy"], dtype=np.float64),
            differential_volume_cc=np.array(
                d["differential_volume_cc"], dtype=np.float64
            ),
            total_volume_cc=d["total_volume_cc"],
        )


@dataclass(frozen=True, slots=True)
class MetricResult:
    """Result for a single computed metric.

    Self-describing: carries its own MetricSpec.
    """

    spec: MetricSpec
    value: float | None
    unit: str
    convergence_estimate: float | None = None
    issues: tuple[Issue, ...] = ()

    def to_dict(self) -> dict:
        d: dict = {
            "spec": self.spec.to_dict(),
            "value": self.value,
            "unit": self.unit,
        }
        if self.convergence_estimate is not None:
            d["convergence_estimate"] = self.convergence_estimate
        if self.issues:
            d["issues"] = [i.to_dict() for i in self.issues]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> MetricResult:
        return cls(
            spec=MetricSpec.from_dict(d["spec"]),
            value=d.get("value"),
            unit=d["unit"],
            convergence_estimate=d.get("convergence_estimate"),
            issues=tuple(Issue.from_dict(i) for i in d.get("issues", ())),
        )


@dataclass(frozen=True, slots=True)
class ROIDiagnostics:
    """Per-ROI computation diagnostics."""

    effective_supersampling: int | None = None
    boundary_voxel_count: int | None = None
    interior_voxel_count: int | None = None
    mean_boundary_gradient_gy_per_mm: float | None = None
    contour_slice_count: int = 0
    endcap_volume_fraction: float | None = None
    computation_time_s: float | None = None

    def to_dict(self) -> dict:
        d: dict = {"contour_slice_count": self.contour_slice_count}
        for field_name in (
            "effective_supersampling",
            "boundary_voxel_count",
            "interior_voxel_count",
            "mean_boundary_gradient_gy_per_mm",
            "endcap_volume_fraction",
            "computation_time_s",
        ):
            val = getattr(self, field_name)
            if val is not None:
                d[field_name] = val
        return d

    @classmethod
    def from_dict(cls, d: dict) -> ROIDiagnostics:
        return cls(
            effective_supersampling=d.get("effective_supersampling"),
            boundary_voxel_count=d.get("boundary_voxel_count"),
            interior_voxel_count=d.get("interior_voxel_count"),
            mean_boundary_gradient_gy_per_mm=d.get("mean_boundary_gradient_gy_per_mm"),
            contour_slice_count=d.get("contour_slice_count", 0),
            endcap_volume_fraction=d.get("endcap_volume_fraction"),
            computation_time_s=d.get("computation_time_s"),
        )


@dataclass(frozen=True, slots=True)
class ROIResult:
    """Complete result for a single ROI.

    Self-describing: carries its own ROIRef and explicit status.
    """

    roi: ROIRef
    status: ROIStatus
    volume_cc: float | None = None
    metrics: tuple[MetricResult, ...] = ()
    dvh: DVHBins | None = None
    diagnostics: ROIDiagnostics | None = None
    issues: tuple[Issue, ...] = ()

    def __post_init__(self) -> None:
        if isinstance(self.status, str):
            object.__setattr__(self, "status", ROIStatus(self.status))

    def to_dict(self) -> dict:
        d: dict = {
            "roi": self.roi.to_dict(),
            "status": self.status.value,
        }
        if self.volume_cc is not None:
            d["volume_cc"] = self.volume_cc
        if self.metrics:
            d["metrics"] = [m.to_dict() for m in self.metrics]
        if self.dvh is not None:
            d["dvh"] = self.dvh.to_dict()
        if self.diagnostics is not None:
            d["diagnostics"] = self.diagnostics.to_dict()
        if self.issues:
            d["issues"] = [i.to_dict() for i in self.issues]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> ROIResult:
        dvh_d = d.get("dvh")
        diag_d = d.get("diagnostics")
        return cls(
            roi=ROIRef.from_dict(d["roi"]),
            status=ROIStatus(d["status"]),
            volume_cc=d.get("volume_cc"),
            metrics=tuple(MetricResult.from_dict(m) for m in d.get("metrics", ())),
            dvh=DVHBins.from_dict(dvh_d) if dvh_d is not None else None,
            diagnostics=(
                ROIDiagnostics.from_dict(diag_d) if diag_d is not None else None
            ),
            issues=tuple(Issue.from_dict(i) for i in d.get("issues", ())),
        )


@dataclass(frozen=True, slots=True)
class InputMetadata:
    """Metadata about the computation inputs, for provenance."""

    rtstruct_file_sha256: str | None = None
    rtdose_file_sha256: str | None = None
    dose_grid_frame: GridFrame | None = None

    def to_dict(self) -> dict:
        d: dict = {}
        if self.rtstruct_file_sha256 is not None:
            d["rtstruct_file_sha256"] = self.rtstruct_file_sha256
        if self.rtdose_file_sha256 is not None:
            d["rtdose_file_sha256"] = self.rtdose_file_sha256
        if self.dose_grid_frame is not None:
            d["dose_grid_frame"] = self.dose_grid_frame.to_dict()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> InputMetadata:
        frame_d = d.get("dose_grid_frame")
        return cls(
            rtstruct_file_sha256=d.get("rtstruct_file_sha256"),
            rtdose_file_sha256=d.get("rtdose_file_sha256"),
            dose_grid_frame=(
                GridFrame.from_dict(frame_d) if frame_d is not None else None
            ),
        )


@dataclass(frozen=True, slots=True)
class PlatformInfo:
    """Platform and dependency version info, for reproducibility."""

    python_version: str = ""
    numpy_version: str = ""
    numba_version: str = ""
    os: str = ""

    def to_dict(self) -> dict:
        return {
            "python_version": self.python_version,
            "numpy_version": self.numpy_version,
            "numba_version": self.numba_version,
            "os": self.os,
        }

    @classmethod
    def from_dict(cls, d: dict) -> PlatformInfo:
        return cls(
            python_version=d.get("python_version", ""),
            numpy_version=d.get("numpy_version", ""),
            numba_version=d.get("numba_version", ""),
            os=d.get("os", ""),
        )


_ISO8601_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")


@dataclass(frozen=True, slots=True)
class ProvenanceRecord:
    """Complete provenance for a computation run.

    Parameters
    ----------
    timestamp_utc : str
        ISO 8601 UTC timestamp ending in 'Z', e.g.
        ``"2024-01-15T10:30:00Z"``.
    """

    pymedphys_version: str = ""
    timestamp_utc: str = ""
    config: DVHConfig | None = None
    input_metadata: InputMetadata | None = None
    platform: PlatformInfo | None = None

    def __post_init__(self) -> None:
        if self.timestamp_utc and not _ISO8601_UTC_RE.match(self.timestamp_utc):
            raise ValueError(
                f"timestamp_utc must be ISO 8601 UTC (ending in 'Z'), "
                f"got '{self.timestamp_utc}'"
            )

    def to_dict(self) -> dict:
        d: dict = {
            "pymedphys_version": self.pymedphys_version,
            "timestamp_utc": self.timestamp_utc,
        }
        if self.config is not None:
            d["config"] = self.config.to_dict()
        if self.input_metadata is not None:
            d["input_metadata"] = self.input_metadata.to_dict()
        if self.platform is not None:
            d["platform"] = self.platform.to_dict()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> ProvenanceRecord:
        config_d = d.get("config")
        meta_d = d.get("input_metadata")
        plat_d = d.get("platform")
        return cls(
            pymedphys_version=d.get("pymedphys_version", ""),
            timestamp_utc=d.get("timestamp_utc", ""),
            config=DVHConfig.from_dict(config_d) if config_d else None,
            input_metadata=(InputMetadata.from_dict(meta_d) if meta_d else None),
            platform=PlatformInfo.from_dict(plat_d) if plat_d else None,
        )


_SUPPORTED_SCHEMA_VERSIONS = frozenset({"1.0"})


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
    dose_refs: DoseReferenceSet | None = None
    issues: tuple[Issue, ...] = ()

    def __post_init__(self) -> None:
        if self.schema_version not in _SUPPORTED_SCHEMA_VERSIONS:
            raise ValueError(
                f"Unsupported schema_version '{self.schema_version}'. "
                f"Supported: {sorted(_SUPPORTED_SCHEMA_VERSIONS)}"
            )
        if self.computation_time_s < 0:
            raise ValueError(
                f"computation_time_s must be >= 0, got {self.computation_time_s}"
            )

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
    def roi_names(self) -> frozenset[str]:
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

    def to_dict(self) -> dict:
        """Serialise to a plain dict suitable for JSON."""
        d: dict = {
            "schema_version": self.schema_version,
            "results": [r.to_dict() for r in self.results],
            "provenance": self.provenance.to_dict(),
            "computation_time_s": self.computation_time_s,
        }
        if self.dose_refs is not None:
            d["dose_refs"] = self.dose_refs.to_dict()
        if self.issues:
            d["issues"] = [i.to_dict() for i in self.issues]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> DVHResultSet:
        """Deserialise from a plain dict.

        Raises
        ------
        ValueError
            If the schema_version is not supported.
        """
        sv = d.get("schema_version", "")
        if sv not in _SUPPORTED_SCHEMA_VERSIONS:
            raise ValueError(
                f"Unsupported schema_version '{sv}'. "
                f"Supported: {sorted(_SUPPORTED_SCHEMA_VERSIONS)}"
            )
        refs_d = d.get("dose_refs")
        return cls(
            schema_version=d["schema_version"],
            results=tuple(ROIResult.from_dict(r) for r in d["results"]),
            provenance=ProvenanceRecord.from_dict(d["provenance"]),
            computation_time_s=d["computation_time_s"],
            dose_refs=(
                DoseReferenceSet.from_dict(refs_d) if refs_d is not None else None
            ),
            issues=tuple(Issue.from_dict(i) for i in d.get("issues", ())),
        )
