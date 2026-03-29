"""Regression tests for stacked type-system changes.

Tests cover:
- Item 1: Richer metric AST (IndexMetric, per-metric dose_ref_id, mean[%Rx])
- Item 2: ROIStatus enum coercion, DVHResultSet validation, timestamp validation
- Item 3: MetricResult and ROIDiagnostics validation
- Item 4: DoseReference/DoseReferenceSet validation and immutability
- Item 5: GridFrame.from_dict() integer coercion
- Item 6: DVHBins.__hash__() value semantics
- Item 7: Torus validity policy
"""

from __future__ import annotations

import math
from types import MappingProxyType

import numpy as np
import pytest

from pymedphys._dvh._benchmarks._geometry import torus_volume
from pymedphys._dvh._types._config import DVHConfig
from pymedphys._dvh._types._dose_ref import DoseReference, DoseReferenceSet
from pymedphys._dvh._types._grid_frame import GridFrame
from pymedphys._dvh._types._issues import Issue, IssueCode, IssueLevel
from pymedphys._dvh._types._metrics import (
    IndexMetric,
    MetricFamily,
    MetricRequestSet,
    MetricSpec,
    OutputUnit,
    ROIMetricRequest,
    ThresholdUnit,
)
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


# ── Item 1: Richer metric AST ─────────────────────────────────────


class TestIndexMetricEnum:
    """Tests for the typed IndexMetric enum."""

    def test_all_index_metrics_present(self) -> None:
        assert set(IndexMetric) == {
            IndexMetric.HI,
            IndexMetric.CI,
            IndexMetric.PCI,
            IndexMetric.GI,
        }

    def test_hi_does_not_require_dose_ref(self) -> None:
        assert IndexMetric.HI.requires_dose_ref is False

    def test_ci_requires_dose_ref(self) -> None:
        assert IndexMetric.CI.requires_dose_ref is True

    def test_pci_requires_dose_ref(self) -> None:
        assert IndexMetric.PCI.requires_dose_ref is True

    def test_gi_requires_dose_ref(self) -> None:
        assert IndexMetric.GI.requires_dose_ref is True


class TestIndexMetricParsing:
    """Tests for typed index metric construction via parse()."""

    def test_parse_hi_sets_index_metric(self) -> None:
        spec = MetricSpec.parse("HI")
        assert spec.index_metric == IndexMetric.HI
        assert spec.family == MetricFamily.INDEX

    def test_parse_ci_sets_index_metric(self) -> None:
        spec = MetricSpec.parse("CI")
        assert spec.index_metric == IndexMetric.CI

    def test_parse_pci_sets_index_metric(self) -> None:
        spec = MetricSpec.parse("PCI")
        assert spec.index_metric == IndexMetric.PCI

    def test_parse_gi_sets_index_metric(self) -> None:
        spec = MetricSpec.parse("GI")
        assert spec.index_metric == IndexMetric.GI

    def test_index_metric_round_trip_via_dict(self) -> None:
        spec = MetricSpec.parse("CI")
        d = spec.to_dict()
        assert d["index_metric"] == "CI"
        restored = MetricSpec.from_dict(d)
        assert restored.index_metric == IndexMetric.CI
        assert restored.family == MetricFamily.INDEX

    def test_requires_dose_ref_uses_typed_enum(self) -> None:
        """requires_dose_ref should use IndexMetric, not raw string."""
        spec = MetricSpec(
            family=MetricFamily.INDEX,
            output_unit=OutputUnit.DIMENSIONLESS,
            raw="CI",
            index_metric=IndexMetric.CI,
        )
        assert spec.requires_dose_ref is True

    def test_implicit_index_metric_inference_from_raw(self) -> None:
        """__post_init__ infers IndexMetric from raw when not explicitly set."""
        spec = MetricSpec(
            family=MetricFamily.INDEX,
            output_unit=OutputUnit.DIMENSIONLESS,
            raw="CI",
        )
        assert spec.index_metric == IndexMetric.CI
        assert spec.requires_dose_ref is True

    def test_implicit_hi_inference_does_not_require_dose_ref(self) -> None:
        """HI inferred from raw should not require a dose ref."""
        spec = MetricSpec(
            family=MetricFamily.INDEX,
            output_unit=OutputUnit.DIMENSIONLESS,
            raw="HI",
        )
        assert spec.index_metric == IndexMetric.HI
        assert spec.requires_dose_ref is False


