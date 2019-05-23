from pymedphys.deliverydata import DeliveryData


def test_object_consistency():
    empty = DeliveryData.empty()
    filtered = empty.filter_cps()

    assert type(filtered.monitor_units) is tuple

    metersets = filtered.metersets(0, 0)
