from pymedphys_base.deliverydata import DeliveryDataBase
from pymedphys.deliverydata import DeliveryData


def test_object_consistency():
    empty = DeliveryData.empty()
    filtered = empty.filter_cps()

    assert type(filtered.monitor_units) is tuple

    metersets = filtered.metersets(0, 0)


def test_base_object():
    empty = DeliveryDataBase.empty()

    assert empty.monitor_units == tuple()

    collection = {
        field: getattr(empty, field)
        for field in empty._fields
    }

    dummy = DeliveryDataBase(**collection)
