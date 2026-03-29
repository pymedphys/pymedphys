"""Semantic lock-in tests for Phase 0 type contracts.

These tests explicitly lock down the public semantics that must not
regress:

- MetricRequestSet canonical round-trip (lossless for duplicate names)
- Duplicate ROI detection via ROIRef.matches() semantics
- NaN/Inf rejection across dose refs, config, occupancy, SDF, results
- Mutation leakage from caller-owned lists/dicts
- Fixed-axis GridFrame semantics
- MetricResult.unit validation
- Timestamp parsing
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from pymedphys._dvh._types._config import (
    AlgorithmConfig,
    DVHConfig,
    PipelinePolicy,
    RuntimeConfig,
    SupersamplingConfig,
)
from pymedphys._dvh._types._contour import Contour, PlanarRegion
from pymedphys._dvh._types._dose_ref import DoseReference, DoseReferenceSet
from pymedphys._dvh._types._grid_frame import GridFrame
from pymedphys._dvh._types._issues import Issue, IssueCode, IssueLevel
from pymedphys._dvh._types._metrics import (
    MetricFamily,
    MetricRequestSet,
    MetricSpec,
    ROIMetricRequest,
    ThresholdUnit,
)
from pymedphys._dvh._types._dose import DoseGrid
from pymedphys._dvh._types._occupancy import OccupancyField
from pymedphys._dvh._types._results import (
    DVHBins,
    DVHResultSet,
    MetricResult,
    ProvenanceRecord,
    ROIDiagnostics,
    ROIResult,
    ROIStatus,
)
from pymedphys._dvh._types._roi_ref import ROIRef
from pymedphys._dvh._types._sdf import SDFField


# ---------------------------------------------------------------------------
# 1. MetricRequestSet canonical round-trip (Task 1)
# ---------------------------------------------------------------------------


class TestMetricRequestSetCanonicalRoundTrip:
    """The canonical to_dict() format must be lossless."""

    def test_duplicate_roi_names_different_numbers_survive_round_trip(self) -> None:
        """Two ROIs with the same name but different roi_numbers must
        survive a to_dict()/from_dict() round-trip without data loss."""
        req1 = ROIMetricRequest.from_strings("PTV", ["D95%"], roi_number=1)
        req2 = ROIMetricRequest.from_strings("PTV", ["mean"], roi_number=2)
        mrs = MetricRequestSet(roi_requests=(req1, req2))
        d = mrs.to_dict()
        restored = MetricRequestSet.from_dict(d)
        assert len(restored.roi_requests) == 2
        assert restored.roi_requests[0].roi.name == "PTV"
        assert restored.roi_requests[0].roi.roi_number == 1
        assert restored.roi_requests[1].roi.name == "PTV"
        assert restored.roi_requests[1].roi.roi_number == 2

    def test_metric_metadata_preserved_in_round_trip(self) -> None:
        """MetricSpec.to_dict() metadata must survive the round-trip."""
        spec = MetricSpec.parse("D95%")
        req = ROIMetricRequest(roi=ROIRef(name="PTV"), metrics=(spec,))
        mrs = MetricRequestSet(roi_requests=(req,))
        d = mrs.to_dict()
        restored = MetricRequestSet.from_dict(d)
        restored_spec = restored.roi_requests[0].metrics[0]
        assert restored_spec.family == spec.family
        assert restored_spec.threshold == spec.threshold
        assert restored_spec.threshold_unit == spec.threshold_unit
        assert restored_spec.output_unit == spec.output_unit

    def test_repeated_metrics_same_roi_rejected(self) -> None:
        """Repeated canonical metrics within the same ROI are rejected."""
        spec = MetricSpec.parse("D95%")
        with pytest.raises(ValueError, match="Duplicate metrics"):
            ROIMetricRequest(roi=ROIRef(name="PTV"), metrics=(spec, spec))

    def test_per_roi_dose_ref_id_preserved(self) -> None:
        """Per-ROI dose_ref_id must survive round-trip."""
        dose_refs = DoseReferenceSet(
            refs={"ptv60": DoseReference(dose_gy=60.0, source="prescription dose")},
            default_id="ptv60",
        )
        req = ROIMetricRequest.from_strings("PTV60", ["D95%"], dose_ref_id="ptv60")
        mrs = MetricRequestSet(roi_requests=(req,), dose_refs=dose_refs)
        d = mrs.to_dict()
        restored = MetricRequestSet.from_dict(d)
        assert restored.roi_requests[0].dose_ref_id == "ptv60"

    def test_canonical_format_uses_roi_requests_key(self) -> None:
        """to_dict() must use 'roi_requests', not 'metrics'."""
        req = ROIMetricRequest.from_strings("PTV", ["mean"])
        mrs = MetricRequestSet(roi_requests=(req,))
        d = mrs.to_dict()
        assert "roi_requests" in d
        assert "metrics" not in d

    def test_omits_none_dose_refs(self) -> None:
        """to_dict() must not emit dose_refs/default_dose_ref when unset."""
        req = ROIMetricRequest.from_strings("PTV", ["mean"])
        mrs = MetricRequestSet(roi_requests=(req,))
        d = mrs.to_dict()
        assert "dose_refs" not in d
        assert "default_dose_ref" not in d

    def test_legacy_metrics_format_still_accepted(self) -> None:
        """from_dict() still accepts the legacy name-keyed format."""
        d = {
            "metrics": {
                "PTV": ["D95%", "mean"],
                "OAR": ["D0.03cc"],
            }
        }
        mrs = MetricRequestSet.from_dict(d)
        assert len(mrs.roi_requests) == 2

    def test_from_dict_rejects_missing_both_keys(self) -> None:
        """from_dict() rejects a dict with neither roi_requests nor metrics."""
        with pytest.raises(ValueError, match="roi_requests.*metrics"):
            MetricRequestSet.from_dict({"dose_refs": None})


# ---------------------------------------------------------------------------
# 2. Duplicate ROI detection via ROIRef.matches() (Task 2)
# ---------------------------------------------------------------------------


class TestDuplicateROIDetection:
    """Duplicate detection must use ROIRef.matches() semantics."""

    def test_same_name_different_numbers_allowed(self) -> None:
        """Same name, different roi_number -> distinct ROIs."""
        req1 = ROIMetricRequest.from_strings("PTV", ["D95%"], roi_number=1)
        req2 = ROIMetricRequest.from_strings("PTV", ["mean"], roi_number=2)
        mrs = MetricRequestSet(roi_requests=(req1, req2))
        assert len(mrs.roi_requests) == 2

    def test_same_number_different_names_rejected(self) -> None:
        """Same roi_number, different names -> matches() returns True."""
        req1 = ROIMetricRequest.from_strings("PTV_high", ["D95%"], roi_number=5)
        req2 = ROIMetricRequest.from_strings("PTV_low", ["mean"], roi_number=5)
        with pytest.raises(ValueError, match="Duplicate ROI"):
            MetricRequestSet(roi_requests=(req1, req2))

    def test_same_name_one_numbered_one_not(self) -> None:
        """Same name, one with roi_number, one without -> matches by name."""
        req1 = ROIMetricRequest.from_strings("PTV", ["D95%"], roi_number=1)
        req2 = ROIMetricRequest.from_strings("PTV", ["mean"])
        with pytest.raises(ValueError, match="Duplicate ROI"):
            MetricRequestSet(roi_requests=(req1, req2))

    def test_same_name_no_numbers_rejected(self) -> None:
        """Same name, no numbers -> duplicate."""
        req1 = ROIMetricRequest.from_strings("PTV", ["D95%"])
        req2 = ROIMetricRequest.from_strings("PTV", ["mean"])
        with pytest.raises(ValueError, match="Duplicate ROI"):
            MetricRequestSet(roi_requests=(req1, req2))

    def test_clearly_distinct_rois(self) -> None:
        """Completely different ROIs are fine."""
        req1 = ROIMetricRequest.from_strings("PTV", ["D95%"])
        req2 = ROIMetricRequest.from_strings("OAR", ["mean"])
        mrs = MetricRequestSet(roi_requests=(req1, req2))
        assert len(mrs.roi_requests) == 2


# ---------------------------------------------------------------------------
# 3. NaN/Inf rejection (Tasks 4, 8)
# ---------------------------------------------------------------------------


class TestNaNInfRejection:
    """Non-finite values must be rejected by all domain types."""

    @pytest.fixture()
    def frame(self) -> GridFrame:
        return GridFrame.from_uniform(
            shape_zyx=(2, 2, 2),
            spacing_mm_xyz=(1.0, 1.0, 1.0),
        )

    # Dose references
    def test_dose_ref_rejects_nan(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            DoseReference(dose_gy=float("nan"), source="test source")

    def test_dose_ref_rejects_inf(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            DoseReference(dose_gy=float("inf"), source="test source")

    # Config
    def test_config_dvh_bin_width_rejects_nan(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            AlgorithmConfig(dvh_bin_width_gy=float("nan"))

    def test_config_batch_size_rejects_inf(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            RuntimeConfig(batch_size_gb=float("inf"))

    def test_config_convergence_tol_rejects_nan(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            SupersamplingConfig(adaptive_convergence_tol=float("nan"))

    def test_pipeline_policy_z_tol_rejects_nan(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            PipelinePolicy(z_tolerance_mm=float("nan"))

    # Occupancy
    def test_occupancy_rejects_nan(self, frame: GridFrame) -> None:
        data = np.full((2, 2, 2), 0.5)
        data[0, 0, 0] = float("nan")
        with pytest.raises(ValueError, match="non-finite"):
            OccupancyField(data=data, frame=frame, roi=ROIRef(name="PTV"))

    def test_occupancy_rejects_inf(self, frame: GridFrame) -> None:
        data = np.full((2, 2, 2), 0.5)
        data[0, 0, 0] = float("inf")
        with pytest.raises(ValueError, match="non-finite|range"):
            OccupancyField(data=data, frame=frame, roi=ROIRef(name="PTV"))

    # SDF
    def test_sdf_rejects_nan(self, frame: GridFrame) -> None:
        data = np.zeros((2, 2, 2))
        data[0, 0, 0] = float("nan")
        with pytest.raises(ValueError, match="finite"):
            SDFField(data=data, frame=frame, roi=ROIRef(name="PTV"))

    # DVH bins
    def test_dvh_bins_rejects_nan_edges(self) -> None:
        with pytest.raises(ValueError, match="non-finite"):
            DVHBins(
                dose_bin_edges_gy=np.array([0.0, float("nan"), 2.0]),
                differential_volume_cc=np.array([1.0, 1.0]),
                total_volume_cc=5.0,
            )

    def test_dvh_bins_rejects_inf_total(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            DVHBins(
                dose_bin_edges_gy=np.array([0.0, 1.0, 2.0]),
                differential_volume_cc=np.array([1.0, 1.0]),
                total_volume_cc=float("inf"),
            )

    # MetricResult
    def test_metric_result_rejects_nan_value(self) -> None:
        spec = MetricSpec.parse("D95%")
        with pytest.raises(ValueError, match="finite"):
            MetricResult(spec=spec, value=float("nan"), unit="Gy")

    def test_metric_result_rejects_inf_convergence(self) -> None:
        spec = MetricSpec.parse("D95%")
        with pytest.raises(ValueError, match="finite"):
            MetricResult(
                spec=spec,
                value=50.0,
                unit="Gy",
                convergence_estimate=float("inf"),
            )

    # DVHResultSet
    def test_result_set_rejects_nan_computation_time(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            DVHResultSet(
                schema_version="1.0",
                results=(),
                provenance=ProvenanceRecord(),
                computation_time_s=float("nan"),
            )

    # GridFrame
    def test_grid_frame_rejects_nan_in_affine(self) -> None:
        aff = np.eye(4)
        aff[0, 3] = float("nan")
        with pytest.raises(ValueError, match="non-finite"):
            GridFrame(shape_zyx=(2, 2, 2), index_to_patient_mm=aff)

    # Contour
    def test_contour_rejects_nan_points(self) -> None:
        pts = np.array([[0.0, 0.0], [1.0, 0.0], [float("nan"), 1.0]])
        with pytest.raises(ValueError, match="non-finite"):
            Contour(points_xy=pts, z_mm=0.0)


# ---------------------------------------------------------------------------
# 4. Mutation leakage from caller-owned containers (Task 5)
# ---------------------------------------------------------------------------


class TestMutationLeakage:
    """Frozen dataclass internals must not leak caller mutations."""

    def test_dose_ref_set_dict_mutation(self) -> None:
        """Mutating the caller's dict must not affect DoseReferenceSet."""
        d = {"rx": DoseReference(dose_gy=60.0, source="prescription dose")}
        drs = DoseReferenceSet(refs=d, default_id="rx")
        # Attempt to mutate the caller's dict — should not affect drs
        d["evil"] = DoseReference(dose_gy=1.0, source="evil source")
        assert "evil" not in drs.refs

    def test_dose_ref_set_refs_immutable(self) -> None:
        """DoseReferenceSet.refs must be truly immutable."""
        drs = DoseReferenceSet.single(dose_gy=60.0, source="prescription dose")
        with pytest.raises(TypeError):
            drs.refs["new"] = DoseReference(dose_gy=1.0, source="test ref")  # type: ignore[index]

    def test_roi_metric_request_list_mutation(self) -> None:
        """Passing a list of metrics, then mutating it, must not leak."""
        specs = [MetricSpec.parse("D95%"), MetricSpec.parse("mean")]
        req = ROIMetricRequest(roi=ROIRef(name="PTV"), metrics=specs)  # type: ignore[arg-type]
        specs.append(MetricSpec.parse("min"))
        assert len(req.metrics) == 2

    def test_metric_request_set_list_mutation(self) -> None:
        """Passing a list of roi_requests, then mutating it, must not leak."""
        req = ROIMetricRequest.from_strings("PTV", ["D95%"])
        reqs = [req]
        mrs = MetricRequestSet(roi_requests=reqs)  # type: ignore[arg-type]
        reqs.append(ROIMetricRequest.from_strings("OAR", ["mean"]))
        assert len(mrs.roi_requests) == 1

    def test_roi_result_issues_list_mutation(self) -> None:
        """Passing a list of issues, then mutating it, must not leak."""
        issue = Issue(
            level=IssueLevel.WARNING,
            code=IssueCode.STRUCTURE_VOLUME_SMALL,
            message="test",
        )
        issues = [issue]
        result = ROIResult(
            roi=ROIRef(name="PTV"),
            status=ROIStatus.OK,
            issues=issues,  # type: ignore[arg-type]
        )
        issues.append(issue)
        assert len(result.issues) == 1


