from pymedphys import Delivery

# pylint: disable = protected-access


def test_object_consistency():
    empty = Delivery._empty()
    filtered = empty._filter_cps()

    assert isinstance(filtered.monitor_units, tuple)

    filtered._metersets(0, 0)


def test_base_object():
    empty = Delivery._empty()

    assert empty.monitor_units == tuple()

    collection = {field: getattr(empty, field) for field in empty._fields}

    dummy = Delivery(**collection)
