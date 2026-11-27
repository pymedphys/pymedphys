"""Clinical treatment deliveries are recomputed, not shared across sessions."""

import pytest

from pymedphys._streamlit.apps.metersetmap import _deliveries


class _FreshDelivery:
    @staticmethod
    def _from_pandas(*args):
        return object()

    @staticmethod
    def from_icom(*args):
        return object()

    @staticmethod
    def from_monaco(*args):
        return object()

    @staticmethod
    def from_mosaiq(*args):
        return object()


@pytest.mark.parametrize(
    "loader_name, input_value",
    [
        ("delivery_from_trf", "synthetic-table"),
        ("delivery_from_icom", b"synthetic-icom"),
        ("delivery_from_tel", "synthetic.TEL"),
        ("delivery_from_mosaiq", (object(), 17)),
    ],
)
def test_delivery_loader_recomputes_each_request(monkeypatch, loader_name, input_value):
    monkeypatch.setattr(_deliveries.pymedphys, "Delivery", _FreshDelivery)
    load = getattr(_deliveries, loader_name)
    assert load(input_value) is not load(input_value)
