# Copyright (C) 2026 Jeffrey D. Cooney

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""Security regression tests for index.json logfile path resolution."""

import json
import os
from pathlib import Path

import pytest

from pymedphys._utilities.config import _open_indexed_logfile, get_filepath


def _entry(relative_path):
    return {"synthetic_hash": {"filepath": relative_path}}


def test_get_filepath_preserves_valid_relative_logfile_path(tmp_path):
    expected = tmp_path / "indexed" / "clinic" / "fraction.trf"
    resolved = get_filepath(
        _entry("clinic/fraction.trf"),
        {"linac_logfile_data_directory": str(tmp_path)},
        "synthetic_hash",
    )
    assert resolved == os.path.abspath(expected)


@pytest.mark.parametrize(
    "invalid",
    [
        "../outside.trf",
        "../../outside.trf",
        "/tmp/outside.trf",
    ],
)
def test_get_filepath_rejects_absolute_and_traversal_entries(tmp_path, invalid):
    with pytest.raises(ValueError, match="escapes the indexed directory"):
        get_filepath(
            _entry(invalid),
            {"linac_logfile_data_directory": str(tmp_path)},
            "synthetic_hash",
        )


def test_get_filepath_rejects_symlink_alias_outside_root(tmp_path):
    indexed = tmp_path / "indexed"
    indexed.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    try:
        (indexed / "alias").symlink_to(external, target_is_directory=True)
    except (NotImplementedError, OSError):
        pytest.skip("Directory symlinks unavailable")

    with pytest.raises(ValueError, match="escapes the indexed directory"):
        get_filepath(
            _entry("alias/clinical.trf"),
            {"linac_logfile_data_directory": str(tmp_path)},
            "synthetic_hash",
        )


def test_get_filepath_returns_resolved_path_for_in_root_symlink(tmp_path):
    indexed = tmp_path / "indexed"
    actual = indexed / "actual"
    actual.mkdir(parents=True)
    logfile = actual / "fraction.trf"
    logfile.write_bytes(b"internal record")
    alias = indexed / "alias"
    try:
        alias.symlink_to(actual, target_is_directory=True)
    except (NotImplementedError, OSError):
        pytest.skip("Directory symlinks unavailable")

    resolved = get_filepath(
        _entry("alias/fraction.trf"),
        {"linac_logfile_data_directory": str(tmp_path)},
        "synthetic_hash",
    )
    assert resolved == str(logfile.resolve())

    # Swapping the checked alias must not redirect the returned filename.
    external = tmp_path / "external"
    external.mkdir()
    (external / "fraction.trf").write_bytes(b"external record")
    alias.unlink()
    alias.symlink_to(external, target_is_directory=True)
    assert Path(resolved).read_bytes() == b"internal record"


def test_get_filepath_hides_symlink_loop_resolution_errors(tmp_path):
    indexed = tmp_path / "indexed"
    indexed.mkdir()
    try:
        (indexed / "loop").symlink_to("loop")
    except (NotImplementedError, OSError):
        pytest.skip("Symlinks unavailable")

    with pytest.raises(ValueError, match="escapes the indexed directory") as exc:
        get_filepath(
            _entry("loop"),
            {"linac_logfile_data_directory": str(tmp_path)},
            "synthetic_hash",
        )
    assert str(tmp_path) not in str(exc.value)


def test_get_filepath_rejects_non_regular_files(tmp_path):
    if not hasattr(os, "mkfifo"):
        pytest.skip("Named pipes unavailable")
    indexed = tmp_path / "indexed"
    indexed.mkdir()
    os.mkfifo(indexed / "pipe")
    with pytest.raises(ValueError, match="escapes the indexed directory"):
        get_filepath(
            _entry("pipe"),
            {"linac_logfile_data_directory": str(tmp_path)},
            "synthetic_hash",
        )


def test_get_filepath_allows_case_variant_on_case_insensitive_volume(tmp_path):
    indexed = tmp_path / "indexed"
    indexed.mkdir()
    case_variant = tmp_path / "INDEXED"
    if not case_variant.exists() or not os.path.samefile(case_variant, indexed):
        pytest.skip("Requires a case-insensitive filesystem")

    nested = indexed / "nested"
    nested.mkdir()
    logfile = nested / "fraction.trf"
    logfile.write_bytes(b"internal record")
    try:
        (indexed / "alias").symlink_to(
            case_variant / "nested", target_is_directory=True
        )
    except (NotImplementedError, OSError):
        pytest.skip("Directory symlinks unavailable")

    resolved = get_filepath(
        _entry("alias/fraction.trf"),
        {"linac_logfile_data_directory": str(tmp_path)},
        "synthetic_hash",
    )
    assert Path(resolved).samefile(logfile)


@pytest.mark.parametrize("invalid_kind", ["traversal", "absolute", "symlink"])
def test_index_logfiles_rejects_untrusted_index_paths_before_hashing(
    tmp_path, monkeypatch, invalid_kind
):
    from pymedphys._trf.manage import index as trf_index

    staged_dir = tmp_path / "to_be_indexed"
    staged_dir.mkdir()
    staged_file = staged_dir / "incoming.trf"
    staged_file.write_bytes(b"synthetic staged logfile")

    if invalid_kind == "traversal":
        malicious_path = "../external.trf"
    elif invalid_kind == "absolute":
        malicious_path = str(tmp_path / "external.trf")
    else:
        indexed = tmp_path / "indexed"
        indexed.mkdir()
        external = tmp_path / "external.trf"
        external.write_bytes(b"unbounded or confidential external data")
        try:
            (indexed / "escape").symlink_to(external)
        except (NotImplementedError, OSError):
            pytest.skip("Symlinks unavailable")
        malicious_path = "escape"

    (tmp_path / "index.json").write_text(
        json.dumps({"synthetic_hash": {"filepath": malicious_path}}),
        encoding="utf-8",
    )
    hashed_files = []

    def fake_hash_file(filename, dot_feedback=False):
        hashed_files.append(Path(filename))
        if Path(filename) != staged_file:
            pytest.fail("An unvalidated indexed path was passed to hash_file")
        return "synthetic_hash"

    monkeypatch.setattr(trf_index, "hash_file", fake_hash_file)
    with pytest.raises(ValueError, match="escapes the indexed directory"):
        trf_index.index_logfiles({}, {}, tmp_path)

    assert hashed_files == [staged_file]
    assert staged_file.exists()



def test_indexed_root_symlink_is_rejected(tmp_path):
    outside = tmp_path / "external"
    outside.mkdir()
    (outside / "fraction.trf").write_bytes(b"out-of-root")
    indexed = tmp_path / "indexed"
    try:
        indexed.symlink_to(outside, target_is_directory=True)
    except (NotImplementedError, OSError):
        pytest.skip("Directory symlinks unavailable")

    with pytest.raises(ValueError, match="escapes the indexed directory"):
        get_filepath(
            _entry("fraction.trf"),
            {"linac_logfile_data_directory": str(tmp_path)},
            "synthetic_hash",
        )
    with pytest.raises(ValueError, match="escapes the indexed directory"):
        with _open_indexed_logfile(indexed, "fraction.trf"):
            pytest.fail("A symlinked indexed root was opened")


def test_indexed_path_rejects_parent_components_even_when_contained(tmp_path):
    indexed = tmp_path / "indexed"
    (indexed / "nested").mkdir(parents=True)
    (indexed / "fraction.trf").write_bytes(b"record")
    with pytest.raises(ValueError, match="escapes the indexed directory"):
        get_filepath(
            _entry("nested/../fraction.trf"),
            {"linac_logfile_data_directory": str(tmp_path)},
            "synthetic_hash",
        )


def test_secure_open_pins_valid_in_root_symlink_target(tmp_path):
    indexed = tmp_path / "indexed"
    actual = indexed / "actual"
    actual.mkdir(parents=True)
    (actual / "fraction.trf").write_bytes(b"internal")
    alias = indexed / "alias"
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "fraction.trf").write_bytes(b"confidential")
    try:
        alias.symlink_to(actual, target_is_directory=True)
    except (NotImplementedError, OSError):
        pytest.skip("Directory symlinks unavailable")

    with _open_indexed_logfile(indexed, "alias/fraction.trf") as archive:
        alias.unlink()
        alias.symlink_to(outside, target_is_directory=True)
        assert archive.read() == b"internal"


@pytest.mark.skipif(
    os.name != "posix" or not hasattr(os, "O_NOFOLLOW"),
    reason="Openat no-follow race regression requires POSIX",
)
@pytest.mark.parametrize("swapped_component", ["root", "directory", "file"])
def test_secure_open_rejects_symlink_swap_during_open(
    tmp_path, monkeypatch, swapped_component
):
    from pymedphys._utilities import config as config_module

    indexed = tmp_path / "indexed"
    actual = indexed / "actual"
    actual.mkdir(parents=True)
    original = actual / "fraction.trf"
    original.write_bytes(b"internal")
    outside = tmp_path / "outside"
    (outside / "actual").mkdir(parents=True)
    external = outside / "actual" / "fraction.trf"
    external.write_bytes(b"confidential")

    real_open = os.open
    swapped = []

    def swap_before_open(path, flags, *args, **kwargs):
        if not swapped and kwargs.get("dir_fd") is not None:
            if swapped_component == "root" and str(path) == "indexed":
                indexed.rename(tmp_path / "former_indexed")
                indexed.symlink_to(outside, target_is_directory=True)
                swapped.append(True)
            elif swapped_component == "directory" and str(path) == "actual":
                actual.rename(indexed / "former_actual")
                actual.symlink_to(outside / "actual", target_is_directory=True)
                swapped.append(True)
            elif swapped_component == "file" and str(path) == "fraction.trf":
                original.unlink()
                original.symlink_to(external)
                swapped.append(True)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(config_module.os, "open", swap_before_open)
    with pytest.raises(ValueError, match="escapes the indexed directory"):
        with _open_indexed_logfile(indexed, "actual/fraction.trf") as archive:
            archive.read()
    assert swapped


def test_secure_open_rejects_nonregular_file_without_blocking(tmp_path):
    if not hasattr(os, "mkfifo"):
        pytest.skip("Named pipes unavailable")
    indexed = tmp_path / "indexed"
    indexed.mkdir()
    os.mkfifo(indexed / "pipe")
    with pytest.raises(ValueError, match="escapes the indexed directory"):
        with _open_indexed_logfile(indexed, "pipe"):
            pytest.fail("A FIFO was accepted")


@pytest.mark.parametrize("archive_matches", [True, False])
def test_index_logfiles_hashes_open_archive_handle(
    tmp_path, archive_matches
):
    from pymedphys._trf.manage import index as trf_index
    from pymedphys._utilities.filehash import hash_file

    indexed = tmp_path / "indexed"
    indexed.mkdir()
    archived = indexed / "existing.trf"
    staged = tmp_path / "to_be_indexed" / "incoming.trf"
    staged.parent.mkdir()
    staged.write_bytes(b"correct archive contents")
    archived.write_bytes(
        b"correct archive contents" if archive_matches else b"corrupt archive"
    )
    expected_hash = hash_file(staged)
    (tmp_path / "index.json").write_text(
        json.dumps({expected_hash: {"filepath": "existing.trf"}}),
        encoding="utf-8",
    )

    if archive_matches:
        trf_index.index_logfiles({}, {}, tmp_path)
        assert not staged.exists()
    else:
        with pytest.raises(AssertionError, match="doesn't agree"):
            trf_index.index_logfiles({}, {}, tmp_path)
        assert staged.exists()
