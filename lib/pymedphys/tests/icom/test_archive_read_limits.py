# Copyright (C) 2026 Jeffrey D. Cooney
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Protect iCOM viewers from oversized decompressed treatment records."""

import lzma

from pymedphys._imports import pytest

from pymedphys._icom import archive
from pymedphys._icom.archive import read_icom_archive


@pytest.mark.parametrize("data", [b"", b"1234567", b"A" * 32])
def test_reads_archive_up_to_and_including_limit(tmp_path, data):
    path = tmp_path / "test.xz"
    path.write_bytes(lzma.compress(data))

    assert read_icom_archive(path, limit=max(1, len(data))) == data


def test_rejects_expansion_above_limit_without_exposing_path(tmp_path):
    patient_id = "SYNTHETIC-PATIENT-12345"
    path = tmp_path / f"{patient_id}.xz"
    path.write_bytes(lzma.compress(b"X" * 4096))

    with pytest.raises(ValueError, match="decompressed size limit") as exc:
        read_icom_archive(path, limit=128)

    assert patient_id not in str(exc.value)


@pytest.mark.parametrize("limit", [-1, 1.5, "1024"])
def test_invalid_limits_rejected(tmp_path, limit):
    with pytest.raises(ValueError, match="limit"):
        read_icom_archive(tmp_path / "unused.xz", limit=limit)


def test_concatenated_xz_records_remain_supported(tmp_path):
    path = tmp_path / "concatenated.xz"
    path.write_bytes(
        lzma.compress(b"delivery-one") + b"\x00" * 4
        + lzma.compress(b"delivery-two")
    )
    assert read_icom_archive(path) == b"delivery-onedelivery-two"


def test_decoder_memory_budget_is_enforced(tmp_path, monkeypatch):
    path = tmp_path / "archive.xz"
    path.write_bytes(lzma.compress(b"synthetic delivery"))
    monkeypatch.setattr(archive, "MAX_LZMA_DECODER_MEMORY", 1)

    with pytest.raises(ValueError, match="Unsafe or invalid"):
        read_icom_archive(path)


def test_compressed_input_budget_is_enforced(tmp_path, monkeypatch):
    path = tmp_path / "archive.xz"
    path.write_bytes(lzma.compress(b"synthetic delivery"))
    monkeypatch.setattr(archive, "MAX_COMPRESSED_ICOM_BYTES", 16)

    with pytest.raises(ValueError, match="compressed size limit"):
        read_icom_archive(path)


def test_selected_archive_budget_limits_combined_output(tmp_path, monkeypatch):
    pytest.importorskip("streamlit")
    from pymedphys._streamlit.apps.metersetmap import _icom

    first = tmp_path / "first.xz"
    second = tmp_path / "second.xz"
    first.write_bytes(lzma.compress(b"a" * 8))
    second.write_bytes(lzma.compress(b"b" * 8))
    monkeypatch.setattr(_icom, "MAX_SELECTED_ICOM_BYTES", 10)
    monkeypatch.setattr(
        _icom,
        "load_icom_stream",
        lambda path, limit: read_icom_archive(path, limit=limit),
    )

    with pytest.raises(ValueError, match="decompressed size limit"):
        _icom.load_icom_streams([first, second])
