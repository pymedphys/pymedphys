"""Bounds checks for compressed clinical iCOM streams."""

import lzma

import pytest

from pymedphys._streamlit.apps.metersetmap import _icom


def test_small_icom_archive_round_trips(tmp_path):
    archive = tmp_path / "small.xz"
    archive.write_bytes(lzma.compress(b"valid test data"))
    assert _icom.load_icom_stream(archive) == b"valid test data"


def test_rejects_oversized_decompressed_icom(tmp_path, monkeypatch):
    monkeypatch.setattr(_icom, "MAX_DECOMPRESSED_ICOM_BYTES", 8)
    archive = tmp_path / "oversized.xz"
    archive.write_bytes(lzma.compress(b"A" * 10_000))
    with pytest.raises(ValueError, match="decompressed data limit"):
        _icom.load_icom_stream(archive)
