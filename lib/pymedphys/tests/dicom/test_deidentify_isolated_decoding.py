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
import json
import logging
import operator
import os
import re
import subprocess
import sys
import time
import types
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


def reading_mode():
    """Return pydicom's validation mode for reading, in the child."""
    return pydicom.config.settings.reading_validation_mode


def logger_level():
    """Return the level of pydicom's logger, in the child."""
    return logging.getLogger("pydicom").level


def modules():
    """Return the names of the modules imported in the child."""
    return sorted(sys.modules)


class _Lazy(types.ModuleType):
    """A module whose attributes cannot be read, as reading a lazy module's
    attributes imports what it stands for."""

    def __getattribute__(self, name):
        raise AssertionError(f"read {name}")


def _reissued(*warned):
    """Return the warnings recorded as those that the child sends are issued
    again, with every warning shown once for each place it is from."""
    returned = isolated_decoding._returned(  # pylint: disable = protected-access
        [True, None, [list(each) for each in warned], []]
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("default")
        isolated_decoding._reissue(returned)  # pylint: disable = protected-access
    return caught


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


def test_a_result_that_json_cannot_encode_fails_the_call_and_keeps_the_child():
    run(operator.add, 1, 2)
    kept = isolated_decoding._child.process.pid  # pylint: disable = protected-access

    with pytest.raises(DecodingFailed) as failed:
        run(fractions.Fraction, 1, 2)

    assert not isinstance(failed.value, DecoderEnded)
    assert run(operator.add, 1, 2) == 3
    assert isolated_decoding._child.process.pid == kept  # pylint: disable = protected-access


def test_a_result_is_returned_as_json_gives_it():
    assert run(divmod, 7, 2) == [3, 1]


@pytest.mark.parametrize(
    "sent",
    [
        None,
        [True, None, [], []][:3],
        [1, None, [], []],
        [True, None, {}, []],
        [True, None, [["text", "UserWarning", None]], []],
        [True, None, [["text", "UserWarning", None, True]], []],
        [True, None, [["text", "UserWarning", None, -1]], []],
        [True, None, [["text", "UserWarning", None, 1 << 31]], []],
        [True, None, [[b"text".hex(), 1, None, 1]], []],
        [True, None, [], [["os", 30, "text"]]],
        [True, None, [], [["pydicomx", 30, "text"]]],
        [True, None, [], [["pydicom", "30", "text"]]],
        [True, None, [], [["pydicom", 30, None]]],
    ],
)
def test_what_the_child_sends_back_must_have_the_form_it_gives(sent):
    with pytest.raises(ValueError):
        isolated_decoding._returned(sent)  # pylint: disable = protected-access


def test_a_child_that_sends_back_anything_else_is_replaced(monkeypatch):
    run(operator.add, 1, 2)
    ended = isolated_decoding._child.process.pid  # pylint: disable = protected-access

    def malformed(sent):
        raise ValueError()

    monkeypatch.setattr(isolated_decoding, "_returned", malformed)
    with pytest.raises(DecoderEnded):
        run(operator.add, 1, 2)
    monkeypatch.undo()

    assert run(operator.add, 1, 2) == 3
    assert isolated_decoding._child.process.pid != ended  # pylint: disable = protected-access


def test_a_pickle_is_not_read_as_what_the_child_sends_back():
    # A pickle of protocol 4 that would load None.
    with pytest.raises(ValueError):
        json.loads(b"\x80\x04N.")


def test_a_warning_category_is_a_builtin_named_by_the_child_or_a_user_warning():
    sent = ["text", "DeprecationWarning", None, 1]
    imported = set(sys.modules)

    (builtin,) = _reissued(sent)
    (named,) = _reissued(["text", "pymedphys._imports.tkinter", None, 1])
    (other,) = _reissued(["text", "__subclasses__", None, 1])

    assert builtin.category is DeprecationWarning
    assert named.category is UserWarning
    assert other.category is UserWarning
    assert set(sys.modules) == imported


def test_a_warning_is_from_the_callers_module_of_that_name_or_from_elsewhere():
    (imported,) = _reissued(["text", "UserWarning", "json", 1])
    (elsewhere,) = _reissued(["text", "UserWarning", "no_such_module", 1])
    (unnamed,) = _reissued(["text", "UserWarning", None, 1])

    assert imported.filename == json.__file__
    assert elsewhere.filename == unnamed.filename == "<decoding process>"


def test_a_lazy_module_named_by_the_child_is_not_read(monkeypatch):
    monkeypatch.setitem(sys.modules, "lazy_module", _Lazy("lazy_module"))

    (lazy,) = _reissued(["text", "UserWarning", "lazy_module", 1])

    assert lazy.filename == "<decoding process>"


def test_the_child_names_the_module_that_warned_without_importing_others():
    before = run(modules)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        run(warnings.warn, SENTINEL)

    (warned,) = caught
    assert warned.filename == isolated_decoding.__file__
    assert run(modules) == before


def test_a_log_record_of_a_logger_that_the_caller_lacks_is_pydicoms(caplog):
    name = "pydicom.no_such_logger"
    assert name not in logging.Logger.manager.loggerDict
    returned = isolated_decoding._returned(  # pylint: disable = protected-access
        [True, None, [], [[name, logging.WARNING, SENTINEL]]]
    )

    with caplog.at_level(logging.WARNING, logger="pydicom"):
        isolated_decoding._reissue(returned)  # pylint: disable = protected-access

    assert [record.name for record in caplog.records] == ["pydicom"]
    assert name not in logging.Logger.manager.loggerDict


def test_a_warning_from_each_module_is_shown_once_for_that_module():
    caught = _reissued(
        ["text", "UserWarning", "json", 1],
        ["text", "UserWarning", "json", 1],
        ["text", "UserWarning", "os", 1],
    )

    assert [each.filename for each in caught] == [json.__file__, os.__file__]


def test_what_the_child_writes_to_standard_output_is_not_read_as_a_result():
    assert run(os.write, 1, b"\x00" * 64) == 64
    assert run(operator.add, 1, 2) == 3


def test_the_process_and_its_child_end_at_once_while_a_thread_waits_on_a_call(
    tmp_path,
):
    script = tmp_path / "exits.py"
    script.write_text(
        "import operator, threading, time\n"
        "from pymedphys._dicom.deidentify import isolated_decoding\n"
        "def call():\n"
        "    try:\n"
        "        isolated_decoding.run(time.sleep, 120)\n"
        # Unhandled, the error's traceback can be printed as the interpreter
        # shuts down, which can then abort waiting for standard error.
        "    except isolated_decoding.DecoderEnded:\n"
        "        pass\n"
        "isolated_decoding.run(operator.add, 1, 2)\n"
        "threading.Thread(target=call, daemon=True).start()\n"
        "time.sleep(1)\n"
    )

    started = time.monotonic()
    # The child shares the script's standard error, so the run waits for both.
    completed = subprocess.run(
        [sys.executable, os.fspath(script)],
        capture_output=True,
        check=False,
        env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)},
        timeout=300,
    )

    assert completed.returncode == 0
    assert time.monotonic() - started < 60


