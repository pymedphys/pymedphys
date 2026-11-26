# Copyright (C) 2026 Jeff

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Adjacent-directory and chained-link boundaries for Monaco export paths."""

import pathlib

from pymedphys._imports import pytest

pytest.importorskip("streamlit")

from pymedphys._experimental.streamlit.apps.anonymise_monaco import _path_within  # noqa: E402


@pytest.mark.parametrize("suffix", ["-other", "_other", "2"])
def test_shared_directory_prefix_does_not_make_sibling_an_export(tmp_path, suffix):
    export = tmp_path / "export"
    export.mkdir()
    sibling = tmp_path / f"export{suffix}"
    sibling.mkdir()
    sentinel = sibling / "synthetic.zip"
    sentinel.write_bytes(b"must remain outside export")

    with pytest.raises(ValueError):
        _path_within(export, f"../{sibling.name}/{sentinel.name}")

    assert sentinel.read_bytes() == b"must remain outside export"


def test_chained_links_cannot_lead_into_a_sibling_directory(tmp_path):
    export = tmp_path / "export"
    export.mkdir()
    sibling = tmp_path / "export-other"
    sibling.mkdir()
    try:
        (export / "outside").symlink_to(sibling, target_is_directory=True)
        (export / "alias").symlink_to(export / "outside", target_is_directory=True)
    except OSError:
        pytest.skip("Creating symbolic links is not permitted here")

    with pytest.raises(ValueError):
        _path_within(export, "alias/synthetic.zip")


def test_root_alias_and_normalised_internal_path_remain_usable(tmp_path):
    export = tmp_path / "export"
    export.mkdir()
    alias = tmp_path / "export-alias"
    try:
        alias.symlink_to(export, target_is_directory=True)
    except OSError:
        pytest.skip("Creating symbolic links is not permitted here")

    result = _path_within(alias, "nested/../synthetic.zip")
    assert result == pathlib.Path(export.resolve(), "synthetic.zip")
