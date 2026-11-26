# Copyright (C) 2026 PyMedPhys contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Bound untrusted Zenodo record metadata before JSON decoding."""

import json

from pymedphys._imports import pytest
from pymedphys._data import zenodo


class _Response:
    def __init__(self, chunks, *, reject=False):
        self.chunks = chunks
        self.reject = reject

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def raise_for_status(self):
        if self.reject:
            raise RuntimeError("HTTP error")

    def iter_content(self, chunk_size):
        yield from self.chunks


def test_zenodo_metadata_reads_successful_stream(monkeypatch):
    payload = json.dumps({"files": [{"key": "synthetic.dcm"}]}).encode()
    monkeypatch.setattr(zenodo.requests, "get", lambda *a, **k: _Response([payload]))
    zenodo.get_all_zenodo_file_data_by_id.cache_clear()
    assert zenodo.get_all_zenodo_file_data_by_id("test-record-ok") == [
        {"key": "synthetic.dcm"}
    ]


def test_zenodo_metadata_rejects_oversized_body(monkeypatch):
    oversized = b"x" * (zenodo.MAX_RECORD_METADATA_BYTES + 1)
    monkeypatch.setattr(zenodo.requests, "get", lambda *a, **k: _Response([oversized]))
    zenodo.get_all_zenodo_file_data_by_id.cache_clear()
    with pytest.raises(ValueError, match="metadata response exceeds"):
        zenodo.get_all_zenodo_file_data_by_id("test-record-large")


def test_zenodo_metadata_rejects_http_error(monkeypatch):
    monkeypatch.setattr(
        zenodo.requests, "get", lambda *a, **k: _Response([], reject=True)
    )
    zenodo.get_all_zenodo_file_data_by_id.cache_clear()
    with pytest.raises(RuntimeError, match="HTTP error"):
        zenodo.get_all_zenodo_file_data_by_id("test-record-http")


def test_zenodo_metadata_uses_bounded_streaming(monkeypatch):
    arguments = {}

    def get(*a, **k):
        arguments.update(k)
        return _Response([b'{"files": []}'])

    monkeypatch.setattr(zenodo.requests, "get", get)
    zenodo.get_all_zenodo_file_data_by_id.cache_clear()
    assert zenodo.get_all_zenodo_file_data_by_id("test-record-stream") == []
    assert arguments["stream"] is True
    assert arguments["timeout"] == 30
