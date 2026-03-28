"""Tests for JSON/TOML serialisation round-trips.

Every serialisable type is tested for: construct → to_dict() → from_dict() → assert equal.
Top-level to_json/from_json wrappers are tested on DVHResultSet.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from pymedphys._dvh._serialisation import from_json, to_json
from pymedphys._dvh._types._config import (
    DVHConfig,
    EndCapPolicy,
    InterpolationMethod,
)
from pymedphys._dvh._types._dose_ref import DoseReference, DoseReferenceSet
from pymedphys._dvh._types._grid_frame import GridFrame
from pymedphys._dvh._types._issues import Issue, IssueCode, IssueLevel
from pymedphys._dvh._types._metrics import (
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
    InputMetadata,
    MetricResult,
    PlatformInfo,
    ProvenanceRecord,
    ROIDiagnostics,
    ROIResult,
)
from pymedphys._dvh._types._roi_ref import ROIRef


# ---------------------------------------------------------------------------
# Leaf types
# ---------------------------------------------------------------------------


class TestROIRefRoundTrip:
    def test_minimal(self) -> None:
        ref = ROIRef(name="PTV")
        d = ref.to_dict()
        restored = ROIRef.from_dict(d)
        assert restored.name == ref.name
        assert restored.roi_number is None
        assert restored.colour_rgb is None

    def test_with_all_fields(self) -> None:
        ref = ROIRef(name="PTV", roi_number=3, colour_rgb=(255, 0, 0))
        d = ref.to_dict()
        restored = ROIRef.from_dict(d)
        assert restored.name == "PTV"
        assert restored.roi_number == 3
        assert restored.colour_rgb == (255, 0, 0)

    def test_json_serialisable(self) -> None:
        ref = ROIRef(name="PTV", roi_number=3, colour_rgb=(255, 0, 0))
        s = json.dumps(ref.to_dict())
        restored = ROIRef.from_dict(json.loads(s))
        assert restored.name == "PTV"


class TestDoseReferenceRoundTrip:
    def test_round_trip(self) -> None:
        ref = DoseReference(dose_gy=60.0, source="prescription: 30 fx x 2 Gy")
        d = ref.to_dict()
        restored = DoseReference.from_dict(d)
        assert restored.dose_gy == ref.dose_gy
        assert restored.source == ref.source


class TestDoseReferenceSetRoundTrip:
    def test_round_trip(self) -> None:
        drs = DoseReferenceSet(
            refs={
                "ptv60": DoseReference(60.0, "PTV60 prescription dose"),
                "ptv42": DoseReference(42.0, "PTV42 prescription dose"),
            },
            default_id="ptv60",
        )
        d = drs.to_dict()
        restored = DoseReferenceSet.from_dict(d)
        assert restored.default_id == "ptv60"
        assert restored.refs["ptv60"].dose_gy == 60.0
        assert restored.refs["ptv42"].dose_gy == 42.0

    def test_single_round_trip(self) -> None:
        drs = DoseReferenceSet.single(42.0, "prescription: 3 fx x 14 Gy")
        d = drs.to_dict()
        restored = DoseReferenceSet.from_dict(d)
        assert restored.default_id == "default"


class TestIssueRoundTrip:
    def test_round_trip(self) -> None:
        issue = Issue(
            level=IssueLevel.WARNING,
            code=IssueCode.DOSE_GRID_COARSE,
            message="Dose grid spacing exceeds 3mm",
            path=("PTV60", "D95%"),
            context={"spacing_mm": 4.0},
        )
        d = issue.to_dict()
        restored = Issue.from_dict(d)
        assert restored.level == IssueLevel.WARNING
        assert restored.code == IssueCode.DOSE_GRID_COARSE
        assert restored.message == issue.message
        assert restored.path == ("PTV60", "D95%")
        assert restored.context == {"spacing_mm": 4.0}

    def test_minimal(self) -> None:
        issue = Issue(
            level=IssueLevel.INFO,
            code=IssueCode.Z_TOLERANCE_APPLIED,
            message="ok",
        )
        d = issue.to_dict()
        restored = Issue.from_dict(d)
        assert not restored.path
        assert restored.context is None


# ---------------------------------------------------------------------------
# Metric types
# ---------------------------------------------------------------------------


class TestMetricSpecRoundTrip:
    def test_dvh_dose(self) -> None:
        spec = MetricSpec(
            family=MetricFamily.DVH_DOSE,
            threshold=95.0,
            threshold_unit=ThresholdUnit.PERCENT,
            output_unit=OutputUnit.GY,
            raw="D95%",
        )
        d = spec.to_dict()
        restored = MetricSpec.from_dict(d)
        assert restored.family == MetricFamily.DVH_DOSE
        assert restored.threshold == 95.0
        assert restored.threshold_unit == ThresholdUnit.PERCENT
        assert restored.output_unit == OutputUnit.GY
        assert restored.raw == "D95%"

    def test_scalar(self) -> None:
        spec = MetricSpec(family=MetricFamily.SCALAR, raw="mean")
        d = spec.to_dict()
        restored = MetricSpec.from_dict(d)
        assert restored.family == MetricFamily.SCALAR
        assert restored.threshold is None


class TestMetricRequestSetRoundTrip:
    def test_simple_format(self) -> None:
        mrs = MetricRequestSet.from_dict(
            {
                "dose_ref_gy": 42.0,
                "dose_ref_source": "prescription: 3 fx x 14 Gy",
                "metrics": {
                    "PTV42": ["D95%", "D99%"],
                    "SpinalCanal": ["D0.03cc"],
                },
            }
        )
        d = mrs.to_dict()
        # Round-trip uses list format with roi_requests key
        assert "roi_requests" in d
        restored = MetricRequestSet.from_dict(d)
        assert len(restored.roi_requests) == 2
        assert restored.dose_refs is not None

    def test_sib_format(self) -> None:
        mrs = MetricRequestSet.from_dict(
            {
                "dose_refs": {
                    "ptv60": {"dose_gy": 60.0, "source": "PTV60 prescription dose"},
                    "ptv42": {"dose_gy": 42.0, "source": "PTV42 prescription dose"},
                },
                "default_dose_ref": "ptv60",
                "metrics": {
                    "PTV60": {"metrics": ["D95%"], "dose_ref": "ptv60"},
                    "PTV42": {"metrics": ["D95%", "mean"], "dose_ref": "ptv42"},
                },
            }
        )
        d = mrs.to_dict()
        restored = MetricRequestSet.from_dict(d)
        assert len(restored.roi_requests) == 2
        assert restored.dose_refs is not None
        assert "ptv60" in restored.dose_refs.refs

    def test_round_trip_preserves_roi_number(self) -> None:
        """to_dict() must preserve roi_number for identity."""
        req = ROIMetricRequest(
            roi=ROIRef(name="PTV", roi_number=7),
            metrics=(MetricSpec.parse("D95%"),),
        )
        mrs = MetricRequestSet(roi_requests=(req,))
        d = mrs.to_dict()
        restored = MetricRequestSet.from_dict(d)
        assert restored.roi_requests[0].roi.roi_number == 7


# ---------------------------------------------------------------------------
# GridFrame (numpy array handling)
# ---------------------------------------------------------------------------


class TestGridFrameRoundTrip:
    def test_round_trip(self) -> None:
        gf = GridFrame.from_uniform(
            shape_zyx=(10, 20, 30),
            spacing_xyz_mm=(2.5, 3.0, 1.5),
            origin_xyz_mm=(-10.0, -20.0, -30.0),
        )
        d = gf.to_dict()
        restored = GridFrame.from_dict(d)
        assert restored.shape_zyx == gf.shape_zyx
        np.testing.assert_array_equal(
            restored.index_to_patient_mm, gf.index_to_patient_mm
        )

    def test_json_serialisable(self) -> None:
        gf = GridFrame.from_uniform(
            shape_zyx=(5, 5, 5),
            spacing_xyz_mm=(1.0, 1.0, 1.0),
            origin_xyz_mm=(0.0, 0.0, 0.0),
        )
        s = json.dumps(gf.to_dict())
        restored = GridFrame.from_dict(json.loads(s))
        assert restored == gf


# ---------------------------------------------------------------------------
# Config types
# ---------------------------------------------------------------------------


class TestDVHConfigRoundTrip:
    def test_default(self) -> None:
        cfg = DVHConfig()
        d = cfg.to_dict()
        restored = DVHConfig.from_dict(d)
        assert restored.algorithm.dvh_bin_width_gy == cfg.algorithm.dvh_bin_width_gy
        assert restored.runtime.deterministic == cfg.runtime.deterministic

    def test_reference_profile(self) -> None:
        cfg = DVHConfig.reference()
        d = cfg.to_dict()
        restored = DVHConfig.from_dict(d)
        assert (
            restored.algorithm.interpolation_method == InterpolationMethod.SHAPE_BASED
        )
        assert restored.algorithm.endcap_policy == EndCapPolicy.ROUNDED
        assert restored.algorithm.supersampling.is_adaptive
        assert restored.runtime.max_threads == 1

    def test_fast_profile(self) -> None:
        cfg = DVHConfig.fast()
        d = cfg.to_dict()
        restored = DVHConfig.from_dict(d)
        assert (
            restored.algorithm.interpolation_method == InterpolationMethod.RIGHT_PRISM
        )
        assert restored.algorithm.supersampling.factor == 3


# ---------------------------------------------------------------------------
# DVHBins (numpy 1D array handling)
# ---------------------------------------------------------------------------


class TestDVHBinsRoundTrip:
    def test_round_trip(self) -> None:
        dvh = DVHBins(
            dose_bin_edges_gy=np.array([0.0, 1.0, 2.0, 3.0]),
            differential_volume_cc=np.array([3.0, 2.0, 1.0]),
            total_volume_cc=6.0,
        )
        d = dvh.to_dict()
        restored = DVHBins.from_dict(d)
        np.testing.assert_array_equal(restored.dose_bin_edges_gy, dvh.dose_bin_edges_gy)
        np.testing.assert_array_equal(
            restored.differential_volume_cc, dvh.differential_volume_cc
        )
        assert restored.total_volume_cc == dvh.total_volume_cc

    def test_cumulative_recomputed(self) -> None:
        """Cumulative values are NOT serialised; they're recomputed."""
        dvh = DVHBins(
            dose_bin_edges_gy=np.array([0.0, 1.0, 2.0]),
            differential_volume_cc=np.array([2.0, 1.0]),
            total_volume_cc=3.0,
        )
        d = dvh.to_dict()
        assert "cumulative_volume_cc" not in d
        restored = DVHBins.from_dict(d)
        assert restored.cumulative_volume_cc[-1] == 0.0

    def test_json_serialisable(self) -> None:
        dvh = DVHBins(
            dose_bin_edges_gy=np.array([0.0, 0.5, 1.0]),
            differential_volume_cc=np.array([1.0, 0.5]),
            total_volume_cc=1.5,
        )
        s = json.dumps(dvh.to_dict())
        restored = DVHBins.from_dict(json.loads(s))
        assert restored.total_volume_cc == 1.5


