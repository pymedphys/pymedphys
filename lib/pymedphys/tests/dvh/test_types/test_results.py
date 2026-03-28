"""Tests for result types: DVHBins, MetricResult, ROIResult, DVHResultSet (RFC section 6.9)."""

from __future__ import annotations

import numpy as np
import pytest

from pymedphys._dvh._types._config import DVHConfig
from pymedphys._dvh._types._issues import Issue, IssueCode, IssueLevel
from pymedphys._dvh._types._metrics import MetricFamily, MetricSpec
from pymedphys._dvh._types._results import (
    DVHBins,
    DVHResultSet,
    InputMetadata,
    MetricResult,
    PlatformInfo,
    ProvenanceRecord,
    ROIDiagnostics,
    ROIResult,
    ROIStatus,
)
from pymedphys._dvh._types._roi_ref import ROIRef


class TestDVHBins:
    """Tests for the canonical DVH storage type."""

    def _make_simple_dvh(self) -> DVHBins:
        """3 bins: [0, 1), [1, 2), [2, 3) with volumes 3, 2, 1 cc."""
        edges = np.array([0.0, 1.0, 2.0, 3.0])
        diff_vol = np.array([3.0, 2.0, 1.0])
        return DVHBins(
            dose_bin_edges_gy=edges,
            differential_volume_cc=diff_vol,
            total_volume_cc=6.0,
        )

    def test_valid_construction(self) -> None:
        dvh = self._make_simple_dvh()
        assert len(dvh.dose_bin_edges_gy) == 4
        assert len(dvh.differential_volume_cc) == 3
        assert dvh.total_volume_cc == 6.0

    def test_rejects_less_than_2_edges(self) -> None:
        with pytest.raises(ValueError, match="at least 2"):
            DVHBins(
                dose_bin_edges_gy=np.array([0.0]),
                differential_volume_cc=np.array([]),
                total_volume_cc=1.0,
            )

    def test_rejects_mismatched_lengths(self) -> None:
        with pytest.raises(ValueError, match="length"):
            DVHBins(
                dose_bin_edges_gy=np.array([0.0, 1.0, 2.0]),
                differential_volume_cc=np.array([1.0]),  # should be 2
                total_volume_cc=1.0,
            )

    def test_cumulative_volume_cc_monotonically_nonincreasing(self) -> None:
        dvh = self._make_simple_dvh()
        cum = dvh.cumulative_volume_cc
        diffs = np.diff(cum)
        assert np.all(diffs <= 0), f"Cumulative DVH not non-increasing: {cum}"

    def test_cumulative_volume_cc_last_element_is_zero(self) -> None:
        dvh = self._make_simple_dvh()
        assert dvh.cumulative_volume_cc[-1] == 0.0

    def test_cumulative_volume_cc_first_element(self) -> None:
        dvh = self._make_simple_dvh()
        # First element should be total of all differential volumes
        assert dvh.cumulative_volume_cc[0] == pytest.approx(6.0)

    def test_cumulative_volume_pct_at_first_edge(self) -> None:
        dvh = self._make_simple_dvh()
        assert dvh.cumulative_volume_pct[0] == pytest.approx(100.0)

    def test_bin_width_gy(self) -> None:
        dvh = self._make_simple_dvh()
        assert dvh.bin_width_gy == pytest.approx(1.0)

    def test_min_dose_gy(self) -> None:
        dvh = self._make_simple_dvh()
        assert dvh.min_dose_gy == pytest.approx(0.0)

    def test_max_dose_gy(self) -> None:
        dvh = self._make_simple_dvh()
        assert dvh.max_dose_gy == pytest.approx(3.0)

    def test_mean_dose_gy(self) -> None:
        dvh = self._make_simple_dvh()
        # bin centres: 0.5, 1.5, 2.5; volumes: 3, 2, 1; total: 6
        # mean = (0.5*3 + 1.5*2 + 2.5*1) / 6 = (1.5 + 3.0 + 2.5) / 6 = 7/6
        assert dvh.mean_dose_gy == pytest.approx(7.0 / 6.0)

    def test_arrays_are_read_only(self) -> None:
        dvh = self._make_simple_dvh()
        with pytest.raises(ValueError, match="read-only"):
            dvh.dose_bin_edges_gy[0] = 999.0
        with pytest.raises(ValueError, match="read-only"):
            dvh.differential_volume_cc[0] = 999.0


