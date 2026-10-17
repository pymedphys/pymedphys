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

import fractions
import logging
import operator
import os
import re
import subprocess
import sys
import warnings

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import isolated_decoding
from pymedphys._dicom.deidentify.diagnostics import redacted_diagnostics
from pymedphys._dicom.deidentify.isolated_decoding import (
    DecoderEnded,
    DecoderUnavailable,
    DecodingFailed,
    run,
)


SENTINEL = "SENTINEL^NAME"


def future_behaviour():
    """Return whether pydicom imitates its future behaviour, in the child."""
    return pydicom.config._use_future  # pylint: disable = protected-access


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


def test_a_result_of_another_class_ends_the_child_and_is_not_loaded():
    with pytest.raises(DecoderEnded):
        run(fractions.Fraction, 1, 2)

    assert run(operator.add, 1, 2) == 3


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


def test_a_warning_in_the_child_is_issued_again_in_the_caller():
    with pytest.warns(UserWarning, match=re.escape(SENTINEL)):
        run(warnings.warn, SENTINEL)


def test_a_warning_that_the_callers_filters_make_an_error_raises():
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        with pytest.raises(DeprecationWarning):
            run(warnings.warn, SENTINEL, DeprecationWarning)


def test_the_callers_redaction_applies_to_the_childs_diagnostics(caplog):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with redacted_diagnostics() as counts:
            run(warnings.warn, SENTINEL)
            run(logging.getLogger("pydicom").warning, SENTINEL)

    assert counts.warnings == 1
    assert counts.log_records == 1
    assert len(caught) == 1
    assert SENTINEL not in str(caught[0].message)
    assert SENTINEL not in caplog.text


def test_a_record_of_pydicom_in_the_child_is_handled_in_the_caller(caplog):
    with caplog.at_level(logging.WARNING, logger="pydicom"):
        run(logging.getLogger("pydicom").warning, SENTINEL)

    assert [(r.name, r.levelno, r.getMessage()) for r in caplog.records] == [
        ("pydicom", logging.WARNING, SENTINEL)
    ]


@pytest.mark.parametrize("future", [False, True])
def test_the_child_imitates_pydicoms_future_behaviour_as_the_caller_does(future):
    # pydicom has no public getter for the current setting.
    was_future = pydicom.config._use_future  # pylint: disable = protected-access
    pydicom.config.future_behavior(future)
    try:
        assert run(future_behaviour) is future
    finally:
        pydicom.config.future_behavior(was_future)


def test_a_child_that_ended_between_calls_is_replaced_before_the_next():
    run(operator.add, 1, 2)
    isolated_decoding._child.process.kill()  # pylint: disable = protected-access
    isolated_decoding._child.process.wait()  # pylint: disable = protected-access

    assert run(operator.add, 1, 2) == 3


@pytest.mark.skipif(sys.platform == "win32", reason="no core file size limit")
def test_the_child_writes_no_core_file():
    import resource  # pylint: disable = import-outside-toplevel, import-error

    assert run(resource.getrlimit, resource.RLIMIT_CORE) == (0, 0)


def test_a_child_that_cannot_start_leaves_the_decoder_unavailable(
    monkeypatch, tmp_path
):
    isolated_decoding._discard()  # pylint: disable = protected-access
    monkeypatch.setattr(sys, "executable", os.fspath(tmp_path / "no-python"))

    with pytest.raises(DecoderUnavailable):
        run(operator.add, 1, 2)


def test_a_child_that_ends_before_it_is_ready_leaves_the_decoder_unavailable(
    monkeypatch,
):
    isolated_decoding._discard()  # pylint: disable = protected-access
    monkeypatch.setattr(isolated_decoding, "_BOOTSTRAP", "import sys\nsys.exit(0)\n")

    with pytest.raises(DecoderUnavailable):
        run(operator.add, 1, 2)
    monkeypatch.undo()
    assert run(operator.add, 1, 2) == 3


def test_what_is_written_to_standard_output_as_the_child_starts_is_not_read(
    monkeypatch,
):
    isolated_decoding._discard()  # pylint: disable = protected-access
    bootstrap = isolated_decoding._BOOTSTRAP.replace(  # pylint: disable = protected-access
        "stream = sys.stdin.buffer\n", "print('x' * 64)\nstream = sys.stdin.buffer\n"
    )
    assert bootstrap != isolated_decoding._BOOTSTRAP  # pylint: disable = protected-access
    monkeypatch.setattr(isolated_decoding, "_BOOTSTRAP", bootstrap)

    assert run(operator.add, 1, 2) == 3
    isolated_decoding._discard()  # pylint: disable = protected-access


@pytest.mark.skipif(not hasattr(os, "fork"), reason="no fork")
@pytest.mark.filterwarnings("ignore::DeprecationWarning")
def test_a_forked_process_starts_its_own_child():
    run(operator.add, 1, 2)

    pid = os.fork()
    if pid == 0:
        code = 1
        try:
            if isolated_decoding._child is None and run(operator.add, 2, 2) == 4:  # pylint: disable = protected-access
                code = 0
        finally:
            os._exit(code)  # pylint: disable = protected-access
    _, status = os.waitpid(pid, 0)

    assert os.waitstatus_to_exitcode(status) == 0
    assert run(operator.add, 1, 2) == 3