# ---------------------------------------------------------------------------
# DVHResultSet (full round-trip)
# ---------------------------------------------------------------------------


def _make_full_result_set() -> DVHResultSet:
    """Build a DVHResultSet with all nested types populated."""
    spec = MetricSpec(
        family=MetricFamily.DVH_DOSE,
        threshold=95.0,
        threshold_unit=ThresholdUnit.PERCENT,
        output_unit=OutputUnit.GY,
        raw="D95%",
    )
    metric_result = MetricResult(
        spec=spec,
        value=41.5,
        unit="Gy",
        issues=(
            Issue(
                level=IssueLevel.INFO,
                code=IssueCode.Z_TOLERANCE_APPLIED,
                message="Z tolerance applied",
            ),
        ),
    )
    dvh = DVHBins(
        dose_bin_edges_gy=np.array([0.0, 1.0, 2.0, 3.0]),
        differential_volume_cc=np.array([3.0, 2.0, 1.0]),
        total_volume_cc=6.0,
    )
    roi_result = ROIResult(
        roi=ROIRef(name="PTV", roi_number=3, colour_rgb=(255, 0, 0)),
        status="ok",
        volume_cc=6.0,
        metrics=(metric_result,),
        dvh=dvh,
        diagnostics=ROIDiagnostics(
            effective_supersampling=3,
            contour_slice_count=10,
        ),
        issues=(
            Issue(
                level=IssueLevel.WARNING,
                code=IssueCode.DOSE_GRID_COARSE,
                message="Coarse grid",
                path=("PTV",),
            ),
        ),
    )
    provenance = ProvenanceRecord(
        pymedphys_version="0.42.0",
        timestamp_utc="2024-01-15T10:30:00Z",
        config=DVHConfig.reference(),
        input_metadata=InputMetadata(
            rtstruct_file_sha256="abc123",
            rtdose_file_sha256="def456",
            dose_grid_frame=GridFrame.from_uniform(
                shape_zyx=(10, 20, 30),
                spacing_xyz_mm=(2.5, 2.5, 2.5),
                origin_xyz_mm=(0.0, 0.0, 0.0),
            ),
        ),
        platform=PlatformInfo(
            python_version="3.11.0",
            numpy_version="1.26.0",
            numba_version="0.59.0",
            os="Linux",
        ),
    )
    return DVHResultSet(
        schema_version="1.0",
        results=(roi_result,),
        provenance=provenance,
        computation_time_s=2.34,
        dose_refs=DoseReferenceSet.single(42.0, "prescription: 3 fx x 14 Gy"),
        issues=(
            Issue(
                level=IssueLevel.INFO,
                code=IssueCode.Z_TOLERANCE_APPLIED,
                message="Global issue",
            ),
        ),
    )