# ---------------------------------------------------------------------------
# 5. Fixed-axis GridFrame semantics (Task 6)
# ---------------------------------------------------------------------------


class TestGridFrameAxisContract:
    """GridFrame enforces fixed (z,y,x) -> (x,y,z) axis mapping."""

    def test_valid_fixed_axis_affine(self) -> None:
        """Standard HFS affine passes validation."""
        gf = GridFrame.from_uniform(
            shape_zyx=(5, 10, 15),
            spacing_mm_xyz=(2.0, 2.5, 3.0),
        )
        assert gf.spacing_mm == (3.0, 2.5, 2.0)  # dz, dy, dx

    def test_valid_sign_flipped_affine(self) -> None:
        """Negative spacing (sign flips) is allowed."""
        aff = np.array(
            [
                [0.0, 0.0, -1.0, 10.0],
                [0.0, 2.5, 0.0, -20.0],
                [3.0, 0.0, 0.0, -30.0],
                [0.0, 0.0, 0.0, 1.0],
            ]
        )
        gf = GridFrame(shape_zyx=(5, 10, 15), index_to_patient_mm=aff)
        assert gf.shape_zyx == (5, 10, 15)

    def test_rejects_axis_permuted_affine(self) -> None:
        """Axis permutation (ix->z instead of ix->x) is rejected."""
        # This affine maps ix->z and iz->x (permutation)
        aff = np.array(
            [
                [1.0, 0.0, 0.0, 0.0],  # row 0 (patient x) from col 0 (iz)
                [0.0, 2.5, 0.0, 0.0],  # row 1 (patient y) from col 1 (iy)
                [0.0, 0.0, 3.0, 0.0],  # row 2 (patient z) from col 2 (ix)
                [0.0, 0.0, 0.0, 1.0],
            ]
        )
        with pytest.raises(ValueError, match="permutation"):
            GridFrame(shape_zyx=(5, 10, 15), index_to_patient_mm=aff)

    def test_rejects_non_axis_aligned_affine(self) -> None:
        """Tilted (rotated) affine is rejected."""
        aff = np.array(
            [
                [0.0, 0.0, 1.0, 0.0],
                [0.0, 2.5, 0.5, 0.0],  # off-diagonal
                [3.0, 0.0, 0.0, 0.0],
                [0.0, 0.0, 0.0, 1.0],
            ]
        )
        with pytest.raises(ValueError, match="axis-aligned"):
            GridFrame(shape_zyx=(5, 10, 15), index_to_patient_mm=aff)


