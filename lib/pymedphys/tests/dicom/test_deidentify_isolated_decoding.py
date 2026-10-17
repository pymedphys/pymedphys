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

"""Calls made in a child process, which can end without ending the caller."""

import operator
import os
import subprocess
import sys

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import isolated_decoding
from pymedphys._dicom.deidentify.isolated_decoding import (
    DecoderEnded,
    DecodingFailed,
    run,
)


def test_a_call_returns_its_result():
    assert run(operator.add, 1, 2) == 3


def test_a_call_that_raises_fails_without_its_message():
    with pytest.raises(DecodingFailed) as failed:
        run(int, "SENTINEL^NAME")

    assert not isinstance(failed.value, DecoderEnded)
    assert "SENTINEL" not in str(failed.value)
    assert failed.value.__cause__ is None


def test_a_call_that_ends_the_child_fails_and_the_next_call_starts_another():
    run(operator.add, 1, 2)
    ended = isolated_decoding._child.process.pid  # pylint: disable = protected-access

    with pytest.raises(DecoderEnded):
        run(os.abort)

    assert run(operator.add, 1, 2) == 3
    assert isolated_decoding._child.process.pid != ended  # pylint: disable = protected-access


def test_what_the_child_writes_to_standard_output_is_not_read_as_a_result():
    assert run(os.write, 1, b"\x00" * 64) == 64
    assert run(operator.add, 1, 2) == 3


def test_the_child_does_not_run_the_main_module_again(tmp_path):
    script = tmp_path / "unguarded.py"
    script.write_text(
        "import operator\n"
        "from pymedphys._dicom.deidentify import isolated_decoding\n"
        "print(isolated_decoding.run(operator.add, 1, 2))\n"
    )

    completed = subprocess.run(
        [sys.executable, os.fspath(script)],
        capture_output=True,
        check=False,
        env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)},
        text=True,
        timeout=300,
    )

    assert completed.returncode == 0
    assert completed.stdout.split() == ["3"]
