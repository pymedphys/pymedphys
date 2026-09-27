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

from pymedphys._imports import pytest

from pymedphys._utilities.filesystem import open_no_lock


def test_open_no_lock_reads_a_file(tmp_path):
    path = tmp_path / "log.txt"
    path.write_text("contents")

    with open_no_lock(path) as a_file:
        assert a_file.read() == "contents"

    assert a_file.closed


def test_open_no_lock_raises_the_original_error(tmp_path):
    # The cleanup used to reference the unopened file, replacing this error
    # with an UnboundLocalError.
    with pytest.raises(FileNotFoundError):
        with open_no_lock(tmp_path / "missing.txt"):
            pass
