from pymedphys.deliverydata import DeliveryData


def test_object_consistency():
    empty = DeliveryData.empty()
    filtered = empty.filter_cps()
    metersets = filtered.metersets(0, 0)