# ---------------------------------------------------------------------------
# 6. MetricResult.unit validation (Task 8)
# ---------------------------------------------------------------------------


class TestMetricResultUnitValidation:
    def test_valid_units_accepted(self) -> None:
        spec = MetricSpec.parse("D95%")
        for unit in ("Gy", "percent_dose", "cc", "percent_vol", "dimensionless"):
            MetricResult(spec=spec, value=50.0, unit=unit)

    def test_invalid_unit_rejected(self) -> None:
        spec = MetricSpec.parse("D95%")
        with pytest.raises(ValueError, match="unit"):
            MetricResult(spec=spec, value=50.0, unit="invalid_unit")


# ---------------------------------------------------------------------------
# 7. Timestamp parsing (Task 8)
# ---------------------------------------------------------------------------


class TestTimestampParsing:
    def test_valid_timestamps(self) -> None:
        ProvenanceRecord(timestamp_utc="2024-01-15T10:30:00Z")
        ProvenanceRecord(timestamp_utc="2024-01-15T10:30:00.123Z")
        ProvenanceRecord(timestamp_utc="")

    def test_rejects_non_utc(self) -> None:
        with pytest.raises(ValueError):
            ProvenanceRecord(timestamp_utc="2024-01-15T10:30:00+05:00")

    def test_rejects_malformed(self) -> None:
        with pytest.raises(ValueError):
            ProvenanceRecord(timestamp_utc="not-a-timestamp")

    def test_rejects_impossible_date(self) -> None:
        """Regex passes but datetime parsing should catch invalid date."""
        with pytest.raises(ValueError):
            ProvenanceRecord(timestamp_utc="2024-13-45T99:99:99Z")


