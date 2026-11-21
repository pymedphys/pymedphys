# Copyright (C) 2026

"""Index progress messages must not disclose treatment-log paths."""

import importlib
from types import SimpleNamespace

index_module = importlib.import_module("pymedphys._trf.manage.index")


def test_logfile_collision_does_not_print_patient_path(tmp_path, monkeypatch, capsys):
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
    patient = "SYNTHETIC_PATIENT_123456"
    filename = tmp_path / f"{patient}.trf"
    filename.write_bytes(b"synthetic")

    def reject_header(_):
        raise ValueError(f"Bad header for {patient}")

    moves = []
    monkeypatch.setattr(index_module, "decode_header_from_file", reject_header)
    monkeypatch.setattr(
        index_module, "rename_and_handle_fileexists",
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
        index_module, "create_logfile_directory_name",
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