class TestMetricResult:
    """Tests for MetricResult."""

    def test_carries_its_spec(self) -> None:
        spec = MetricSpec(family=MetricFamily.SCALAR, raw="mean")
        result = MetricResult(spec=spec, value=45.2, unit="Gy")
        assert result.spec is spec
        assert result.value == 45.2
        assert result.unit == "Gy"

    def test_value_can_be_none(self) -> None:
        spec = MetricSpec(family=MetricFamily.SCALAR, raw="mean")
        result = MetricResult(spec=spec, value=None, unit="Gy")
        assert result.value is None


class TestROIDiagnostics:
    """Tests for ROIDiagnostics."""

    def test_default_construction(self) -> None:
        diag = ROIDiagnostics()
        assert diag.effective_supersampling is None
        assert diag.boundary_voxel_count is None
        assert diag.contour_slice_count == 0


class TestROIResult:
    """Tests for ROIResult."""

    def test_status_ok(self) -> None:
        result = ROIResult(
            roi=ROIRef(name="PTV"),
            status=ROIStatus.OK,
            volume_cc=45.0,
        )
        assert result.status == ROIStatus.OK

    def test_status_skipped(self) -> None:
        result = ROIResult(
            roi=ROIRef(name="BadROI"),
            status=ROIStatus.SKIPPED,
        )
        assert result.status == ROIStatus.SKIPPED

    def test_status_failed(self) -> None:
        result = ROIResult(
            roi=ROIRef(name="ErrorROI"),
            status=ROIStatus.FAILED,
        )
        assert result.status == ROIStatus.FAILED


def _make_provenance() -> ProvenanceRecord:
    """Helper to create a minimal ProvenanceRecord."""
    return ProvenanceRecord(
        pymedphys_version="0.1.0",
        timestamp_utc="2024-01-01T00:00:00Z",
        config=DVHConfig(),
        input_metadata=InputMetadata(),
        platform=PlatformInfo(
            python_version="3.11.0",
            numpy_version="1.26.0",
            numba_version="0.59.0",
            os="Linux",
        ),
    )


def _make_result_set(**kwargs: object) -> DVHResultSet:
    """Helper to create a minimal DVHResultSet with sensible defaults."""
    defaults: dict = {
        "schema_version": "1.0",
        "results": (),
        "provenance": _make_provenance(),
        "computation_time_s": 1.0,
    }
    defaults.update(kwargs)
    return DVHResultSet(**defaults)  # type: ignore[arg-type]


