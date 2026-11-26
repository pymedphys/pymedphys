"""Reject object-name collisions before downloading an IDC DICOM series."""

import importlib.util
import io
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
    ],
)
def test_rejects_unsafe_listing_before_any_download(
    tmp_path, monkeypatch, object_names, message
):
    monkeypatch.setattr(IDCMODULE, "keys", lambda _uuid: object_names)

    def never_download(_url, _destination):
        pytest.fail("invalid series listing must not trigger file downloads")

    monkeypatch.setattr(IDCMODULE, "_download_to_file", never_download)
    with pytest.raises(SystemExit, match=message):
        IDCMODULE.fetch(UUID, tmp_path)
    assert not list((tmp_path / UUID).iterdir())


def test_distinct_object_names_are_downloaded(tmp_path, monkeypatch):
    objects = [f"{UUID}/first.dcm", f"{UUID}/second.dcm"]
    monkeypatch.setattr(IDCMODULE, "keys", lambda _uuid: objects)
    monkeypatch.setattr(
        IDCMODULE,
        "_download_to_file",
        lambda url, destination: destination.write_bytes(url.encode("ascii")),
    )

    assert IDCMODULE.fetch(UUID, tmp_path) == 2
    assert (tmp_path / UUID / "first.dcm").is_file()
    assert (tmp_path / UUID / "second.dcm").is_file()


def test_large_objects_are_written_in_bounded_chunks(tmp_path, monkeypatch):
    payload = b"x" * (2 * (1 << 20) + 7)
    chunk_sizes = []

    class Response(io.BytesIO):
        def read(self, size=-1):
            chunk_sizes.append(size)
            return super().read(size)

    monkeypatch.setattr(
        IDCMODULE.urllib.request,
        "urlopen",
        lambda url, timeout: Response(payload),
    )
    path = tmp_path / "object.dcm"
    IDCMODULE._download_to_file(IDCMODULE.BUCKET + "file", path)
    assert path.read_bytes() == payload
    assert len(chunk_sizes) >= 4
    assert all(size == 1 << 20 for size in chunk_sizes)


def test_failed_stream_is_discarded_before_retry(tmp_path, monkeypatch):
    attempts = []

    class BrokenResponse(io.BytesIO):
        def read(self, size=-1):
            if self.tell() >= 3:
                raise OSError("broken response")
            return super().read(3)

    def fake_open(url, timeout):
        attempts.append(url)
        return (
            BrokenResponse(b"bad partial")
            if len(attempts) == 1
            else io.BytesIO(b"valid")
        )

    monkeypatch.setattr(IDCMODULE.urllib.request, "urlopen", fake_open)
    monkeypatch.setattr(IDCMODULE.time, "sleep", lambda seconds: None)
    path = tmp_path / "object.dcm"
    IDCMODULE._download_to_file(IDCMODULE.BUCKET + "file", path)
    assert len(attempts) == 2
    assert path.read_bytes() == b"valid"
