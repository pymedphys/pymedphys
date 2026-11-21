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

"""Index progress messages must not disclose treatment-log paths."""

import importlib
import os
import sys
import traceback
from types import SimpleNamespace

import pytest

from pymedphys._trf.decode.header import decode_header

index_module = importlib.import_module("pymedphys._trf.manage.index")


def test_logfile_collision_does_not_print_patient_path(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PYMEDPHYS_REDACT_TRF_PATHS", "1")
    patient = "SYNTHETIC_PATIENT_123456"
    original = tmp_path / f"{patient}_incoming.trf"
    archived = tmp_path / f"{patient}_archived.trf"
    original.write_bytes(b"same")
    archived.write_bytes(b"same")

    def simulate_windows_collision(*_args):
        raise FileExistsError()

    monkeypatch.setattr(index_module.os, "rename", simulate_windows_collision)
    index_module.rename_and_handle_fileexists(original, archived)

    assert not original.exists()
    captured = capsys.readouterr()
    assert patient not in captured.out + captured.err
    assert "Destination logfile already exists" in captured.out


def test_header_error_does_not_print_exception_with_patient_id(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setenv("PYMEDPHYS_REDACT_TRF_PATHS", "1")
    patient = "SYNTHETIC_PATIENT_123456"
    filename = tmp_path / f"{patient}.trf"
    filename.write_bytes(b"synthetic")

    def reject_header(_):
        raise ValueError(f"Bad header for {patient}")

    moves = []
    monkeypatch.setattr(index_module, "decode_header_from_file", reject_header)
    monkeypatch.setattr(
        index_module,
        "rename_and_handle_fileexists",
        lambda old, new: moves.append((old, new)),
    )

    index_module.file_ready_to_be_indexed(
        connections={},
        filehash_list=["synthetic-hash"],
        to_be_indexed_dict={"synthetic-hash": str(filename)},
        unknown_error_in_logfile=str(tmp_path / "errors"),
        no_mosaiq_record_found=str(tmp_path / "unmatched"),
        no_field_label_in_logfile=str(tmp_path / "no-field"),
        indexed_directory=str(tmp_path / "indexed"),
        index_filepath=str(tmp_path / "index.json"),
        index={},
        machine_map={},
        centre_details={},
        centre_server_map={},
    )

    assert len(moves) == 1
    captured = capsys.readouterr()
    assert patient not in captured.out + captured.err
    assert "Logfile header could not be processed" in captured.out


def test_successful_index_does_not_print_patient_paths(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PYMEDPHYS_REDACT_TRF_PATHS", "1")
    patient = "SYNTHETIC_PATIENT_123456"
    filename = tmp_path / f"{patient}.trf"
    filename.write_bytes(b"synthetic")
    header = SimpleNamespace(
        machine="unit",
        date="2026-11-20",
        field_label="field",
        field_name="field",
    )
    monkeypatch.setattr(index_module, "decode_header_from_file", lambda _: header)
    monkeypatch.setattr(
        index_module, "date_convert", lambda *_: ("mosaiq-time", "path-time")
    )
    monkeypatch.setattr(
        index_module, "get_mosaiq_delivery_details", lambda *_args, **_kw: object()
    )
    monkeypatch.setattr(
        index_module,
        "create_logfile_directory_name",
        lambda *_: f"{patient}/clinical/field",
    )
    monkeypatch.setattr(
        index_module, "create_index_entry", lambda *_: {"synthetic": True}
    )

    index_module.file_ready_to_be_indexed(
        connections={"server": object()},
        filehash_list=["synthetic-hash"],
        to_be_indexed_dict={"synthetic-hash": str(filename)},
        unknown_error_in_logfile=str(tmp_path / "errors"),
        no_mosaiq_record_found=str(tmp_path / "unmatched"),
        no_field_label_in_logfile=str(tmp_path / "no-field"),
        indexed_directory=str(tmp_path / "indexed"),
        index_filepath=str(tmp_path / "index.json"),
        index={},
        machine_map={"unit": {"centre": "centre"}},
        centre_details={"centre": {"timezone": "UTC"}},
        centre_server_map={"centre": "server"},
    )

    assert not filename.exists()
    archived = tmp_path / "indexed" / patient / "clinical" / "field" / filename.name
    assert archived.exists()
    captured = capsys.readouterr()
    assert patient not in captured.out + captured.err
    assert "Indexed logfile" in captured.out


def test_default_collision_output_preserves_local_file_identity(
    tmp_path, monkeypatch, capsys
):
    patient = "SYNTHETIC_PATIENT_123456"
    original = tmp_path / f"{patient}_incoming.trf"
    archived = tmp_path / f"{patient}_archived.trf"
    original.write_bytes(b"same")
    archived.write_bytes(b"same")
    monkeypatch.delenv("PYMEDPHYS_REDACT_TRF_PATHS", raising=False)

    def simulate_windows_collision(*_args):
        raise FileExistsError()

    monkeypatch.setattr(index_module.os, "rename", simulate_windows_collision)
    index_module.rename_and_handle_fileexists(original, archived)

    assert str(archived) in capsys.readouterr().out


@pytest.mark.parametrize("redact", [False, True])
def test_real_header_decoder_respects_redaction(redact, monkeypatch, capsys):
    patient = "SYNTHETIC_PATIENT_123456"
    if redact:
        monkeypatch.setenv("PYMEDPHYS_REDACT_TRF_PATHS", "1")
    else:
        monkeypatch.delenv("PYMEDPHYS_REDACT_TRF_PATHS", raising=False)

    # Exercise _header_match through the real decoder, not a mocked decoder.
    with pytest.raises(ValueError, match="TRF header not in an expected form"):
        decode_header(("malformed TRF header " + patient).encode("ascii"))

    captured = capsys.readouterr()
    if redact:
        assert patient not in captured.out + captured.err
    else:
        assert patient in captured.out


@pytest.mark.parametrize("redact", [False, True])
def test_orchestration_cli_fatal_archive_move_respects_redaction(
    tmp_path, monkeypatch, capsys, redact
):
    from pymedphys import _config
    from pymedphys.cli import pymedphys_cli

    orchestration_module = importlib.import_module(
        "pymedphys._trf.manage.orchestration"
    )
    patient = "SYNTHETIC_PATIENT_123456"
    incoming = tmp_path / "to_be_indexed" / f"{patient}.trf"
    incoming.parent.mkdir(parents=True)
    incoming.write_bytes(b"synthetic logfile")

    if redact:
        monkeypatch.setenv("PYMEDPHYS_REDACT_TRF_PATHS", "1")
    else:
        monkeypatch.delenv("PYMEDPHYS_REDACT_TRF_PATHS", raising=False)

    config = {
        "trf_logfiles": {"root_directory": str(tmp_path)},
        "site": [
            {
                "name": "centre",
                "mosaiq": {
                    "timezone": "UTC",
                    "hostname": "localhost",
                    "port": 1433,
                },
                "linac": [{"name": "unit", "samba_ip": "127.0.0.1"}],
            }
        ],
    }
    monkeypatch.setattr(_config, "get_config", lambda: config)
    monkeypatch.setattr(
        orchestration_module,
        "fetch_system_diagnostics_multi_linac",
        lambda *_: None,
    )
    monkeypatch.setattr(
        orchestration_module,
        "extract_diagnostic_zips_and_archive",
        lambda *_: None,
    )
    monkeypatch.setattr(index_module._pp_mosaiq, "connect", lambda *_: object())
    monkeypatch.setattr(
        index_module,
        "decode_header_from_file",
        lambda *_: SimpleNamespace(
            machine="unit",
            date="2026-11-20",
            field_label="field",
            field_name="field",
        ),
    )
    monkeypatch.setattr(
        index_module, "date_convert", lambda *_: ("mosaiq-time", "path-time")
    )
    monkeypatch.setattr(
        index_module,
        "get_mosaiq_delivery_details",
        lambda *_args, **_kw: SimpleNamespace(
            patient_id=patient,
            last_name="Test",
            first_name="Patient",
            qa_mode=False,
            field_id="1",
            field_type="TREATMENT",
        ),
    )
    monkeypatch.setattr(
        index_module,
        "create_index_entry",
        lambda *_: {"synthetic": True},
    )

    real_rename = os.rename

    def reject_archive_move(source, destination):
        if os.fspath(source) == os.fspath(incoming):
            raise PermissionError(
                13, f"archive move failed for {patient}", source, None, destination
            )
        return real_rename(source, destination)

    monkeypatch.setattr(index_module.os, "rename", reject_archive_move)
    monkeypatch.setattr(sys, "argv", ["pymedphys", "trf", "orchestrate"])

    error_type = RuntimeError if redact else PermissionError
    with pytest.raises(error_type) as caught:
        pymedphys_cli()

    captured = capsys.readouterr()
    formatted = "".join(traceback.format_exception(caught.value))
    if redact:
        assert "TRF indexing failed (PermissionError)" in formatted
        assert patient not in captured.out + captured.err + formatted
        assert "archive move failed" not in formatted
    else:
        assert patient in formatted
    assert "Complete" not in captured.out
