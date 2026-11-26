# Copyright (C) 2026 PyMedPhys contributors
#
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

"""Confinement of paths read from the logfile index."""

from pymedphys._imports import pytest
from pymedphys._utilities.config import get_filepath


def test_indexed_logfile_path_within_root(tmp_path):
    root = tmp_path / "logfiles"
    root.mkdir()
    index = {"hash": {"filepath": "machine/2026.trf"}}
    result = get_filepath(index, {"linac_logfile_data_directory": str(root)}, "hash")
    assert result == str(root / "indexed" / "machine" / "2026.trf")


@pytest.mark.parametrize("filename", ["../../outside.trf", "/tmp/outside.trf"])
def test_indexed_logfile_path_does_not_escape_root(tmp_path, filename):
    config = {"linac_logfile_data_directory": str(tmp_path / "logfiles")}
    index = {"hash": {"filepath": filename}}
    with pytest.raises(ValueError, match="outside indexed data directory"):
        get_filepath(index, config, "hash")


def test_indexed_logfile_path_rejects_symlink_escape(tmp_path):
    indexed = tmp_path / "logfiles" / "indexed"
    indexed.mkdir(parents=True)
    external = tmp_path / "external"
    external.mkdir()
    try:
        (indexed / "linked").symlink_to(external, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Directory symlinks are unavailable")
    config = {"linac_logfile_data_directory": str(tmp_path / "logfiles")}
    index = {"hash": {"filepath": "linked/patient.trf"}}
    with pytest.raises(ValueError, match="outside indexed data directory"):
        get_filepath(index, config, "hash")