def test_the_child_does_not_run_the_main_module_again(tmp_path):
    script = tmp_path / "unguarded.py"
    script.write_text(
        "import operator\n"
        "from pymedphys._dicom.deidentify import isolated_decoding\n"
        "print(isolated_decoding.run(operator.add, 1, 2))\n"
    )

    completed = subprocess.run(
        [sys.executable, "-W", "always::ResourceWarning", os.fspath(script)],
        capture_output=True,
        check=False,
        env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)},
        text=True,
        timeout=300,
    )

    assert completed.returncode == 0
    assert completed.stdout.split() == ["3"]
    # The child is ended as the script exits.
    assert "ResourceWarning" not in completed.stderr


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


def test_the_child_reads_with_the_callers_validation_mode(monkeypatch):
    settings = pydicom.config.settings
    monkeypatch.setattr(settings, "reading_validation_mode", pydicom.config.RAISE)

    assert run(reading_mode) == pydicom.config.RAISE


def test_the_childs_pydicom_logger_has_the_callers_level():
    logger = logging.getLogger("pydicom")
    was = logger.level
    logger.setLevel(logging.DEBUG)
    try:
        assert run(logger_level) == logging.DEBUG
    finally:
        logger.setLevel(was)


def test_a_child_that_ended_between_calls_is_replaced_before_the_next():
    run(operator.add, 1, 2)
    isolated_decoding._child.process.kill()  # pylint: disable = protected-access
    isolated_decoding._child.process.wait()  # pylint: disable = protected-access

    assert run(operator.add, 1, 2) == 3


@pytest.mark.skipif(sys.platform == "win32", reason="no core file size limit")
def test_the_child_writes_no_core_file():
    import resource  # pylint: disable = import-outside-toplevel, import-error

    assert run(resource.getrlimit, resource.RLIMIT_CORE) == [0, 0]


def test_a_child_that_cannot_start_leaves_the_decoder_unavailable(
    monkeypatch, tmp_path
):
    isolated_decoding._discard()  # pylint: disable = protected-access
    monkeypatch.setattr(sys, "executable", os.fspath(tmp_path / "no-python"))

    with pytest.raises(DecoderUnavailable):
        run(operator.add, 1, 2)


