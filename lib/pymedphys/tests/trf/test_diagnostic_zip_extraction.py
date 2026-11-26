# Copyright (C) 2026 PyMedPhys contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""An untrusted diagnostic ZIP must never write outside the TRF intake."""

import zipfile

from pymedphys._imports import pytest
from pymedphys._trf.manage.diagnostics_zips import (
    extract_diagnostic_zips_and_archive,
)


def _archive(root, name):
    incoming = root / "diagnostics" / "to_be_indexed" / "linac-1"
    incoming.mkdir(parents=True)
    archive = incoming / "SDD+fixture.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr(name, b"synthetic log bytes")
    return archive


@pytest.mark.parametrize(
    "name", ["../outside.trf", "/absolute.trf", "C:/outside.trf", "nested\\outside.trf"]
)
def test_diagnostic_zip_rejects_unsafe_member_names(tmp_path, name):
    archive = _archive(tmp_path, name)
    with pytest.raises(ValueError, match="Unsafe diagnostic ZIP member"):
        extract_diagnostic_zips_and_archive(tmp_path)
    assert archive.exists()
    assert not (tmp_path / "outside.trf").exists()


def test_diagnostic_zip_rejects_preexisting_symlink_escape(tmp_path):
    _archive(tmp_path, "link/escape.trf")
    extraction = tmp_path / "to_be_indexed"
    extraction.mkdir()
    target = tmp_path / "external"
    target.mkdir()
    try:
        (extraction / "link").symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Directory symlinks are unavailable")
    with pytest.raises(ValueError, match="Unsafe diagnostic ZIP member"):
        extract_diagnostic_zips_and_archive(tmp_path)
    assert not (target / "escape.trf").exists()


def test_diagnostic_zip_extracts_safe_trf_and_archives_source(tmp_path):
    _archive(tmp_path, "machine/good.trf")
    extract_diagnostic_zips_and_archive(tmp_path)
    assert (
        tmp_path / "to_be_indexed" / "machine" / "good.trf"
    ).read_bytes() == b"synthetic log bytes"
    assert (
        tmp_path / "diagnostics" / "already_indexed" / "linac-1" / "SDD+fixture.zip"
    ).exists()
