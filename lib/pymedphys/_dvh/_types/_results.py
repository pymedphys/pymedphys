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
from pymedphys._dvh._types._validators import (
    _validate_nonneg_array,
    _validate_nonneg_finite,
    _validate_strictly_increasing,
)


@dataclass(frozen=True, slots=True, eq=False)
class DVHBins:
    """Canonical DVH storage: dose bin edges + differential volume.

    ``dose_bin_edges_gy`` has length N+1 for N bins.
    ``differential_volume_cc`` has length N.

    Invariants enforced at construction:

    - Edges are finite and strictly increasing.
    - Differential volumes are finite and non-negative.
    - ``total_volume_cc`` is finite and non-negative.

    When ``total_volume_cc == 0`` (zero-volume ROI), cumulative
    percentage values are all 0.0 and ``binned_mean_dose_gy``
    returns 0.0.

    Parameters
    ----------
    dose_bin_edges_gy : npt.NDArray[np.float64]
        Bin edges in Gy, length N+1. Must be finite and strictly
        increasing.
    differential_volume_cc : npt.NDArray[np.float64]
        Differential volume per bin in cc, length N. Must be finite
        and non-negative.
    total_volume_cc : float
        Total ROI volume in cc. Must be finite and non-negative.
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
        _validate_strictly_increasing(edges, "dose_bin_edges_gy")
        _validate_nonneg_array(dv, "differential_volume_cc")
        _validate_nonneg_finite(self.total_volume_cc, "total_volume_cc")

        edges.flags.writeable = False
        dv.flags.writeable = False
        object.__setattr__(self, "dose_bin_edges_gy", edges)
        object.__setattr__(self, "differential_volume_cc", dv)

        cum = np.concatenate([np.cumsum(dv[::-1])[::-1], [0.0]])
        cum.flags.writeable = False
        object.__setattr__(self, "_cumulative_volume_cc", cum)

        if self.total_volume_cc == 0:
            pct = np.zeros_like(cum)
        else:
            pct = cum / self.total_volume_cc * 100.0
        pct.flags.writeable = False
        object.__setattr__(self, "_cumulative_volume_pct", pct)

    @property
    def bin_width_gy(self) -> float:
        """Uniform bin width in Gy.

        Raises
        ------
        ValueError
            If bin widths are not uniform (relative tolerance 1e-9).
        """
        widths = np.diff(self.dose_bin_edges_gy)
        w0 = widths[0]
        if len(widths) > 1 and not np.allclose(widths, w0, rtol=1e-9):
            raise ValueError(
                "bin_width_gy requires uniform bin widths, but edges are "
                "non-uniform. Use np.diff(dose_bin_edges_gy) for per-bin widths."
            )
        return float(w0)

    @property
    def cumulative_volume_cc(self) -> npt.NDArray[np.float64]:
        """Cumulative DVH: V(D) at each bin edge (N+1 values).

        ``cumulative_volume_cc[j]`` = total volume receiving >=
        ``dose_bin_edges_gy[j]``.
        """
        return self._cumulative_volume_cc

    @property
    def cumulative_volume_pct(self) -> npt.NDArray[np.float64]:
        """Cumulative DVH as percentage of total volume.

        Returns all zeros when ``total_volume_cc == 0``.
        """
        return self._cumulative_volume_pct

    @property
    def binned_min_dose_gy(self) -> float:
        """Histogram-derived minimum dose approximation.

        Returns the lower edge of the lowest bin with nonzero volume.
        This is a binned approximation — the true minimum dose lies
        somewhere within that bin.

        Returns 0.0 for zero-volume ROIs.
        """
        nonzero = np.nonzero(self.differential_volume_cc)[0]
        if len(nonzero) == 0:
            return 0.0
        return float(self.dose_bin_edges_gy[nonzero[0]])

    @property
    def binned_max_dose_gy(self) -> float:
        """Histogram-derived maximum dose approximation.

        Returns the upper edge of the highest bin with nonzero volume.
        This is a binned approximation — the true maximum dose lies
        somewhere within that bin.

        Returns 0.0 for zero-volume ROIs.
        """
        nonzero = np.nonzero(self.differential_volume_cc)[0]
        if len(nonzero) == 0:
            return 0.0
        return float(self.dose_bin_edges_gy[nonzero[-1] + 1])

    @property
    def binned_mean_dose_gy(self) -> float:
        """Histogram-derived volume-weighted mean dose approximation.

        Computed from bin centres weighted by differential volume.
        This is a binned approximation that depends on bin width.

        Returns 0.0 for zero-volume ROIs.
        """
        if self.total_volume_cc == 0:
            return 0.0
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
    value: Optional[float]
    unit: str
    convergence_estimate: Optional[float] = None
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

    effective_supersampling: Optional[int] = None
    boundary_voxel_count: Optional[int] = None
    interior_voxel_count: Optional[int] = None
    mean_boundary_gradient_gy_per_mm: Optional[float] = None
    contour_slice_count: int = 0
    endcap_volume_fraction: Optional[float] = None
    computation_time_s: Optional[float] = None

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
    status: Literal["ok", "skipped", "failed"]
    volume_cc: Optional[float] = None
    metrics: tuple[MetricResult, ...] = ()
    dvh: Optional[DVHBins] = None
    diagnostics: Optional[ROIDiagnostics] = None
    issues: tuple[Issue, ...] = ()

    def to_dict(self) -> dict:
        d: dict = {
            "roi": self.roi.to_dict(),
            "status": self.status,
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
            status=d["status"],
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
    """Metadata about the computation inputs, for provenance.

    Parameters
    ----------
    rtstruct_file_sha256 : str, optional
        SHA-256 hash of the RTSTRUCT file.
    rtdose_file_sha256 : str, optional
        SHA-256 hash of the RTDOSE file.
    dose_grid_frame : GridFrame, optional
        Grid frame of the dose input.
    input_pathway : str, optional
        How the inputs were provided. One of ``"from_dicom"``,
        ``"from_arrays"``, or ``"direct"``.
    structure_representation : str, optional
        How structures were represented. One of ``"contour"``,
        ``"mask"``, or ``"sdf"``.
    """

    rtstruct_file_sha256: Optional[str] = None
    rtdose_file_sha256: Optional[str] = None
    dose_grid_frame: Optional[GridFrame] = None
    input_pathway: Optional[str] = None
    structure_representation: Optional[str] = None

    def to_dict(self) -> dict:
        d: dict = {}
        if self.rtstruct_file_sha256 is not None:
            d["rtstruct_file_sha256"] = self.rtstruct_file_sha256
        if self.rtdose_file_sha256 is not None:
            d["rtdose_file_sha256"] = self.rtdose_file_sha256
        if self.dose_grid_frame is not None:
            d["dose_grid_frame"] = self.dose_grid_frame.to_dict()
        if self.input_pathway is not None:
            d["input_pathway"] = self.input_pathway
        if self.structure_representation is not None:
            d["structure_representation"] = self.structure_representation
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
            input_pathway=d.get("input_pathway"),
            structure_representation=d.get("structure_representation"),
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


@dataclass(frozen=True, slots=True)
class ProvenanceRecord:
    """Complete provenance for a computation run.

    Parameters
    ----------
    pymedphys_version : str
        Version of pymedphys that produced the results.
    timestamp_utc : str
        ISO 8601 timestamp of computation start.
    config : DVHConfig, optional
        Configuration used for this run.
    input_metadata : InputMetadata, optional
        Metadata about the inputs.
    platform : PlatformInfo, optional
        Platform and dependency versions.
    inapplicable_settings : tuple[str, ...], optional
        Settings that are irrelevant for the given input pathway.
        For example, contour interpolation and end-capping are
        inapplicable when inputs are mask-derived via ``from_arrays``.
    """

    pymedphys_version: str = ""
    timestamp_utc: str = ""
    config: Optional[DVHConfig] = None
    input_metadata: Optional[InputMetadata] = None
    platform: Optional[PlatformInfo] = None
    inapplicable_settings: tuple[str, ...] = ()

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
        if self.inapplicable_settings:
            d["inapplicable_settings"] = list(self.inapplicable_settings)
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
            inapplicable_settings=tuple(d.get("inapplicable_settings", ())),
        )


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
        """Deserialise from a plain dict."""
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
