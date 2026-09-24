# Copyright (C) 2026 Matthew Jennings

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Offline checks of the data download helper."""

import pathlib

from pymedphys._imports import pytest

from pymedphys._data import download


def test_file_url_is_copied(tmp_path: pathlib.Path):
    source = tmp_path / "source.bin"
    payload = bytes(range(256)) * 4
    source.write_bytes(payload)
    destination = tmp_path / "destination.bin"

    download.download_with_progress(source.as_uri(), destination)

    assert destination.read_bytes() == payload


@pytest.mark.parametrize("url", ["ftp://example.invalid/data.zip", "data:,hello"])
def test_unsupported_scheme_is_rejected(url: str, tmp_path: pathlib.Path):
    destination = tmp_path / "unused.bin"

    with pytest.raises(ValueError, match="Unsupported URL scheme"):
        download.download_with_progress(url, destination)

    assert not destination.exists()
