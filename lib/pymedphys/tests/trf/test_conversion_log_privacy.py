# Copyright (C) 2026 Jeffrey D. Cooney

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

"""TRF conversion diagnostics must not expose patient-bearing path names."""

import importlib
import logging
from pathlib import Path

trf2csv_module = importlib.import_module("pymedphys._trf.decode.trf2csv")


class _FakeFrame:
    def to_csv(self, filepath):
        Path(filepath).write_text("synthetic\n")


def test_trf_to_csv_does_not_log_patient_bearing_paths(tmp_path, caplog, monkeypatch):
    patient_name = "SYNTHETIC_SENSITIVE_PATIENT_123456"
    source = tmp_path / f"{patient_name}.trf"
    source.write_bytes(b"synthetic")
    monkeypatch.setattr(
        trf2csv_module, "trf2pandas", lambda _: (_FakeFrame(), _FakeFrame())
    )

    monkeypatch.setenv("PYMEDPHYS_REDACT_TRF_PATHS", "1")
    with caplog.at_level(logging.INFO):
        header_path, table_path = trf2csv_module.trf2csv(
            source, output_directory=tmp_path
        )

    assert header_path.exists() and table_path.exists()
    assert patient_name not in caplog.text
    assert str(source) not in caplog.text
    assert "Converting TRF file" in caplog.text


def test_directory_conversion_does_not_print_patient_paths(
    tmp_path, capsys, monkeypatch
):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()
    patient_name = "SYNTHETIC_SENSITIVE_PATIENT_123456"
    (input_dir / f"{patient_name}.trf").write_bytes(b"synthetic")
    monkeypatch.setattr(
        trf2csv_module, "trf2pandas", lambda _: (_FakeFrame(), _FakeFrame())
    )

    monkeypatch.setenv("PYMEDPHYS_REDACT_TRF_PATHS", "1")
    trf2csv_module.trf2csv_by_directory(str(input_dir), str(output_dir))

    captured = capsys.readouterr()
    assert patient_name not in captured.out + captured.err
    assert "Converting TRF file" in captured.out
    assert len(list(output_dir.glob("*.csv"))) == 2


def test_default_progress_keeps_local_file_identity(tmp_path, monkeypatch, caplog):
    patient_name = "SYNTHETIC_SENSITIVE_PATIENT_123456"
    source = tmp_path / f"{patient_name}.trf"
    source.write_bytes(b"synthetic")
    monkeypatch.delenv("PYMEDPHYS_REDACT_TRF_PATHS", raising=False)
    monkeypatch.setattr(
        trf2csv_module, "trf2pandas", lambda _: (_FakeFrame(), _FakeFrame())
    )

    with caplog.at_level(logging.INFO):
        trf2csv_module.trf2csv(source, output_directory=tmp_path)

    assert str(source) in caplog.text