def test_a_child_that_cannot_start_is_logged_once_without_its_message(
    monkeypatch, tmp_path, caplog
):
    isolated_decoding._discard()  # pylint: disable = protected-access
    monkeypatch.setattr(isolated_decoding, "_unavailable_logged", False)
    missing = os.fspath(tmp_path / "no-python")
    monkeypatch.setattr(sys, "executable", missing)

    with caplog.at_level(logging.WARNING, logger=isolated_decoding.__name__):
        for _ in range(2):
            with pytest.raises(DecoderUnavailable):
                run(operator.add, 1, 2)

    (record,) = caplog.records
    assert "FileNotFoundError" in record.getMessage()
    assert missing not in record.getMessage()


def test_no_child_is_started_once_the_process_is_exiting(monkeypatch):
    isolated_decoding._discard()  # pylint: disable = protected-access
    monkeypatch.setattr(isolated_decoding, "_exiting", True)

    with pytest.raises(DecoderUnavailable):
        run(operator.add, 1, 2)

    assert isolated_decoding._child is None  # pylint: disable = protected-access


def test_a_child_started_as_the_process_begins_to_exit_is_ended(monkeypatch):
    isolated_decoding._discard()  # pylint: disable = protected-access
    started = []

    class _ExitingAsStarted(isolated_decoding._Child):  # pylint: disable = protected-access
        """A child whose start the exit hook overtakes, having found no child
        to end."""

        def __init__(self) -> None:
            super().__init__()
            started.append(self.process)
            monkeypatch.setattr(isolated_decoding, "_exiting", True)

    monkeypatch.setattr(isolated_decoding, "_Child", _ExitingAsStarted)

    with pytest.raises(DecoderUnavailable):
        run(operator.add, 1, 2)

    assert isolated_decoding._child is None  # pylint: disable = protected-access
    (process,) = started
    assert process.returncode is not None


def test_the_exit_hook_ends_the_child_and_starts_no_other(tmp_path):
    script = tmp_path / "exits.py"
    script.write_text(
        "import atexit, operator, sys\n"
        "def check():\n"
        "    isolated_decoding = sys.modules[\n"
        "        'pymedphys._dicom.deidentify.isolated_decoding'\n"
        "    ]\n"
        "    print(process.returncode is not None)\n"
        "    try:\n"
        "        isolated_decoding.run(operator.add, 1, 2)\n"
        "    except isolated_decoding.DecoderUnavailable:\n"
        "        print('unavailable')\n"
        # Registered before the module's own hook, so run after it.
        "atexit.register(check)\n"
        "from pymedphys._dicom.deidentify import isolated_decoding\n"
        "print(isolated_decoding.run(operator.add, 1, 2))\n"
        "process = isolated_decoding._child.process\n"
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
    assert completed.stdout.split() == ["3", "True", "unavailable"]


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
def test_a_forked_process_starts_its_own_child(tmp_path):
    """Check real fork handling without inheriting the pytest worker's state."""
    script = tmp_path / "forks.py"
    # Test collection imports scientific libraries and runner plugins. Fork
    # from a fresh interpreter so that their state is not inherited, while
    # retaining the ownership checks on both sides of a real fork.
    script.write_text(
        "import operator, os, signal, time, traceback\n"
        "from pymedphys._dicom.deidentify import isolated_decoding as decoder\n"
        "assert decoder.run(operator.add, 1, 2) == 3\n"
        "parent_decoder = decoder._child\n"
        "decoder._unavailable_logged = True\n"
        "pid = os.fork()\n"
        "if pid == 0:\n"
        "    code = 1\n"
        "    try:\n"
        "        assert decoder._child is None\n"
        "        assert not decoder._unavailable_logged\n"
        "        assert decoder.run(operator.add, 2, 2) == 4\n"
        "        assert decoder._child.process.pid != parent_decoder.process.pid\n"
        "        code = 0\n"
        "    except BaseException:\n"
        "        traceback.print_exc()\n"
        "    finally:\n"
        "        try:\n"
        "            decoder._exit()\n"
        "        finally:\n"
        "            os._exit(code)\n"
        "try:\n"
        "    deadline = time.monotonic() + 60\n"
        "    while True:\n"
        "        finished, status = os.waitpid(pid, os.WNOHANG)\n"
        "        if finished:\n"
        "            break\n"
        "        if time.monotonic() >= deadline:\n"
        "            os.kill(pid, signal.SIGKILL)\n"
        "            os.waitpid(pid, 0)\n"
        "            raise AssertionError('forked process did not finish')\n"
        "        time.sleep(0.01)\n"
        "    assert os.waitstatus_to_exitcode(status) == 0, status\n"
        "    assert decoder._child is parent_decoder\n"
        "    assert parent_decoder.process.poll() is None\n"
        "    assert decoder.run(operator.add, 1, 2) == 3\n"
        "finally:\n"
        "    decoder._exit()\n"
    )

    completed = subprocess.run(
        [sys.executable, os.fspath(script)],
        capture_output=True,
        check=False,
        env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)},
        text=True,
        timeout=120,
    )

    assert completed.returncode == 0, (completed.stdout, completed.stderr)
