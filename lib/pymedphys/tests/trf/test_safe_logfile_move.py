# Copyright (C) 2026 Jeffrey D. Cooney

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Keep existing TRF logfiles intact when archiving a second file."""

from pymedphys._imports import pytest
from pymedphys._trf.manage.index import rename_and_handle_fileexists


def test_archive_move_creates_destination_without_rewriting_source(tmp_path):
    source = tmp_path / "incoming.trf"
    destination = tmp_path / "archived" / "log.trf"
    source.write_bytes(b"one synthetic treatment logfile")

    rename_and_handle_fileexists(source, destination)

    assert not source.exists()
    assert destination.read_bytes() == b"one synthetic treatment logfile"


def test_archive_move_never_replaces_conflicting_destination(tmp_path):
    source = tmp_path / "incoming.trf"
    destination = tmp_path / "archived.trf"
    source.write_bytes(b"second, different synthetic logfile")
    destination.write_bytes(b"previous synthetic logfile")

    with pytest.raises(FileExistsError, match="hash does not match"):
        rename_and_handle_fileexists(source, destination)

    assert source.read_bytes() == b"second, different synthetic logfile"
    assert destination.read_bytes() == b"previous synthetic logfile"


def test_matching_archived_duplicate_only_removes_incoming_file(tmp_path):
    source = tmp_path / "incoming.trf"
    destination = tmp_path / "archived.trf"
    source.write_bytes(b"same content")
    destination.write_bytes(b"same content")

    rename_and_handle_fileexists(source, destination)

    assert not source.exists()
    assert destination.read_bytes() == b"same content"
