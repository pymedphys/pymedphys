# Copyright (C) 2026 PyMedPhys contributors
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
