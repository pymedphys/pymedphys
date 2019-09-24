from pymedphys import Delivery


def test_object_consistency():
    empty = Delivery._empty()
    filtered = empty._filter_cps()  # pylint: disable = protected-access

    assert type(filtered.monitor_units) is tuple

    metersets = filtered._metersets(0, 0)


def test_base_object():
    empty = Delivery._empty()

    assert empty.monitor_units == tuple()

    collection = {field: getattr(empty, field) for field in empty._fields}

    dummy = Delivery(**collection)