class TestDVHResultSet:
    """Tests for DVHResultSet."""

    def _make_result(
        self,
        name: str,
        number: int | None = None,
        status: ROIStatus = ROIStatus.OK,
    ) -> ROIResult:
        return ROIResult(
            roi=ROIRef(name=name, roi_number=number),
            status=status,
        )

    def test_by_name_returns_matching_roi(self) -> None:
        rs = DVHResultSet(
            schema_version="1.0",
            results=(
                self._make_result("PTV"),
                self._make_result("Cord"),
            ),
            provenance=_make_provenance(),
            computation_time_s=1.0,
        )
        result = rs.by_name("PTV")
        assert result.roi.name == "PTV"

    def test_by_name_raises_on_missing(self) -> None:
        rs = DVHResultSet(
            schema_version="1.0",
            results=(self._make_result("PTV"),),
            provenance=_make_provenance(),
            computation_time_s=1.0,
        )
        with pytest.raises(KeyError, match="No ROI named"):
            rs.by_name("Missing")

    def test_by_name_raises_on_ambiguity(self) -> None:
        rs = DVHResultSet(
            schema_version="1.0",
            results=(
                self._make_result("PTV", number=1),
                self._make_result("PTV", number=2),
            ),
            provenance=_make_provenance(),
            computation_time_s=1.0,
        )
        with pytest.raises(ValueError, match="Ambiguous"):
            rs.by_name("PTV")

    def test_by_ref_resolves_by_number(self) -> None:
        rs = DVHResultSet(
            schema_version="1.0",
            results=(
                self._make_result("PTV", number=1),
                self._make_result("PTV", number=2),
            ),
            provenance=_make_provenance(),
            computation_time_s=1.0,
        )
        ref = ROIRef(name="PTV", roi_number=2)
        result = rs.by_ref(ref)
        assert result.roi.roi_number == 2

    def test_getitem_delegates_to_by_name(self) -> None:
        rs = DVHResultSet(
            schema_version="1.0",
            results=(self._make_result("PTV"),),
            provenance=_make_provenance(),
            computation_time_s=1.0,
        )
        assert rs["PTV"].roi.name == "PTV"

    def test_roi_names_returns_frozenset(self) -> None:
        rs = DVHResultSet(
            schema_version="1.0",
            results=(
                self._make_result("PTV"),
                self._make_result("Cord"),
            ),
            provenance=_make_provenance(),
            computation_time_s=1.0,
        )
        names = rs.roi_names
        assert isinstance(names, frozenset)
        assert names == frozenset({"PTV", "Cord"})

    def test_all_issues_collects_across_levels(self) -> None:
        global_issue = Issue(
            level=IssueLevel.INFO,
            code=IssueCode.Z_TOLERANCE_APPLIED,
            message="global",
        )
        roi_issue = Issue(
            level=IssueLevel.WARNING,
            code=IssueCode.DOSE_GRID_COARSE,
            message="roi-level",
            path=("PTV",),
        )
        metric_issue = Issue(
            level=IssueLevel.ERROR,
            code=IssueCode.METRIC_UNAVAILABLE,
            message="metric-level",
            path=("PTV", "D95%"),
        )
        spec = MetricSpec(family=MetricFamily.SCALAR, raw="mean")
        metric_result = MetricResult(
            spec=spec, value=None, unit="Gy", issues=(metric_issue,)
        )
        roi_result = ROIResult(
            roi=ROIRef(name="PTV"),
            status=ROIStatus.OK,
            metrics=(metric_result,),
            issues=(roi_issue,),
        )
        rs = DVHResultSet(
            schema_version="1.0",
            results=(roi_result,),
            provenance=_make_provenance(),
            computation_time_s=1.0,
            issues=(global_issue,),
        )
        all_issues = rs.all_issues()
        assert len(all_issues) == 3
        assert all_issues[0].message == "global"
        assert all_issues[1].message == "roi-level"
        assert all_issues[2].message == "metric-level"

    # D4: Test by_ref raises KeyError on missing match
    def test_by_ref_raises_on_missing(self) -> None:
        rs = DVHResultSet(
            schema_version="1.0",
            results=(self._make_result("PTV", number=1),),
            provenance=_make_provenance(),
            computation_time_s=1.0,
        )
        with pytest.raises(KeyError, match="No ROI matching"):
            rs.by_ref(ROIRef(name="Nonexistent", roi_number=99))

    # B7/F3: schema_version and computation_time validation
    def test_rejects_unsupported_schema_version(self) -> None:
        with pytest.raises(ValueError, match="Unsupported schema_version"):
            DVHResultSet(
                schema_version="99.0",
                results=(),
                provenance=_make_provenance(),
                computation_time_s=1.0,
            )

    def test_rejects_negative_computation_time(self) -> None:
        with pytest.raises(ValueError, match="computation_time_s"):
            DVHResultSet(
                schema_version="1.0",
                results=(),
                provenance=_make_provenance(),
                computation_time_s=-1.0,
            )


