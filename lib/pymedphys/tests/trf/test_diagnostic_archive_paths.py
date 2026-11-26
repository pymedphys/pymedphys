# Copyright (C) 2026 PyMedPhys contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Archive destination confinement for linac diagnostic ZIPs."""

from pymedphys._imports import pytest
from pymedphys._trf.manage.diagnostics_zips import already_indexed_path


def test_archive_path_keeps_valid_machine_subdirectory(tmp_path):
    incoming = tmp_path / "to_be_indexed"
    archived = tmp_path / "already_indexed"
    incoming.mkdir()
    source = incoming / "linac-1" / "SDD+123.zip"
    expected = archived / "linac-1" / "SDD+123.zip"
    assert already_indexed_path(source, incoming, archived) == str(expected)


def test_archive_path_rejects_sibling_source(tmp_path):
    incoming = tmp_path / "to_be_indexed"
    incoming.mkdir()
    archived = tmp_path / "already_indexed"
    outsider = tmp_path / "outside.zip"
    with pytest.raises(ValueError, match="outside the to-be-indexed"):
        already_indexed_path(outsider, incoming, archived)


def test_archive_path_rejects_linked_source(tmp_path):
    incoming = tmp_path / "to_be_indexed"
    incoming.mkdir()
    external = tmp_path / "outside"
    external.mkdir()
    try:
        (incoming / "linked").symlink_to(external, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Directory symlinks are unavailable")
    with pytest.raises(ValueError, match="outside the to-be-indexed"):
        already_indexed_path(incoming / "linked" / "a.zip", incoming, tmp_path / "already_indexed")


def test_archive_path_rejects_symlinked_destination(tmp_path):
    incoming = tmp_path / "to_be_indexed"
    incoming.mkdir()
    source = incoming / "machine" / "a.zip"
    archived = tmp_path / "already_indexed"
    archived.mkdir()
    external = tmp_path / "outside"
    external.mkdir()
    try:
        (archived / "machine").symlink_to(external, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Directory symlinks are unavailable")
    with pytest.raises(ValueError, match="outside the already-indexed"):
        already_indexed_path(source, incoming, archived)
