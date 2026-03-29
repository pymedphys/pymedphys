"""Tests for MetricSpec.parse() grammar (RFC section 6.5)."""

from __future__ import annotations

import pytest

from pymedphys._dvh._types._metrics import (
    IndexMetric,
    MetricFamily,
    MetricSpec,
    OutputUnit,
    ThresholdUnit,
)


class TestMetricSpecParse:
    """Tests for the metric string grammar parser."""

    # --- Dose-at-volume metrics ---

    def test_d95_percent(self) -> None:
        spec = MetricSpec.parse("D95%")
        assert spec.family == MetricFamily.DVH_DOSE
        assert spec.threshold == pytest.approx(95.0)
        assert spec.threshold_unit == ThresholdUnit.PERCENT
        assert spec.output_unit == OutputUnit.GY

    def test_d0_03cc(self) -> None:
        spec = MetricSpec.parse("D0.03cc")
        assert spec.family == MetricFamily.DVH_DOSE
        assert spec.threshold == pytest.approx(0.03)
        assert spec.threshold_unit == ThresholdUnit.CC
        assert spec.output_unit == OutputUnit.GY

    def test_d95_percent_rx_output(self) -> None:
        spec = MetricSpec.parse("D95%[%Rx]")
        assert spec.family == MetricFamily.DVH_DOSE
        assert spec.threshold == pytest.approx(95.0)
        assert spec.threshold_unit == ThresholdUnit.PERCENT
        assert spec.output_unit == OutputUnit.PERCENT_DOSE

    def test_d99_percent(self) -> None:
        spec = MetricSpec.parse("D99%")
        assert spec.threshold == pytest.approx(99.0)

    def test_d2_percent(self) -> None:
        spec = MetricSpec.parse("D2%")
        assert spec.threshold == pytest.approx(2.0)

    # --- Volume-at-dose metrics ---

    def test_v10gy(self) -> None:
        spec = MetricSpec.parse("V10Gy")
        assert spec.family == MetricFamily.DVH_VOLUME
        assert spec.threshold == pytest.approx(10.0)
        assert spec.threshold_unit == ThresholdUnit.GY
        assert spec.output_unit == OutputUnit.CC

    def test_v95_percent(self) -> None:
        spec = MetricSpec.parse("V95%")
        assert spec.family == MetricFamily.DVH_VOLUME
        assert spec.threshold == pytest.approx(95.0)
        assert spec.threshold_unit == ThresholdUnit.PERCENT
        assert spec.output_unit == OutputUnit.CC

    def test_v20gy_percent_output(self) -> None:
        spec = MetricSpec.parse("V20Gy[%]")
        assert spec.family == MetricFamily.DVH_VOLUME
        assert spec.threshold == pytest.approx(20.0)
        assert spec.threshold_unit == ThresholdUnit.GY
        assert spec.output_unit == OutputUnit.PERCENT_VOLUME

    # --- Scalar metrics ---

    def test_mean(self) -> None:
        spec = MetricSpec.parse("mean")
        assert spec.family == MetricFamily.SCALAR

    def test_median(self) -> None:
        spec = MetricSpec.parse("median")
        assert spec.family == MetricFamily.SCALAR

    def test_min(self) -> None:
        spec = MetricSpec.parse("min")
        assert spec.family == MetricFamily.SCALAR

    def test_max(self) -> None:
        spec = MetricSpec.parse("max")
        assert spec.family == MetricFamily.SCALAR

    # --- Index metrics ---

    def test_hi(self) -> None:
        spec = MetricSpec.parse("HI")
        assert spec.family == MetricFamily.INDEX

    def test_ci(self) -> None:
        spec = MetricSpec.parse("CI")
        assert spec.family == MetricFamily.INDEX

    def test_pci(self) -> None:
        spec = MetricSpec.parse("PCI")
        assert spec.family == MetricFamily.INDEX

    def test_gi(self) -> None:
        spec = MetricSpec.parse("GI")
        assert spec.family == MetricFamily.INDEX

    # --- Error cases ---

    def test_raises_on_empty_string(self) -> None:
        with pytest.raises(ValueError):
            MetricSpec.parse("")

    def test_raises_on_garbage(self) -> None:
        with pytest.raises(ValueError):
            MetricSpec.parse("notametric")


class TestMetricSpecParseExtended:
    """Extended grammar tests: round-trips, mean[%Rx], IndexMetric enum."""

    def test_canonical_key_stable(self) -> None:
        spec = MetricSpec.parse("D95%")
        key1 = spec.canonical_key
        key2 = MetricSpec.parse("D95%").canonical_key
        assert key1 == key2

    def test_raw_string_preserved(self) -> None:
        spec = MetricSpec.parse("D95%")
        assert spec.raw == "D95%"

    # E3: mean[%Rx] support
    def test_mean_percent_rx(self) -> None:
        spec = MetricSpec.parse("mean[%Rx]")
        assert spec.family == MetricFamily.SCALAR
        assert spec.output_unit == OutputUnit.PERCENT_DOSE
        assert spec.requires_dose_ref is True

    # E2/A5: Index metrics carry IndexMetric enum
    def test_ci_carries_index_metric(self) -> None:
        spec = MetricSpec.parse("CI")
        assert spec.index_metric == IndexMetric.CI
        assert spec.requires_dose_ref is True

    def test_hi_carries_index_metric(self) -> None:
        spec = MetricSpec.parse("HI")
        assert spec.index_metric == IndexMetric.HI
        assert spec.requires_dose_ref is False

    def test_gi_carries_index_metric(self) -> None:
        spec = MetricSpec.parse("GI")
        assert spec.index_metric == IndexMetric.GI
        assert spec.requires_dose_ref is True

    def test_pci_carries_index_metric(self) -> None:
        spec = MetricSpec.parse("PCI")
        assert spec.index_metric == IndexMetric.PCI
        assert spec.requires_dose_ref is True
