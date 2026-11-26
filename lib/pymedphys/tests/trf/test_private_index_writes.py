# Copyright (C) 2026 PyMedPhys contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Logfile indexes must be persisted without predictable temporary files."""

import json
import os
import stat

from pymedphys._imports import pytest
from pymedphys._trf.manage import index as indexing


def test_index_write_replaces_data_and_cleans_temp_files(tmp_path):
    target = tmp_path / "index.json"
    target.write_text("old", encoding="utf-8")
    indexing.write_index(target, {"abc": {"filepath": "a.trf"}})
    assert json.loads(target.read_text(encoding="utf-8")) == {
        "abc": {"filepath": "a.trf"}
    }
    assert sorted(path.name for path in tmp_path.iterdir()) == ["index.json"]


@pytest.mark.skipif(os.name == "nt", reason="POSIX permissions only")
def test_index_write_is_owner_only(tmp_path):
    target = tmp_path / "index.json"
    indexing.write_index(target, {"abc": 1})
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_index_write_does_not_follow_old_temp_name_symlink(tmp_path):
    old_target = tmp_path / "index.json"
    external = tmp_path / "external.json"
    external.write_text("sensitive", encoding="utf-8")
    try:
        (tmp_path / "index_temp.json").symlink_to(external)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks are unavailable")
    indexing.write_index(old_target, {"abc": 1})
    assert external.read_text(encoding="utf-8") == "sensitive"
    assert json.loads(old_target.read_text(encoding="utf-8")) == {"abc": 1}


def test_index_write_cleans_temp_file_after_failed_replace(tmp_path, monkeypatch):
    target = tmp_path / "index.json"

    def fail_replace(*_):
        raise OSError("synthetic failed rename")

    monkeypatch.setattr(indexing.os, "replace", fail_replace)
    with pytest.raises(OSError, match="synthetic failed rename"):
        indexing.write_index(target, {"abc": 1})
    assert list(tmp_path.iterdir()) == []
