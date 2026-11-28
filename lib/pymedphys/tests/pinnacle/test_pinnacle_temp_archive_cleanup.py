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

"""Pinnacle clinical TAR extracts must not persist after CLI termination."""

import io
import tarfile
from pathlib import Path
from types import SimpleNamespace

from pymedphys._imports import pytest

from pymedphys._pinnacle import pinnacle_cli


def _archive(tmp_path):
    archive = tmp_path / "clinical.tar"
    with tarfile.open(archive, "w") as output:
        contents = b"synthetic patient data"
        member = tarfile.TarInfo("Patient_001/Patient")
        member.size = len(contents)
        output.addfile(member, io.BytesIO(contents))
    return archive


def _args(archive):
    return SimpleNamespace(
        input_path=str(archive),
        output_directory=None,
        verbose=False,
        modality=[],
        plan="",
        trial="",
        list=True,
        image=None,
        uid_prefix=None,
        roiskip=None,
        mrn=False,
    )


def test_export_cleans_extracted_patient_files_on_early_exit(tmp_path, monkeypatch):
    seen = []

    class MockPinnacle:
        def __init__(self, path, _logger):
            seen.append(Path(path))
            assert (Path(path) / "Patient").is_file()

        def log_trial_names(self):
            return None

        def log_images(self):
            return None

    monkeypatch.setattr(pinnacle_cli, "PinnacleExport", MockPinnacle)

    with pytest.raises(SystemExit):
        pinnacle_cli.export_cli(_args(_archive(tmp_path)))

    assert len(seen) == 1
    assert not seen[0].exists(), "the extracted patient folder must be removed"


def test_export_cleans_extracted_patient_files_on_exception(tmp_path, monkeypatch):
    seen = []

    def failing_extract(_archive_path, scratch):
        root = Path(scratch)
        seen.append(root)
        (root / "patient-file").write_text("synthetic data", encoding="utf-8")
        raise RuntimeError("synthetic extraction failure")

    monkeypatch.setattr(pinnacle_cli, "extract_tar", failing_extract)
    with pytest.raises(RuntimeError, match="synthetic extraction failure"):
        pinnacle_cli.export_cli(_args(_archive(tmp_path)))

    assert len(seen) == 1
    assert not seen[0].exists(), "partial extracted patient data must be removed"