class TestPerMetricDoseRef:
    """Tests for per-metric dose_ref_id override."""

    def test_metric_level_invalid_dose_ref_id_raises(self) -> None:
        """MetricSpec with unknown dose_ref_id should raise ValueError."""
        dose_refs = DoseReferenceSet(
            refs={
                "ptv60": DoseReference(60.0, "PTV60 prescription dose"),
            },
            default_id="ptv60",
        )
        spec = MetricSpec(
            family=MetricFamily.INDEX,
            output_unit=OutputUnit.DIMENSIONLESS,
            raw="CI",
            index_metric=IndexMetric.CI,
            dose_ref_id="missing",
        )
        req = ROIMetricRequest(
            roi=ROIRef(name="PTV"),
            metrics=(spec,),
        )
        with pytest.raises(ValueError, match="missing.*not found"):
            MetricRequestSet(roi_requests=(req,), dose_refs=dose_refs)

    def test_metric_level_dose_ref_overrides_roi(self) -> None:
        """metric.dose_ref_id takes precedence over roi_request.dose_ref_id."""
        dose_refs = DoseReferenceSet(
            refs={
                "ptv60": DoseReference(60.0, "PTV60 prescription dose"),
                "ptv42": DoseReference(42.0, "PTV42 prescription dose"),
            },
            default_id="ptv60",
        )
        # Metric explicitly references ptv42, overriding ROI's ptv60
        spec = MetricSpec(
            family=MetricFamily.DVH_VOLUME,
            threshold=95.0,
            threshold_unit=ThresholdUnit.PERCENT,
            output_unit=OutputUnit.CC,
            raw="V95%",
            dose_ref_id="ptv42",
        )
        req = ROIMetricRequest(
            roi=ROIRef(name="PTV"),
            metrics=(spec,),
            dose_ref_id="ptv60",
        )
        # Should not raise — ptv42 exists in dose_refs
        mrs = MetricRequestSet(roi_requests=(req,), dose_refs=dose_refs)
        assert mrs.roi_requests[0].metrics[0].dose_ref_id == "ptv42"

    def test_metric_dose_ref_id_serialises_round_trip(self) -> None:
        spec = MetricSpec(
            family=MetricFamily.SCALAR,
            raw="mean",
            dose_ref_id="ptv42",
        )
        d = spec.to_dict()
        assert d["dose_ref_id"] == "ptv42"
        restored = MetricSpec.from_dict(d)
        assert restored.dose_ref_id == "ptv42"

    def test_metric_dose_ref_id_absent_when_none(self) -> None:
        spec = MetricSpec(family=MetricFamily.SCALAR, raw="mean")
        d = spec.to_dict()
        assert "dose_ref_id" not in d

    def test_mixed_metrics_with_different_dose_refs(self) -> None:
        """Mixed metrics within one ROI using different dose refs."""
        dose_refs = DoseReferenceSet(
            refs={
                "ptv60": DoseReference(60.0, "PTV60 prescription dose"),
                "ptv42": DoseReference(42.0, "PTV42 prescription dose"),
            },
            default_id="ptv60",
        )
        # First metric uses ptv42, second uses ROI-level default (ptv60)
        spec1 = MetricSpec.parse("V95%")
        object.__setattr__(spec1, "dose_ref_id", "ptv42")
        spec2 = MetricSpec.parse("D95%[%Rx]")  # needs dose ref
        req = ROIMetricRequest(
            roi=ROIRef(name="PTV"),
            metrics=(spec1, spec2),
            dose_ref_id="ptv60",
        )
        mrs = MetricRequestSet(roi_requests=(req,), dose_refs=dose_refs)
        assert len(mrs.roi_requests[0].metrics) == 2


