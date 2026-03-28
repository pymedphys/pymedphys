"""Tests for JSON/TOML serialisation — stubs for future implementation."""

from __future__ import annotations

import pytest


@pytest.mark.skip(reason="serialisation not yet implemented")
def test_json_round_trip_metric_spec() -> None:
    """MetricSpec should survive JSON round-trip."""


@pytest.mark.skip(reason="serialisation not yet implemented")
def test_json_round_trip_dvh_config() -> None:
    """DVHConfig should survive JSON round-trip."""


@pytest.mark.skip(reason="serialisation not yet implemented")
def test_json_round_trip_dvh_result_set() -> None:
    """DVHResultSet should survive JSON round-trip."""


@pytest.mark.skip(reason="serialisation not yet implemented")
def test_toml_round_trip_metric_request_set() -> None:
    """MetricRequestSet should survive TOML round-trip."""