class TestDVHResultSetRoundTrip:
    def test_dict_round_trip(self) -> None:
        rs = _make_full_result_set()
        d = rs.to_dict()
        restored = DVHResultSet.from_dict(d)
        assert restored.schema_version == "1.0"
        assert len(restored.results) == 1
        assert restored.results[0].roi.name == "PTV"
        assert restored.results[0].status == "ok"
        assert restored.results[0].volume_cc == 6.0
        assert restored.computation_time_s == pytest.approx(2.34)

    def test_json_round_trip(self) -> None:
        rs = _make_full_result_set()
        json_str = to_json(rs)
        restored = from_json(json_str, DVHResultSet)
        assert restored.schema_version == "1.0"
        assert len(restored.results) == 1
        assert restored.results[0].roi.name == "PTV"
        assert restored.results[0].dvh is not None
        assert rs.results[0].dvh is not None
        np.testing.assert_array_equal(
            restored.results[0].dvh.dose_bin_edges_gy,
            rs.results[0].dvh.dose_bin_edges_gy,
        )

    def test_provenance_preserved(self) -> None:
        rs = _make_full_result_set()
        d = rs.to_dict()
        restored = DVHResultSet.from_dict(d)
        assert restored.provenance.pymedphys_version == "0.42.0"
        assert restored.provenance.input_metadata is not None
        assert restored.provenance.input_metadata.rtstruct_file_sha256 == "abc123"
        assert restored.provenance.platform is not None
        assert restored.provenance.platform.python_version == "3.11.0"

    def test_metrics_preserved(self) -> None:
        rs = _make_full_result_set()
        d = rs.to_dict()
        restored = DVHResultSet.from_dict(d)
        m = restored.results[0].metrics[0]
        assert m.spec.family == MetricFamily.DVH_DOSE
        assert m.spec.threshold == 95.0
        assert m.value == 41.5
        assert m.unit == "Gy"

    def test_issues_preserved(self) -> None:
        rs = _make_full_result_set()
        d = rs.to_dict()
        restored = DVHResultSet.from_dict(d)
        all_issues = restored.all_issues()
        assert len(all_issues) == 3  # 1 global + 1 roi + 1 metric
