"""Tests for MetricSpec, enums, and request types (RFC section 6.5)."""

from __future__ import annotations

import pytest

from pymedphys._dvh._types._dose_ref import DoseReference, DoseReferenceSet
from pymedphys._dvh._types._metrics import (
    MetricFamily,
    MetricRequestSet,
    MetricSpec,
    OutputUnit,
    ROIMetricRequest,
    ThresholdUnit,
)
from pymedphys._dvh._types._roi_ref import ROIRef


class TestMetricFamilyEnum:
    def test_has_dvh_dose(self) -> None:
        assert MetricFamily.DVH_DOSE == "dvh_dose"

    def test_has_dvh_volume(self) -> None:
        assert MetricFamily.DVH_VOLUME == "dvh_volume"

    def test_has_scalar(self) -> None:
        assert MetricFamily.SCALAR == "scalar"

    def test_has_index(self) -> None:
        assert MetricFamily.INDEX == "index"


class TestThresholdUnitEnum:
    def test_has_percent(self) -> None:
        assert ThresholdUnit.PERCENT == "percent"

    def test_has_cc(self) -> None:
        assert ThresholdUnit.CC == "cc"

    def test_has_gy(self) -> None:
        assert ThresholdUnit.GY == "Gy"

    def test_has_none(self) -> None:
        assert ThresholdUnit.NONE == "none"


class TestOutputUnitEnum:
    def test_has_gy(self) -> None:
        assert OutputUnit.GY == "Gy"

    def test_has_percent_dose(self) -> None:
        assert OutputUnit.PERCENT_DOSE == "percent_dose"

    def test_has_cc(self) -> None:
        assert OutputUnit.CC == "cc"

    def test_has_percent_volume(self) -> None:
        assert OutputUnit.PERCENT_VOLUME == "percent_vol"

    def test_has_dimensionless(self) -> None:
        assert OutputUnit.DIMENSIONLESS == "dimensionless"


