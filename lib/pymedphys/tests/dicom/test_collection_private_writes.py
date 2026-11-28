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

"""DICOM wrapper exports must not create broadly readable clinical files."""

import io
import os
import stat

from pymedphys._imports import pytest

from pymedphys._dicom.collection import DicomBase


class SyntheticDataset:
    def save_as(self, stream):
        stream.write(b"synthetic DICOM bytes")


def wrapped(dataset=None):
    obj = DicomBase.__new__(DicomBase)
    obj.dataset = dataset or SyntheticDataset()
    return obj


@pytest.mark.skipif(os.name == "nt", reason="POSIX file permissions")
def test_path_exports_are_private_on_create_and_overwrite(tmp_path):
    destination = tmp_path / "clinical.dcm"
    wrapped().to_file(destination)
    assert destination.read_bytes() == b"synthetic DICOM bytes"
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600

    destination.chmod(0o644)
    wrapped().to_file(destination)
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink semantics")
def test_path_export_replaces_symlink_instead_of_following_it(tmp_path):
    outside = tmp_path / "outside.dcm"
    outside.write_bytes(b"original")
    link = tmp_path / "clinical.dcm"
    link.symlink_to(outside)

    wrapped().to_file(link)

    assert outside.read_bytes() == b"original"
    assert link.read_bytes() == b"synthetic DICOM bytes"
    assert not link.is_symlink()


def test_filelike_output_is_preserved():
    output = io.BytesIO()
    wrapped().to_file(output)
    assert output.getvalue() == b"synthetic DICOM bytes"


def test_failed_export_preserves_previous_file_and_cleans_temp(tmp_path):
    destination = tmp_path / "clinical.dcm"
    destination.write_bytes(b"prior")

    class Broken:
        def save_as(self, stream):
            stream.write(b"partial patient data")
            raise RuntimeError("synthetic write failure")

    with pytest.raises(RuntimeError, match="synthetic write failure"):
        wrapped(Broken()).to_file(destination)

    assert destination.read_bytes() == b"prior"
    assert list(tmp_path.iterdir()) == [destination]