class TestMeanPercentRx:
    """Tests for mean[%Rx] parsing and round-trip."""

    def test_parse_mean_percent_rx(self) -> None:
        spec = MetricSpec.parse("mean[%Rx]")
        assert spec.family == MetricFamily.SCALAR
        assert spec.output_unit == OutputUnit.PERCENT_DOSE

    def test_mean_percent_rx_requires_dose_ref(self) -> None:
        spec = MetricSpec.parse("mean[%Rx]")
        assert spec.requires_dose_ref is True

    def test_mean_percent_rx_round_trip(self) -> None:
        spec = MetricSpec.parse("mean[%Rx]")
        d = spec.to_dict()
        restored = MetricSpec.from_dict(d)
        assert restored.family == MetricFamily.SCALAR
        assert restored.output_unit == OutputUnit.PERCENT_DOSE
        assert restored.raw == "mean[%Rx]"


# ── Item 2: ROIStatus enum, DVHResultSet validation, timestamps ───


class TestROIStatusEnum:
    """Tests for ROIStatus enum and string coercion."""

    def test_valid_statuses(self) -> None:
        assert ROIStatus.OK.value == "ok"
        assert ROIStatus.SKIPPED.value == "skipped"
        assert ROIStatus.FAILED.value == "failed"

    def test_string_coercion_to_enum(self) -> None:
        result = ROIResult(roi=ROIRef(name="PTV"), status="ok")
        assert isinstance(result.status, ROIStatus)
        assert result.status == ROIStatus.OK

    def test_enum_value_accepted(self) -> None:
        result = ROIResult(roi=ROIRef(name="PTV"), status=ROIStatus.SKIPPED)
        assert result.status == ROIStatus.SKIPPED

    def test_invalid_status_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be one of"):
            ROIResult(roi=ROIRef(name="PTV"), status="invalid_status")

    def test_status_serialises_as_string(self) -> None:
        result = ROIResult(roi=ROIRef(name="PTV"), status=ROIStatus.OK)
        d = result.to_dict()
        assert d["status"] == "ok"

    def test_status_deserialises_from_string(self) -> None:
        d = {"roi": {"name": "PTV"}, "status": "failed"}
        result = ROIResult.from_dict(d)
        assert result.status == ROIStatus.FAILED


