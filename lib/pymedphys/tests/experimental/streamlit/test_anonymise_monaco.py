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
from pymedphys._experimental.streamlit.apps.anonymise_monaco import (  # noqa: E402
    _path_within,
    _reject_source_links,
)


def test_file_name_resolves_inside_directory(tmp_path):
    path = _path_within(tmp_path, "012345.zip")

    assert path == pathlib.Path(os.path.realpath(tmp_path), "012345.zip")


@pytest.mark.parametrize(
    "name",
    ["../012345.zip", "archive/../../012345.zip", "..", "."],
)
def test_file_name_leaving_directory_is_refused(tmp_path, name):
    directory = tmp_path / "export"
    directory.mkdir()

    with pytest.raises(ValueError):
        _path_within(directory, name)


def test_absolute_file_name_is_refused(tmp_path):
    directory = tmp_path / "export"
    directory.mkdir()

    with pytest.raises(ValueError):
        _path_within(directory, str(tmp_path / "012345.zip"))


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
        _path_within(directory, "link/012345.zip")


def test_symbolic_link_inside_directory_is_the_entry_itself(tmp_path):
    """Deleting a patient's zip file that is a link to another export removes
    the link, not the other export."""
    directory = tmp_path / "export"
    directory.mkdir()
    other_export = directory / "654321.zip"
    other_export.write_bytes(b"another patient's export")
    link = directory / "012345.zip"
    try:
        link.symlink_to(other_export)
    except OSError:
        pytest.skip("Creating symbolic links is not permitted here")

    path = _path_within(directory, "012345.zip")
    path.unlink()

    assert not os.path.lexists(link)
    assert other_export.read_bytes() == b"another patient's export"


def test_symbolic_link_to_a_file_outside_directory_is_refused(tmp_path):
    directory = tmp_path / "export"
    directory.mkdir()
    try:
        (directory / "012345.zip").symlink_to(tmp_path / "012345.zip")
    except OSError:
        pytest.skip("Creating symbolic links is not permitted here")

    with pytest.raises(ValueError):
        _path_within(directory, "012345.zip")


def test_monaco_source_without_links_is_accepted(tmp_path):
    patient = tmp_path / "patient"
    patient.mkdir()
    (patient / "nested").mkdir()
    (patient / "nested" / "safe.txt").write_text("synthetic", encoding="utf-8")

    _reject_source_links(patient)


@pytest.mark.parametrize("link_is_directory", [False, True])
def test_monaco_source_refuses_linked_external_content(tmp_path, link_is_directory):
    patient = tmp_path / "patient"
    patient.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    target = outside if link_is_directory else outside / "private.txt"
    if not link_is_directory:
        target.write_text("synthetic-private", encoding="utf-8")
    try:
        (patient / "linked").symlink_to(target, target_is_directory=link_is_directory)
    except OSError:
        pytest.skip("Creating symbolic links is not permitted here")

    with pytest.raises(ValueError, match="symbolic link"):
        _reject_source_links(patient)


def test_monaco_source_refuses_symlinked_root(tmp_path):
    patient = tmp_path / "patient"
    patient.mkdir()
    link = tmp_path / "linked-patient"
    try:
        link.symlink_to(patient, target_is_directory=True)
    except OSError:
        pytest.skip("Creating symbolic links is not permitted here")

    with pytest.raises(ValueError, match="symbolic link"):
        _reject_source_links(link)
