# Copyright (C) 2026 jdotc1

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""Regression coverage for traversal-safe machine diagnostic directories."""

import os

import pytest

from pymedphys._trf.manage import diagnostics_zips


def test_machine_diagnostic_paths_use_normal_subdirectories(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        diagnostics_zips,
        "fetch_system_diagnostics",
        lambda *args, **_kwargs: calls.append(args),
    )
    diagnostics_zips.fetch_system_diagnostics_multi_linac(
        {"Linac A": "192.0.2.10"}, tmp_path
    )
    assert calls == [
        (
            "192.0.2.10",
            str((tmp_path / "to_be_indexed" / "Linac A").resolve()),
            str((tmp_path / "already_indexed" / "Linac A").resolve()),
        )
    ]
    assert (tmp_path / "to_be_indexed" / "Linac A").is_dir()


@pytest.mark.parametrize(
    "machine",
    [
        "",
        ".",
        "..",
        ".. ",
        ".. .",
        "Linac A.",
        "Linac A ",
        "Linac A/.",
        "CON",
        "con.txt",
        "NUL",
        "LPT1.log",
        "bad:name",
        "bad?name",
        "../escape",
        "nested/machine",
        "/tmp/escape",
        r"..\escape",
        r"C:\escape",
        "bad\nmachine",
        "bad\x00name",
    ],
)
def test_machine_id_cannot_select_another_directory(tmp_path, monkeypatch, machine):
    monkeypatch.setattr(
        diagnostics_zips,
        "fetch_system_diagnostics",
        lambda *_args, **_kwargs: pytest.fail(
            "No copy may start for an invalid machine"
        ),
    )
    with pytest.raises(ValueError, match="Machine identifier"):
        diagnostics_zips.fetch_system_diagnostics_multi_linac(
            {machine: "192.0.2.10"}, tmp_path
        )


def test_machine_id_cannot_follow_existing_symlink_outside_root(tmp_path, monkeypatch):
    indexed_root = tmp_path / "to_be_indexed"
    indexed_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (indexed_root / "alias").symlink_to(outside, target_is_directory=True)
    except (NotImplementedError, OSError):
        pytest.skip("Directory symlinks unavailable")

    monkeypatch.setattr(
        diagnostics_zips,
        "fetch_system_diagnostics",
        lambda *_args, **_kwargs: pytest.fail(
            "No copy may start through an unsafe symlink"
        ),
    )
    with pytest.raises(ValueError, match="symlink|reparse"):
        diagnostics_zips.fetch_system_diagnostics_multi_linac(
            {"alias": "192.0.2.10"}, tmp_path
        )


def test_machine_names_cannot_alias_on_case_insensitive_filesystems(tmp_path):
    with pytest.raises(ValueError, match="alias"):
        diagnostics_zips.fetch_system_diagnostics_multi_linac(
            {"Linac A": "192.0.2.10", "linac a": "192.0.2.11"}, tmp_path
        )
    assert not (tmp_path / "to_be_indexed").exists()


@pytest.mark.parametrize("root_arg", ["to_be_indexed", "already_indexed"])
def test_diagnostics_root_cannot_be_symlink_outside_storage(tmp_path, root_arg):
    storage = tmp_path / "storage"
    storage.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (storage / root_arg).symlink_to(outside, target_is_directory=True)
    except (NotImplementedError, OSError):
        pytest.skip("Directory symlinks unavailable")

    with pytest.raises(ValueError, match="symlink|reparse"):
        diagnostics_zips.fetch_system_diagnostics_multi_linac(
            {"Linac A": "192.0.2.10"}, storage
        )
    assert not (outside / "Linac A").exists()


@pytest.mark.parametrize("directory_name", ["to_be_indexed", "already_indexed"])
@pytest.mark.parametrize("target", ["sibling", "outside"])
def test_machine_directory_cannot_be_symlink_alias(tmp_path, directory_name, target):
    storage = tmp_path / "storage"
    parent = storage / directory_name
    parent.mkdir(parents=True)
    destination = (
        (parent / "other-machine") if target == "sibling" else tmp_path / "outside"
    )
    destination.mkdir()
    try:
        (parent / "alias").symlink_to(destination, target_is_directory=True)
    except (NotImplementedError, OSError):
        pytest.skip("Directory symlinks unavailable")

    with pytest.raises(ValueError, match="symlink|reparse"):
        diagnostics_zips.fetch_system_diagnostics_multi_linac(
            {"alias": "192.0.2.10"}, storage
        )
    assert not list(destination.iterdir())


def test_reject_unsafe_custom_root_names(tmp_path):
    with pytest.raises(ValueError, match="Directory identifier"):
        diagnostics_zips.fetch_system_diagnostics_multi_linac(
            {"Linac A": "192.0.2.10"}, tmp_path, already_indexed="../archive"
        )


def test_anchored_copy_ignores_machine_symlink_inserted_after_open(
    tmp_path, monkeypatch
):
    if os.name == "nt":
        pytest.skip("Windows directory handles prevent renaming while pinned")
    storage = tmp_path / "storage"
    outside = tmp_path / "outside"
    outside.mkdir()
    source = tmp_path / "SDD+sample.zip"
    source.write_bytes(b"test-data")
    machine_path = storage / "to_be_indexed" / "Linac A"
    renamed = machine_path.with_name("moved-machine")

    def swap_during_glob(_pattern):
        machine_path.rename(renamed)
        machine_path.symlink_to(outside, target_is_directory=True)
        return [str(source)]

    monkeypatch.setattr(diagnostics_zips, "glob", swap_during_glob)
    diagnostics_zips.fetch_system_diagnostics_multi_linac(
        {"Linac A": "192.0.2.10"}, storage
    )
    assert not list(outside.iterdir())
    assert (renamed / source.name).read_bytes() == b"test-data"


def test_existing_destination_symlink_is_rejected(tmp_path, monkeypatch):
    storage = tmp_path / "storage"
    machine = storage / "to_be_indexed" / "Linac A"
    machine.mkdir(parents=True)
    outside = tmp_path / "outside.zip"
    outside.write_bytes(b"leave unchanged")
    try:
        (machine / "SDD+sample.zip").symlink_to(outside)
    except (NotImplementedError, OSError):
        pytest.skip("File symlinks unavailable")
    source = tmp_path / "SDD+sample.zip"
    source.write_bytes(b"should not copy")
    monkeypatch.setattr(diagnostics_zips, "glob", lambda _pattern: [str(source)])

    with pytest.raises(ValueError, match="not a regular file"):
        diagnostics_zips.fetch_system_diagnostics_multi_linac(
            {"Linac A": "192.0.2.10"}, storage
        )
    assert outside.read_bytes() == b"leave unchanged"


def test_copy_and_archive_duplicate_detection(tmp_path, monkeypatch):
    source = tmp_path / "SDD+sample.zip"
    source.write_bytes(b"original")
    monkeypatch.setattr(diagnostics_zips, "glob", lambda _pattern: [str(source)])
    storage = tmp_path / "storage"
    machine_map = {"Linac A": "192.0.2.10"}
    diagnostics_zips.fetch_system_diagnostics_multi_linac(machine_map, storage)
    pending = storage / "to_be_indexed" / "Linac A" / source.name
    assert pending.read_bytes() == b"original"
    pending.replace(storage / "already_indexed" / "Linac A" / source.name)
    source.write_bytes(b"changed")
    diagnostics_zips.fetch_system_diagnostics_multi_linac(machine_map, storage)
    assert not pending.exists()
    archived_file = storage / "already_indexed" / "Linac A" / source.name
    assert archived_file.read_bytes() == b"original"
