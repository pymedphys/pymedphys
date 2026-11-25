"""Reject object-name collisions before downloading an IDC DICOM series."""

import importlib.util
from pathlib import Path

import pytest


_SPEC = importlib.util.spec_from_file_location(
    "fetch_idc_series_under_test", Path(__file__).with_name("fetch_idc_series.py")
)
assert _SPEC is not None and _SPEC.loader is not None
IDCMODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(IDCMODULE)

UUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


@pytest.mark.parametrize(
    ("object_names", "message"),
    [
        ([f"{UUID}/one/CT.dcm", f"{UUID}/two/CT.dcm"], "Colliding"),
        ([f"{UUID}/CT.dcm", f"{UUID}/ct.DCM"], "Colliding"),
        ([f"{UUID}/CT.dcm", "other-prefix/OTHER.dcm"], "Unexpected"),
        ([f"{UUID}/.hidden"], "Unexpected"),
        ([f"{UUID}/CON.dcm"], "Unexpected"),
        ([f"{UUID}/prn"], "Unexpected"),
        ([f"{UUID}/LPT1.DCM"], "Unexpected"),
        ([f"{UUID}/alternate:stream.dcm"], "Unexpected"),
        ([f"{UUID}/image.dcm "], "Unexpected"),
        ([f"{UUID}/image.dcm."], "Unexpected"),
        ([f"{UUID}/image\\nname.dcm"], "Unexpected"),
        ([f"{UUID}/image\\x7fname.dcm"], "Unexpected"),
    ],
)
def test_rejects_unsafe_listing_before_any_download(
    tmp_path, monkeypatch, object_names, message
):
    monkeypatch.setattr(IDCMODULE, "keys", lambda _uuid: object_names)

    def never_download(_url):
        pytest.fail("invalid series listing must not trigger file downloads")

    monkeypatch.setattr(IDCMODULE, "_get", never_download)
    with pytest.raises(SystemExit, match=message):
        IDCMODULE.fetch(UUID, tmp_path)
    assert not list((tmp_path / UUID).iterdir())


def test_distinct_object_names_are_downloaded(tmp_path, monkeypatch):
    objects = [f"{UUID}/first.dcm", f"{UUID}/second.dcm"]
    monkeypatch.setattr(IDCMODULE, "keys", lambda _uuid: objects)
    monkeypatch.setattr(IDCMODULE, "_get", lambda url: url.encode("ascii"))

    assert IDCMODULE.fetch(UUID, tmp_path) == 2
    assert (tmp_path / UUID / "first.dcm").is_file()
    assert (tmp_path / UUID / "second.dcm").is_file()
