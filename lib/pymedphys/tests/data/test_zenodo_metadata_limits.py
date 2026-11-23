"""Bound and validate untrusted Zenodo record JSON responses."""

import json
from unittest import mock

import pytest

from pymedphys._data import zenodo


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
        self.status_checked = False

    def __enter__(self):
        return self

    def __exit__(self, _kind, _value, _traceback):
        return False

    def raise_for_status(self):
        self.status_checked = True

    def iter_content(self, chunk_size):
        for start in range(0, len(self.payload), chunk_size):
            yield self.payload[start : start + chunk_size]


def test_zenodo_metadata_streams_normal_record(monkeypatch):
    records = [{"key": "data.dcm", "checksum": "md5:123"}]
    response = FakeResponse(json.dumps({"files": records}).encode("utf-8"))
    getter = mock.Mock(return_value=response)
    monkeypatch.setattr(zenodo.requests, "get", getter)
    zenodo.get_all_zenodo_file_data_by_id.cache_clear()
    try:
        assert zenodo.get_all_zenodo_file_data_by_id(123456) == records
        assert response.status_checked
        getter.assert_called_once_with(
            f"{zenodo.BASE_URL}123456", timeout=30, stream=True
        )
    finally:
        zenodo.get_all_zenodo_file_data_by_id.cache_clear()


def test_zenodo_metadata_aborts_oversized_response(monkeypatch):
    response = FakeResponse(b"x" * (zenodo.MAX_RECORD_METADATA_BYTES + 1))
    monkeypatch.setattr(zenodo.requests, "get", lambda *_args, **_kwargs: response)
    zenodo.get_all_zenodo_file_data_by_id.cache_clear()
    try:
        with pytest.raises(ValueError, match="metadata exceeds the size limit"):
            zenodo.get_all_zenodo_file_data_by_id(654321)
        assert response.status_checked
    finally:
        zenodo.get_all_zenodo_file_data_by_id.cache_clear()
