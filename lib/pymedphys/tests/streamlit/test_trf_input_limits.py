"""Regression tests for bounded MetersetMap TRF reads."""

import io

import pytest

from pymedphys._streamlit.apps.metersetmap import _trf


def test_bounded_trf_reader_accepts_file_object_and_path(tmp_path):
    payload = b"TRF test bytes"
    path = tmp_path / "example.trf"
    path.write_bytes(payload)
    assert _trf._read_limited_trf_bytes(path) == payload
    stream = io.BytesIO(payload)
    stream.seek(4)
    assert _trf._read_limited_trf_bytes(stream) == payload


def test_bounded_trf_reader_rejects_overflow(tmp_path, monkeypatch):
    monkeypatch.setattr(_trf, "MAX_TRF_INPUT_BYTES", 4)
    path = tmp_path / "oversized.trf"
    path.write_bytes(b"12345")
    for source in (path, io.BytesIO(b"12345")):
        with pytest.raises(ValueError, match="allowed input size"):
            _trf._read_limited_trf_bytes(source)
