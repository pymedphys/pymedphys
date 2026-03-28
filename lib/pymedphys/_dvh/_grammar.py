"""Metric grammar — implementation is in _types/_metrics.py.

MetricSpec.parse() is defined directly on the MetricSpec dataclass.
This module exists as a named entry point per the RFC task list.
"""

from pymedphys._dvh._types._metrics import MetricSpec

__all__ = ["MetricSpec"]
