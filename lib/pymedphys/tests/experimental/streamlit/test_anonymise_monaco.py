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

"""Where the Monaco anonymisation app creates and deletes files."""

import os
import pathlib

from pymedphys._imports import pytest

pytest.importorskip("streamlit")

# The app imports the Streamlit utilities at import time, so this import must
# come after the skip guard.
from pymedphys._experimental.streamlit.apps import anonymise_monaco  # noqa: E402


def test_file_name_resolves_inside_directory(tmp_path):
    path = anonymise_monaco._path_within(tmp_path, "012345.zip")

    assert path == pathlib.Path(os.path.realpath(tmp_path), "012345.zip")


@pytest.mark.parametrize(
    "name",
    ["../012345.zip", "archive/../../012345.zip", "..", "."],
)
def test_file_name_leaving_directory_is_refused(tmp_path, name):
    directory = tmp_path / "export"
    directory.mkdir()

    with pytest.raises(ValueError):
        anonymise_monaco._path_within(directory, name)


def test_absolute_file_name_is_refused(tmp_path):
    directory = tmp_path / "export"
    directory.mkdir()

    with pytest.raises(ValueError):
        anonymise_monaco._path_within(directory, str(tmp_path / "012345.zip"))


def test_symbolic_link_out_of_directory_is_refused(tmp_path):
    directory = tmp_path / "export"
    directory.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (directory / "link").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Creating symbolic links is not permitted here")

    with pytest.raises(ValueError):
        anonymise_monaco._path_within(directory, "link/012345.zip")