class TestDVHBinsValidation:
    """Tests for DVHBins construction-time validation (A1, A2)."""

    def test_rejects_non_increasing_edges(self) -> None:
        """A1: Reversed bin edges must be rejected."""
        with pytest.raises(ValueError, match="strictly increasing"):
            DVHBins(
                dose_bin_edges_gy=np.array([3.0, 2.0, 1.0, 0.0]),
                differential_volume_cc=np.array([1.0, 1.0, 1.0]),
                total_volume_cc=3.0,
            )

    def test_rejects_equal_adjacent_edges(self) -> None:
        """A1: Equal adjacent edges are not strictly increasing."""
        with pytest.raises(ValueError, match="strictly increasing"):
            DVHBins(
                dose_bin_edges_gy=np.array([0.0, 1.0, 1.0, 2.0]),
                differential_volume_cc=np.array([1.0, 1.0, 1.0]),
                total_volume_cc=3.0,
            )

    def test_rejects_negative_differential_volume(self) -> None:
        """A1: Negative differential volumes are physically meaningless."""
        with pytest.raises(ValueError, match="non-negative"):
            DVHBins(
                dose_bin_edges_gy=np.array([0.0, 1.0, 2.0]),
                differential_volume_cc=np.array([1.0, -0.5]),
                total_volume_cc=1.0,
            )

    def test_rejects_zero_total_volume(self) -> None:
        """A1: Zero total volume causes division by zero."""
        with pytest.raises(ValueError, match="strictly positive"):
            DVHBins(
                dose_bin_edges_gy=np.array([0.0, 1.0, 2.0]),
                differential_volume_cc=np.array([0.0, 0.0]),
                total_volume_cc=0.0,
            )

    def test_rejects_negative_total_volume(self) -> None:
        """A1: Negative total volume is physically meaningless."""
        with pytest.raises(ValueError, match="strictly positive"):
            DVHBins(
                dose_bin_edges_gy=np.array([0.0, 1.0, 2.0]),
                differential_volume_cc=np.array([1.0, 1.0]),
                total_volume_cc=-1.0,
            )

    def test_rejects_nonuniform_spacing(self) -> None:
        """A2: Non-uniform bin spacing is not yet supported."""
        with pytest.raises(ValueError, match="uniform spacing"):
            DVHBins(
                dose_bin_edges_gy=np.array([0.0, 1.0, 3.0]),
                differential_volume_cc=np.array([1.0, 1.0]),
                total_volume_cc=2.0,
            )

    def test_all_zero_differential_volume(self) -> None:
        """D2: All-zero differential volume is valid (empty structure)
        but mean_dose_gy returns 0.0 (no volume to average over).
        """
        dvh = DVHBins(
            dose_bin_edges_gy=np.array([0.0, 1.0, 2.0]),
            differential_volume_cc=np.array([0.0, 0.0]),
            total_volume_cc=1.0,  # Must be positive
        )
        assert dvh.min_dose_gy == 0.0
        assert dvh.max_dose_gy == 0.0
        assert dvh.mean_dose_gy == pytest.approx(0.0)
        assert dvh.cumulative_volume_cc[0] == 0.0


class TestROIStatusEnum:
    """Tests for ROIStatus enum (C2)."""

    def test_status_values(self) -> None:
        assert ROIStatus.OK == "ok"
        assert ROIStatus.SKIPPED == "skipped"
        assert ROIStatus.FAILED == "failed"

    def test_roi_result_coerces_string_to_enum(self) -> None:
        result = ROIResult(roi=ROIRef(name="PTV"), status="ok")  # type: ignore[arg-type]
        assert isinstance(result.status, ROIStatus)
        assert result.status == ROIStatus.OK

    def test_roi_result_accepts_enum(self) -> None:
        result = ROIResult(roi=ROIRef(name="PTV"), status=ROIStatus.SKIPPED)
        assert result.status == ROIStatus.SKIPPED

    def test_roi_result_rejects_invalid_status(self) -> None:
        with pytest.raises(ValueError):
            ROIResult(roi=ROIRef(name="PTV"), status="invalid_status")  # type: ignore[arg-type]


class TestProvenanceTimestampValidation:
    """Tests for ProvenanceRecord timestamp validation (C4)."""

    def test_valid_timestamp(self) -> None:
        prov = ProvenanceRecord(timestamp_utc="2024-01-15T10:30:00Z")
        assert prov.timestamp_utc == "2024-01-15T10:30:00Z"

    def test_valid_timestamp_with_fractional_seconds(self) -> None:
        prov = ProvenanceRecord(timestamp_utc="2024-01-15T10:30:00.123Z")
        assert prov.timestamp_utc == "2024-01-15T10:30:00.123Z"

    def test_empty_timestamp_allowed(self) -> None:
        prov = ProvenanceRecord(timestamp_utc="")
        assert prov.timestamp_utc == ""

    def test_rejects_non_utc_timestamp(self) -> None:
        with pytest.raises(ValueError, match="ISO 8601 UTC"):
            ProvenanceRecord(timestamp_utc="2024-01-15T10:30:00+05:00")

    def test_rejects_malformed_timestamp(self) -> None:
        with pytest.raises(ValueError, match="ISO 8601 UTC"):
            ProvenanceRecord(timestamp_utc="not-a-timestamp")
