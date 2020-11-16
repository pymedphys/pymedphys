import pymedphys
from pymedphys._trf.manage import identify


def test_date_convert_parity():
    path = pymedphys.data_path("negative-metersetmap.trf")
    header, _ = pymedphys.trf.read(path)

    utc_date = header["date"][0]
    timezone = "Australia/Sydney"

    dateutil_version = identify.date_convert_using_dateutil(utc_date, timezone)
    pandas_version = identify.date_convert(utc_date, timezone)

    assert dateutil_version == pandas_version
