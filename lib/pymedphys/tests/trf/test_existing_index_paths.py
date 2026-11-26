# Copyright (C) 2026 PyMedPhys contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Imported logfile index entries cannot escape the indexed directory."""

from pymedphys._imports import pytest
from pymedphys._trf.manage.index import confined_index_path


def test_existing_index_accepts_nested_logfile(tmp_path):
    root = tmp_path / "indexed"
    root.mkdir()
    expected = root / "centre" / "delivery.trf"
    assert confined_index_path(root, "centre/delivery.trf") == str(expected)


@pytest.mark.parametrize(
    "path", ["../../elsewhere.trf", "../elsewhere.trf", "/tmp/elsewhere.trf"]
)
def test_existing_index_rejects_parent_or_absolute_escape(tmp_path, path):
    root = tmp_path / "indexed"
    root.mkdir()
    with pytest.raises(ValueError, match="outside the indexed directory"):
        confined_index_path(root, path)


def test_existing_index_rejects_symlink_escape(tmp_path):
    root = tmp_path / "indexed"
    root.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    try:
        (root / "linked").symlink_to(external, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Directory symlinks are unavailable")
    with pytest.raises(ValueError, match="outside the indexed directory"):
        confined_index_path(root, "linked/record.trf")