class TestMetricSpec:
    """Tests for MetricSpec dataclass."""

    def test_rejects_negative_threshold(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            MetricSpec(
                family=MetricFamily.DVH_DOSE,
                threshold=-1.0,
                threshold_unit=ThresholdUnit.PERCENT,
            )

    def test_accepts_zero_threshold(self) -> None:
        spec = MetricSpec(
            family=MetricFamily.DVH_DOSE,
            threshold=0.0,
            threshold_unit=ThresholdUnit.PERCENT,
        )
        assert spec.threshold == 0.0

    def test_requires_dose_ref_false_for_hi(self) -> None:
        spec = MetricSpec(
            family=MetricFamily.INDEX,
            raw="HI",
        )
        assert spec.requires_dose_ref is False

    def test_requires_dose_ref_true_for_v95_percent(self) -> None:
        spec = MetricSpec(
            family=MetricFamily.DVH_VOLUME,
            threshold=95.0,
            threshold_unit=ThresholdUnit.PERCENT,
            raw="V95%",
        )
        assert spec.requires_dose_ref is True

    def test_requires_dose_ref_true_for_percent_dose_output(self) -> None:
        spec = MetricSpec(
            family=MetricFamily.DVH_DOSE,
            threshold=95.0,
            threshold_unit=ThresholdUnit.PERCENT,
            output_unit=OutputUnit.PERCENT_DOSE,
            raw="D95%[%Rx]",
        )
        assert spec.requires_dose_ref is True

    def test_requires_dose_ref_true_for_ci(self) -> None:
        spec = MetricSpec(family=MetricFamily.INDEX, raw="CI")
        assert spec.requires_dose_ref is True

    def test_requires_dose_ref_true_for_gi(self) -> None:
        spec = MetricSpec(family=MetricFamily.INDEX, raw="GI")
        assert spec.requires_dose_ref is True

    def test_requires_dose_ref_false_for_d95_percent(self) -> None:
        """D95% outputs in Gy by default — no dose ref needed."""
        spec = MetricSpec(
            family=MetricFamily.DVH_DOSE,
            threshold=95.0,
            threshold_unit=ThresholdUnit.PERCENT,
            output_unit=OutputUnit.GY,
            raw="D95%",
        )
        assert spec.requires_dose_ref is False

    def test_canonical_key_same_for_equivalent_specs(self) -> None:
        spec1 = MetricSpec(
            family=MetricFamily.DVH_DOSE,
            threshold=95.0,
            threshold_unit=ThresholdUnit.PERCENT,
            output_unit=OutputUnit.GY,
            raw="D95%",
        )
        spec2 = MetricSpec(
            family=MetricFamily.DVH_DOSE,
            threshold=95.0,
            threshold_unit=ThresholdUnit.PERCENT,
            output_unit=OutputUnit.GY,
            raw="D 95 %",  # different raw string
        )
        assert spec1.canonical_key == spec2.canonical_key

    def test_canonical_key_different_for_different_specs(self) -> None:
        spec1 = MetricSpec(
            family=MetricFamily.DVH_DOSE,
            threshold=95.0,
            threshold_unit=ThresholdUnit.PERCENT,
        )
        spec2 = MetricSpec(
            family=MetricFamily.DVH_DOSE,
            threshold=99.0,
            threshold_unit=ThresholdUnit.PERCENT,
        )
        assert spec1.canonical_key != spec2.canonical_key


class TestROIMetricRequest:
    """Tests for ROIMetricRequest."""

    def _make_spec(self, threshold: float = 95.0) -> MetricSpec:
        return MetricSpec(
            family=MetricFamily.DVH_DOSE,
            threshold=threshold,
            threshold_unit=ThresholdUnit.PERCENT,
            output_unit=OutputUnit.GY,
            raw=f"D{threshold}%",
        )

    def test_rejects_empty_metrics(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            ROIMetricRequest(roi=ROIRef(name="PTV"), metrics=())

    def test_rejects_duplicate_metrics(self) -> None:
        spec = self._make_spec(95.0)
        with pytest.raises(ValueError, match="Duplicate"):
            ROIMetricRequest(roi=ROIRef(name="PTV"), metrics=(spec, spec))

    def test_from_strings_creates_request(self) -> None:
        req = ROIMetricRequest.from_strings(
            name="PTV",
            metric_strings=["D95%", "D0.03cc"],
            roi_number=3,
        )
        assert req.roi.name == "PTV"
        assert req.roi.roi_number == 3
        assert len(req.metrics) == 2


class TestMetricRequestSet:
    """Tests for MetricRequestSet."""

    def _make_ref(self, dose: float = 60.0) -> DoseReference:
        return DoseReference(dose_gy=dose, source="test prescription source")

    def test_rejects_duplicate_rois(self) -> None:
        spec = MetricSpec(family=MetricFamily.SCALAR, raw="mean")
        req1 = ROIMetricRequest(roi=ROIRef(name="PTV"), metrics=(spec,))
        spec2 = MetricSpec(family=MetricFamily.SCALAR, raw="max")
        req2 = ROIMetricRequest(roi=ROIRef(name="PTV"), metrics=(spec2,))
        with pytest.raises(ValueError, match="Duplicate ROI"):
            MetricRequestSet(roi_requests=(req1, req2))

    def test_validates_dose_ref_availability(self) -> None:
        spec = MetricSpec(
            family=MetricFamily.DVH_VOLUME,
            threshold=95.0,
            threshold_unit=ThresholdUnit.PERCENT,
            raw="V95%",
        )
        req = ROIMetricRequest(roi=ROIRef(name="PTV"), metrics=(spec,))
        with pytest.raises(ValueError, match="dose reference"):
            MetricRequestSet(roi_requests=(req,))

    def test_accepts_valid_dose_ref(self) -> None:
        spec = MetricSpec(
            family=MetricFamily.DVH_VOLUME,
            threshold=95.0,
            threshold_unit=ThresholdUnit.PERCENT,
            raw="V95%",
        )
        req = ROIMetricRequest(roi=ROIRef(name="PTV"), metrics=(spec,))
        dose_refs = DoseReferenceSet.single(60.0, "prescription: 30 fx x 2 Gy")
        mrs = MetricRequestSet(roi_requests=(req,), dose_refs=dose_refs)
        assert len(mrs.roi_requests) == 1

    def test_from_dict_simple_format(self) -> None:
        d = {
            "dose_ref_gy": 42.0,
            "dose_ref_source": "prescription: 3 fx x 14 Gy",
            "metrics": {
                "PTV42": ["D95%", "D99%"],
                "SpinalCanal": ["D0.03cc"],
            },
        }
        mrs = MetricRequestSet.from_dict(d)
        assert len(mrs.roi_requests) == 2
        assert mrs.dose_refs is not None

    def test_from_dict_rich_sib_format(self) -> None:
        d = {
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
        mrs = MetricRequestSet.from_dict(d)
        assert len(mrs.roi_requests) == 2
        assert mrs.dose_refs is not None
        assert "ptv60" in mrs.dose_refs.refs

    def test_dose_ref_resolution_fails_when_no_default_and_no_explicit_ref(
        self,
    ) -> None:
        """D5: When requires_dose_ref=True, dose_refs is provided, but
        both m.dose_ref_id and rr.dose_ref_id are None and
        DoseReferenceSet.default_id is also None, validation must fail.
        """
        # V95% requires a dose ref (threshold_unit=PERCENT for DVH_VOLUME)
        spec = MetricSpec(
            family=MetricFamily.DVH_VOLUME,
            threshold=95.0,
            threshold_unit=ThresholdUnit.PERCENT,
            raw="V95%",
        )
        req = ROIMetricRequest(roi=ROIRef(name="PTV"), metrics=(spec,))
        # Provide a DoseReferenceSet with NO default_id
        dose_refs = DoseReferenceSet(
            refs={
                "ptv60": DoseReference(60.0, "PTV60 prescription dose"),
            },
            default_id=None,
        )
        with pytest.raises(ValueError, match="No ref_id"):
            MetricRequestSet(roi_requests=(req,), dose_refs=dose_refs)

    def test_roi_refs_returns_frozenset(self) -> None:
        spec = MetricSpec(family=MetricFamily.SCALAR, raw="mean")
        req = ROIMetricRequest(roi=ROIRef(name="PTV"), metrics=(spec,))
        mrs = MetricRequestSet(roi_requests=(req,))
        refs = mrs.roi_refs
        assert isinstance(refs, frozenset)
        assert len(refs) == 1
