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

"""DICOM anonymisation auditing must inspect the requested literal directory."""

from pathlib import Path

from pymedphys._dicom.anonymise import core


def test_anonymity_audit_scans_bracketed_directory_name(tmp_path, monkeypatch):
    patient = tmp_path / "patient[1]"
    nested = patient / "series"
    nested.mkdir(parents=True)
    sensitive = nested / "plan.dcm"
    sensitive.write_bytes(b"synthetic non-anonymised contents")

    visited = []

    def fake_is_anonymised_file(path, ignore_private_tags=False):
        visited.append(Path(path))
        return False

    monkeypatch.setattr(core, "is_anonymised_file", fake_is_anonymised_file)

    assert core.is_anonymised_directory(patient) is False
    assert visited == [sensitive]


def test_anonymity_audit_never_scans_matching_sibling(tmp_path, monkeypatch):
    patient = tmp_path / "patient[1]"
    neighbour = tmp_path / "patient1"
    patient.mkdir()
    neighbour.mkdir()
    intended = patient / "intended.dcm"
    unrelated = neighbour / "unrelated.dcm"
    intended.write_bytes(b"synthetic")
    unrelated.write_bytes(b"synthetic")

    visited = []

    def fake_is_anonymised_file(path, ignore_private_tags=False):
        visited.append(Path(path))
        return True

    monkeypatch.setattr(core, "is_anonymised_file", fake_is_anonymised_file)

    assert core.is_anonymised_directory(patient) is True
    assert visited == [intended]
