from pymedphys_base.delivery import Delivery


def test_object_consistency():
    empty = Delivery.empty()
    filtered = empty.filter_cps()

    assert type(filtered.monitor_units) is tuple

    metersets = filtered.metersets(0, 0)


def test_base_object():
    empty = Delivery.empty()

    assert empty.monitor_units == tuple()

    collection = {field: getattr(empty, field) for field in empty._fields}

    dummy = Delivery(**collection)