class TestDVHResultSetValidation:
    """Tests for DVHResultSet.__post_init__ validation."""

    def _make_provenance(self) -> ProvenanceRecord:
        return ProvenanceRecord(
            pymedphys_version="0.1.0",
            timestamp_utc="2024-01-01T00:00:00Z",
        )

    def test_rejects_unsupported_schema_version(self) -> None:
        with pytest.raises(ValueError, match="Unsupported schema_version"):
            DVHResultSet(
                schema_version="99.0",
                results=(),
                provenance=self._make_provenance(),
                computation_time_s=1.0,
            )

    def test_accepts_supported_schema_version(self) -> None:
        rs = DVHResultSet(
            schema_version="1.0",
            results=(),
            provenance=self._make_provenance(),
            computation_time_s=1.0,
        )
        assert rs.schema_version == "1.0"

    def test_rejects_negative_computation_time(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            DVHResultSet(
                schema_version="1.0",
                results=(),
                provenance=self._make_provenance(),
                computation_time_s=-1.0,
            )

    def test_rejects_nan_computation_time(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            DVHResultSet(
                schema_version="1.0",
                results=(),
                provenance=self._make_provenance(),
                computation_time_s=float("nan"),
            )

    def test_rejects_inf_computation_time(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            DVHResultSet(
                schema_version="1.0",
                results=(),
                provenance=self._make_provenance(),
                computation_time_s=float("inf"),
            )


class TestProvenanceTimestampValidation:
    """Tests for ProvenanceRecord timestamp validation."""

    def test_accepts_valid_iso8601_utc(self) -> None:
        p = ProvenanceRecord(timestamp_utc="2024-01-15T10:30:00Z")
        assert p.timestamp_utc == "2024-01-15T10:30:00Z"

    def test_accepts_valid_iso8601_with_offset(self) -> None:
        p = ProvenanceRecord(timestamp_utc="2024-01-15T10:30:00+05:30")
        assert p.timestamp_utc == "2024-01-15T10:30:00+05:30"

    def test_accepts_valid_iso8601_with_fractional_seconds(self) -> None:
        p = ProvenanceRecord(timestamp_utc="2024-01-15T10:30:00.123Z")
        assert p.timestamp_utc == "2024-01-15T10:30:00.123Z"

    def test_accepts_empty_string(self) -> None:
        p = ProvenanceRecord(timestamp_utc="")
        assert p.timestamp_utc == ""

    def test_rejects_invalid_timestamp(self) -> None:
        with pytest.raises(ValueError, match="ISO 8601"):
            ProvenanceRecord(timestamp_utc="not-a-timestamp")

    def test_rejects_date_only(self) -> None:
        with pytest.raises(ValueError, match="timezone"):
            ProvenanceRecord(timestamp_utc="2024-01-15")

    def test_rejects_timestamp_without_timezone(self) -> None:
        with pytest.raises(ValueError, match="timezone"):
            ProvenanceRecord(timestamp_utc="2024-01-15T10:30:00")


# ── Item 3: MetricResult and ROIDiagnostics validation ────────────


class TestMetricResultValidation:
    """Tests for MetricResult.__post_init__ validation."""

    def _make_spec(self) -> MetricSpec:
        return MetricSpec(family=MetricFamily.SCALAR, raw="mean")

    def test_rejects_nan_value(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            MetricResult(spec=self._make_spec(), value=float("nan"), unit="Gy")

    def test_rejects_inf_value(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            MetricResult(spec=self._make_spec(), value=float("inf"), unit="Gy")

    def test_accepts_none_value(self) -> None:
        r = MetricResult(spec=self._make_spec(), value=None, unit="Gy")
        assert r.value is None

    def test_rejects_nan_convergence_estimate(self) -> None:
        with pytest.raises(ValueError, match="convergence_estimate"):
            MetricResult(
                spec=self._make_spec(),
                value=1.0,
                unit="Gy",
                convergence_estimate=float("nan"),
            )

    def test_rejects_invalid_unit(self) -> None:
        with pytest.raises(ValueError, match="unit"):
            MetricResult(spec=self._make_spec(), value=1.0, unit="invalid_unit")

    def test_accepts_valid_units(self) -> None:
        # Valid units are derived from OutputUnit enum values plus ""
        for unit in ("Gy", "percent_dose", "cc", "percent_vol", "dimensionless", ""):
            r = MetricResult(spec=self._make_spec(), value=1.0, unit=unit)
            assert r.unit == unit


class TestROIDiagnosticsValidation:
    """Tests for ROIDiagnostics.__post_init__ validation."""

    def test_rejects_negative_boundary_voxel_count(self) -> None:
        with pytest.raises(ValueError, match="non-negative integer"):
            ROIDiagnostics(boundary_voxel_count=-1)

    def test_rejects_negative_interior_voxel_count(self) -> None:
        with pytest.raises(ValueError, match="non-negative integer"):
            ROIDiagnostics(interior_voxel_count=-5)

    def test_rejects_negative_computation_time(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            ROIDiagnostics(computation_time_s=-0.1)

    def test_rejects_nan_gradient(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            ROIDiagnostics(mean_boundary_gradient_gy_per_mm=float("nan"))

    def test_rejects_endcap_fraction_above_one(self) -> None:
        with pytest.raises(ValueError, match=r"\[0, 1\]"):
            ROIDiagnostics(endcap_volume_fraction=1.5)

    def test_rejects_negative_endcap_fraction(self) -> None:
        with pytest.raises(ValueError, match=r"\[0, 1\]"):
            ROIDiagnostics(endcap_volume_fraction=-0.1)

    def test_accepts_valid_diagnostics(self) -> None:
        diag = ROIDiagnostics(
            effective_supersampling=3,
            boundary_voxel_count=100,
            interior_voxel_count=500,
            mean_boundary_gradient_gy_per_mm=0.5,
            contour_slice_count=10,
            endcap_volume_fraction=0.02,
            computation_time_s=1.5,
        )
        assert diag.effective_supersampling == 3
        assert diag.endcap_volume_fraction == 0.02


# ── Item 4: DoseReference/DoseReferenceSet validation ─────────────


class TestDoseReferenceValidation:
    """Tests for strengthened DoseReference validation."""

    def test_rejects_nan_dose(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            DoseReference(dose_gy=float("nan"), source="valid source text")

    def test_rejects_inf_dose(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            DoseReference(dose_gy=float("inf"), source="valid source text")

    def test_rejects_neg_inf_dose(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            DoseReference(dose_gy=float("-inf"), source="valid source text")

    def test_rejects_source_without_alphabetic(self) -> None:
        with pytest.raises(ValueError, match="alphabetic"):
            DoseReference(dose_gy=60.0, source="12345")

    def test_accepts_source_with_alpha(self) -> None:
        ref = DoseReference(dose_gy=60.0, source="dose 60 Gy")
        assert ref.source == "dose 60 Gy"


class TestDoseReferenceSetImmutability:
    """Tests for DoseReferenceSet immutability via MappingProxyType."""

    def test_refs_is_mapping_proxy(self) -> None:
        drs = DoseReferenceSet.single(42.0, "prescription: 3 fx x 14 Gy")
        assert isinstance(drs.refs, MappingProxyType)

    def test_caller_mutation_does_not_affect_stored_refs(self) -> None:
        original = {"ptv60": DoseReference(60.0, "PTV60 prescription dose")}
        drs = DoseReferenceSet(refs=original)
        # Mutate the original dict
        original["ptv42"] = DoseReference(42.0, "PTV42 prescription dose")
        # DoseReferenceSet should not be affected
        assert "ptv42" not in drs.refs
        assert len(drs.refs) == 1

    def test_stored_refs_cannot_be_mutated(self) -> None:
        drs = DoseReferenceSet.single(42.0, "prescription: 3 fx x 14 Gy")
        with pytest.raises(TypeError):
            drs.refs["new_key"] = DoseReference(  # type: ignore[index]
                10.0, "should not work"
            )

    def test_rejects_empty_string_key(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            DoseReferenceSet(refs={"": DoseReference(60.0, "valid source text")})

    def test_rejects_whitespace_only_key(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            DoseReferenceSet(refs={"   ": DoseReference(60.0, "valid source text")})


# ── Item 5: GridFrame.from_dict() integer coercion ────────────────


class TestGridFrameFromDictIntegerCoercion:
    """Tests for GridFrame.from_dict() integer coercion."""

    def test_float_shape_coerced_to_int(self) -> None:
        d = {
            "shape_zyx": [10.0, 20.0, 30.0],
            "index_to_patient_mm": [
                [0, 0, 1.0, 0],
                [0, 1.0, 0, 0],
                [1.0, 0, 0, 0],
                [0, 0, 0, 1],
            ],
        }
        gf = GridFrame.from_dict(d)
        assert gf.shape_zyx == (10, 20, 30)
        assert all(isinstance(v, int) for v in gf.shape_zyx)

    def test_string_shape_coerced_to_int(self) -> None:
        """JSON may deserialise integers as strings in some contexts."""
        d = {
            "shape_zyx": ["5", "5", "5"],
            "index_to_patient_mm": [
                [0, 0, 1.0, 0],
                [0, 1.0, 0, 0],
                [1.0, 0, 0, 0],
                [0, 0, 0, 1],
            ],
        }
        gf = GridFrame.from_dict(d)
        assert gf.shape_zyx == (5, 5, 5)

    def test_rejects_non_integer_shape(self) -> None:
        """Non-integer shape values (e.g. 5.5) should be rejected, not truncated."""
        d = {
            "shape_zyx": [5.5, 10, 20],
            "index_to_patient_mm": [
                [0, 0, 1.0, 0],
                [0, 1.0, 0, 0],
                [1.0, 0, 0, 0],
                [0, 0, 0, 1],
            ],
        }
        with pytest.raises(ValueError, match="integers"):
            GridFrame.from_dict(d)

    def test_rejects_negative_shape_in_from_dict(self) -> None:
        d = {
            "shape_zyx": [-5, 10, 20],
            "index_to_patient_mm": [
                [0, 0, 1.0, 0],
                [0, 1.0, 0, 0],
                [1.0, 0, 0, 0],
                [0, 0, 0, 1],
            ],
        }
        with pytest.raises(ValueError, match="positive"):
            GridFrame.from_dict(d)


class TestGridFrameAxisPermutationPolicy:
    """Tests confirming axis permutation is allowed."""

    def test_from_uniform_uses_permuted_affine(self) -> None:
        gf = GridFrame.from_uniform(
            shape_zyx=(5, 5, 5),
            spacing_xyz_mm=(1.0, 2.0, 3.0),
            origin_xyz_mm=(0.0, 0.0, 0.0),
        )
        # The affine has non-zero entries in permuted positions
        assert gf.index_to_patient_mm[2, 0] != 0  # iz maps to z
        assert gf.index_to_patient_mm[1, 1] != 0  # iy maps to y
        assert gf.index_to_patient_mm[0, 2] != 0  # ix maps to x

    def test_sign_flipped_affine_accepted(self) -> None:
        aff = np.array(
            [
                [0, 0, -1.0, 10],
                [0, 1.0, 0, 0],
                [1.0, 0, 0, 0],
                [0, 0, 0, 1],
            ],
            dtype=np.float64,
        )
        gf = GridFrame(shape_zyx=(5, 5, 5), index_to_patient_mm=aff)
        assert gf.shape_zyx == (5, 5, 5)


# ── Item 6: DVHBins.__hash__() value semantics ───────────────────


class TestDVHBinsHashSemantics:
    """Tests for DVHBins hash/equality consistency."""

    def test_equal_objects_have_equal_hashes(self) -> None:
        dvh1 = DVHBins(
            dose_bin_edges_gy=np.array([0.0, 1.0, 2.0]),
            differential_volume_cc=np.array([3.0, 2.0]),
            total_volume_cc=5.0,
        )
        dvh2 = DVHBins(
            dose_bin_edges_gy=np.array([0.0, 1.0, 2.0]),
            differential_volume_cc=np.array([3.0, 2.0]),
            total_volume_cc=5.0,
        )
        assert dvh1 == dvh2
        assert hash(dvh1) == hash(dvh2)

    def test_different_diff_volume_different_hash(self) -> None:
        dvh1 = DVHBins(
            dose_bin_edges_gy=np.array([0.0, 1.0, 2.0]),
            differential_volume_cc=np.array([3.0, 2.0]),
            total_volume_cc=5.0,
        )
        dvh2 = DVHBins(
            dose_bin_edges_gy=np.array([0.0, 1.0, 2.0]),
            differential_volume_cc=np.array([1.0, 4.0]),
            total_volume_cc=5.0,
        )
        assert dvh1 != dvh2
        # Hash collision is theoretically possible but extremely unlikely
        assert hash(dvh1) != hash(dvh2)

    def test_different_total_volume_different_hash(self) -> None:
        dvh1 = DVHBins(
            dose_bin_edges_gy=np.array([0.0, 1.0, 2.0]),
            differential_volume_cc=np.array([3.0, 2.0]),
            total_volume_cc=5.0,
        )
        dvh2 = DVHBins(
            dose_bin_edges_gy=np.array([0.0, 1.0, 2.0]),
            differential_volume_cc=np.array([3.0, 2.0]),
            total_volume_cc=10.0,
        )
        assert dvh1 != dvh2
        assert hash(dvh1) != hash(dvh2)

    def test_hashable_objects_work_in_set(self) -> None:
        dvh1 = DVHBins(
            dose_bin_edges_gy=np.array([0.0, 1.0, 2.0]),
            differential_volume_cc=np.array([3.0, 2.0]),
            total_volume_cc=5.0,
        )
        dvh2 = DVHBins(
            dose_bin_edges_gy=np.array([0.0, 1.0, 2.0]),
            differential_volume_cc=np.array([3.0, 2.0]),
            total_volume_cc=5.0,
        )
        assert len({dvh1, dvh2}) == 1


# ── Item 7: Torus validity policy ────────────────────────────────


class TestTorusValidityPolicy:
    """Tests for simple torus restriction (R > r)."""

    def test_valid_simple_torus(self) -> None:
        v = torus_volume(20.0, 5.0)
        expected = 2.0 * np.pi**2 * 20.0 * 25.0
        assert v == pytest.approx(expected, rel=1e-12)

    def test_rejects_horn_torus_R_equals_r(self) -> None:
        with pytest.raises(ValueError, match="strictly greater"):
            torus_volume(10.0, 10.0)

    def test_rejects_spindle_torus_R_less_than_r(self) -> None:
        with pytest.raises(ValueError, match="strictly greater"):
            torus_volume(5.0, 10.0)


# ── Additional regression tests (review round 2) ─────────────────


class TestIndexMetricCanonicalKeyDistinct:
    """TEST-1: Multiple index metrics must coexist in same ROI."""

    def test_hi_and_ci_have_different_canonical_keys(self) -> None:
        hi = MetricSpec.parse("HI")
        ci = MetricSpec.parse("CI")
        assert hi.canonical_key != ci.canonical_key

    def test_multiple_index_metrics_in_same_roi(self) -> None:
        hi = MetricSpec.parse("HI")
        ci = MetricSpec.parse("CI")
        pci = MetricSpec.parse("PCI")
        gi = MetricSpec.parse("GI")
        dose_refs = DoseReferenceSet.single(60.0, "prescription: 30 fx x 2 Gy")
        req = ROIMetricRequest(roi=ROIRef(name="PTV"), metrics=(hi, ci, pci, gi))
        mrs = MetricRequestSet(roi_requests=(req,), dose_refs=dose_refs)
        assert len(mrs.roi_requests[0].metrics) == 4


class TestMeanAndMeanPercentRxCoexistence:
    """TEST-4: mean and mean[%Rx] can coexist in same ROI."""

    def test_mean_and_mean_percent_rx_different_canonical_keys(self) -> None:
        m1 = MetricSpec.parse("mean")
        m2 = MetricSpec.parse("mean[%Rx]")
        assert m1.canonical_key != m2.canonical_key

    def test_mean_and_mean_percent_rx_in_same_roi(self) -> None:
        m1 = MetricSpec.parse("mean")
        m2 = MetricSpec.parse("mean[%Rx]")
        dose_refs = DoseReferenceSet.single(60.0, "prescription: 30 fx x 2 Gy")
        req = ROIMetricRequest(roi=ROIRef(name="PTV"), metrics=(m1, m2))
        mrs = MetricRequestSet(roi_requests=(req,), dose_refs=dose_refs)
        assert len(mrs.roi_requests[0].metrics) == 2


class TestROIDiagnosticsRejectsBool:
    """TEST-7 + DESIGN-5: bool values rejected for integer count fields."""

    def test_rejects_bool_boundary_voxel_count(self) -> None:
        with pytest.raises(ValueError, match="non-negative integer"):
            ROIDiagnostics(boundary_voxel_count=True)

    def test_rejects_bool_false_as_voxel_count(self) -> None:
        with pytest.raises(ValueError, match="non-negative integer"):
            ROIDiagnostics(interior_voxel_count=False)


class TestGridFrameFromDictZeroShape:
    """TEST-7: GridFrame.from_dict rejects zero shape elements."""

    def test_rejects_zero_shape_element(self) -> None:
        d = {
            "shape_zyx": [0, 10, 20],
            "index_to_patient_mm": [
                [0, 0, 1.0, 0],
                [0, 1.0, 0, 0],
                [1.0, 0, 0, 0],
                [0, 0, 0, 1],
            ],
        }
        with pytest.raises(ValueError, match="positive"):
            GridFrame.from_dict(d)


class TestUnknownIndexMetricRejected:
    """DESIGN-2: Unknown index metric raw string is rejected."""

    def test_rejects_unknown_index_metric(self) -> None:
        with pytest.raises(ValueError, match="known index_metric"):
            MetricSpec(
                family=MetricFamily.INDEX,
                output_unit=OutputUnit.DIMENSIONLESS,
                raw="UNKNOWN_INDEX",
            )
