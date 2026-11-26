# Copyright (C) 2026 PyMedPhys contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Diagnostic ZIP copying must never replace existing paths or symlinks."""

from pymedphys._imports import pytest
from pymedphys._trf.manage import diagnostics_zips


def _prepare(tmp_path, monkeypatch):
    source = tmp_path / "SDD+source.zip"
    source.write_bytes(b"synthetic archive")
    destination = tmp_path / "incoming"
    destination.mkdir()
    monkeypatch.setattr(diagnostics_zips, "glob", lambda _: [str(source)])
    return source, destination


def test_diagnostic_copy_creates_new_file(tmp_path, monkeypatch):
    source, destination = _prepare(tmp_path, monkeypatch)
    diagnostics_zips.fetch_system_diagnostics("127.0.0.1", destination)
    assert (destination / source.name).read_bytes() == source.read_bytes()


def test_diagnostic_copy_preserves_existing_file(tmp_path, monkeypatch):
    source, destination = _prepare(tmp_path, monkeypatch)
    existing = destination / source.name
    existing.write_bytes(b"original")
    diagnostics_zips.fetch_system_diagnostics("127.0.0.1", destination)
    assert existing.read_bytes() == b"original"


def test_diagnostic_copy_refuses_dangling_symlink(tmp_path, monkeypatch):
    source, destination = _prepare(tmp_path, monkeypatch)
    external = tmp_path / "external.zip"
    try:
        (destination / source.name).symlink_to(external)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks are unavailable")
    diagnostics_zips.fetch_system_diagnostics("127.0.0.1", destination)
    assert not external.exists()


def test_diagnostic_copy_preserves_already_indexed_alias(tmp_path, monkeypatch):
    source, destination = _prepare(tmp_path, monkeypatch)
    archived = tmp_path / "archived"
    archived.mkdir()
    external = tmp_path / "external.zip"
    try:
        (archived / source.name).symlink_to(external)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks are unavailable")
    diagnostics_zips.fetch_system_diagnostics("127.0.0.1", destination, archived)
    assert not (destination / source.name).exists()