# ---------------------------------------------------------------------------
# 8. ROIDiagnostics validation (Task 8)
# ---------------------------------------------------------------------------


class TestROIDiagnosticsValidation:
    def test_rejects_negative_boundary_count(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            ROIDiagnostics(boundary_voxel_count=-1)

    def test_rejects_negative_interior_count(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            ROIDiagnostics(interior_voxel_count=-1)

    def test_rejects_negative_contour_count(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            ROIDiagnostics(contour_slice_count=-1)

    def test_rejects_endcap_fraction_out_of_range(self) -> None:
        with pytest.raises(ValueError, match=r"\[0\.0, 1\.0\]"):
            ROIDiagnostics(endcap_volume_fraction=1.5)

    def test_rejects_nan_computation_time(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            ROIDiagnostics(computation_time_s=float("nan"))

    def test_rejects_nan_gradient(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            ROIDiagnostics(mean_boundary_gradient_gy_per_mm=float("nan"))

    def test_valid_diagnostics(self) -> None:
        diag = ROIDiagnostics(
            effective_supersampling=3,
            boundary_voxel_count=100,
            interior_voxel_count=500,
            mean_boundary_gradient_gy_per_mm=0.5,
            contour_slice_count=10,
            endcap_volume_fraction=0.05,
            computation_time_s=1.5,
        )
        assert diag.contour_slice_count == 10


# ---------------------------------------------------------------------------
# 9. MetricSpec threshold NaN/Inf rejection (review A1)
# ---------------------------------------------------------------------------


class TestMetricSpecThresholdValidation:
    def test_rejects_nan_threshold(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            MetricSpec(
                family=MetricFamily.DVH_DOSE,
                threshold=float("nan"),
                threshold_unit=ThresholdUnit.PERCENT,
                raw="test",
            )

    def test_rejects_inf_threshold(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            MetricSpec(
                family=MetricFamily.DVH_DOSE,
                threshold=float("inf"),
                threshold_unit=ThresholdUnit.PERCENT,
                raw="test",
            )


# ---------------------------------------------------------------------------
# 10. DoseGrid NaN/Inf rejection (review A2)
# ---------------------------------------------------------------------------


class TestDoseGridFiniteValidation:
    @pytest.fixture()
    def frame(self) -> GridFrame:
        return GridFrame.from_uniform(
            shape_zyx=(2, 2, 2),
            spacing_mm_xyz=(1.0, 1.0, 1.0),
        )

    def test_rejects_nan_dose(self, frame: GridFrame) -> None:
        data = np.zeros((2, 2, 2))
        data[0, 0, 0] = float("nan")
        with pytest.raises(ValueError, match="non-finite"):
            DoseGrid(dose_gy=data, frame=frame)

    def test_rejects_inf_dose(self, frame: GridFrame) -> None:
        data = np.zeros((2, 2, 2))
        data[0, 0, 0] = float("inf")
        with pytest.raises(ValueError, match="non-finite"):
            DoseGrid(dose_gy=data, frame=frame)

    def test_rejects_nan_uncertainty(self, frame: GridFrame) -> None:
        dose = np.ones((2, 2, 2))
        unc = np.zeros((2, 2, 2))
        unc[0, 0, 0] = float("nan")
        with pytest.raises(ValueError, match="non-finite"):
            DoseGrid(dose_gy=dose, frame=frame, uncertainty_gy=unc)


# ---------------------------------------------------------------------------
# 11. ROIResult.volume_cc validation (review A3)
# ---------------------------------------------------------------------------


class TestROIResultVolumeValidation:
    def test_rejects_nan_volume(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            ROIResult(
                roi=ROIRef(name="PTV"),
                status=ROIStatus.OK,
                volume_cc=float("nan"),
            )

    def test_rejects_negative_volume(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            ROIResult(
                roi=ROIRef(name="PTV"),
                status=ROIStatus.OK,
                volume_cc=-1.0,
            )

    def test_accepts_zero_volume(self) -> None:
        r = ROIResult(roi=ROIRef(name="PTV"), status=ROIStatus.OK, volume_cc=0.0)
        assert r.volume_cc == 0.0


# ---------------------------------------------------------------------------
# 12. Issue.context immutability (review B1)
# ---------------------------------------------------------------------------


class TestIssueContextImmutability:
    def test_context_mutation_does_not_leak(self) -> None:
        ctx = {"spacing_mm": 4.0}
        issue = Issue(
            level=IssueLevel.WARNING,
            code=IssueCode.STRUCTURE_VOLUME_SMALL,
            message="test",
            context=ctx,
        )
        ctx["evil"] = True
        assert issue.context is not None
        assert "evil" not in issue.context

    def test_context_is_immutable(self) -> None:
        issue = Issue(
            level=IssueLevel.WARNING,
            code=IssueCode.STRUCTURE_VOLUME_SMALL,
            message="test",
            context={"spacing_mm": 4.0},
        )
        with pytest.raises(TypeError):
            issue.context["new_key"] = True  # type: ignore[index]


# ---------------------------------------------------------------------------
# 13. MetricRequestSet default_id round-trip (review C5)
# ---------------------------------------------------------------------------


class TestMetricRequestSetDefaultIdRoundTrip:
    def test_default_id_survives_canonical_round_trip(self) -> None:
        dose_refs = DoseReferenceSet(
            refs={
                "ptv60": DoseReference(dose_gy=60.0, source="prescription dose"),
                "ptv42": DoseReference(dose_gy=42.0, source="boost prescription"),
            },
            default_id="ptv60",
        )
        req = ROIMetricRequest.from_strings("PTV60", ["D95%"], dose_ref_id="ptv60")
        mrs = MetricRequestSet(roi_requests=(req,), dose_refs=dose_refs)
        d = mrs.to_dict()
        restored = MetricRequestSet.from_dict(d)
        assert restored.dose_refs is not None
        assert restored.dose_refs.default_id == "ptv60"


# ---------------------------------------------------------------------------
# 14. ROIRef colour_rgb length validation (review E2)
# ---------------------------------------------------------------------------


class TestROIRefColourValidation:
    def test_rejects_too_few_elements(self) -> None:
        with pytest.raises(ValueError, match="3 elements"):
            ROIRef(name="PTV", colour_rgb=(255, 0))  # type: ignore[arg-type]

    def test_rejects_too_many_elements(self) -> None:
        with pytest.raises(ValueError, match="3 elements"):
            ROIRef(name="PTV", colour_rgb=(255, 0, 0, 128))  # type: ignore[arg-type]
