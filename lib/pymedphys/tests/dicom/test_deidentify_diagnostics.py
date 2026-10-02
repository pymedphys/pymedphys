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

"""Tests for the engine's redaction of pydicom's warnings and log records."""

import io
import logging
import threading
import time
import warnings

import pytest

from pymedphys._imports import pydicom

from pymedphys._dicom.deidentify import diagnostics
from pymedphys._dicom.deidentify.diagnostics import (
    SUMMARY,
    WARNING_SUMMARY,
    redacted_diagnostics,
)

# Synthetic text that no redacted diagnostic may contain.
SENTINEL = "ZZSENTINELZZ"
LOGGERS = ["pydicom", "pydicom.pixels.decoders.base", "pydicom.anything.new"]


def _warn_from_pydicom(message: str) -> None:
    """Warn as pydicom does, logging the message and issuing it."""
    pydicom.misc.warn_and_log(message)


@pytest.mark.parametrize("name", LOGGERS)
@pytest.mark.parametrize("level", [logging.DEBUG, logging.WARNING, logging.ERROR])
def test_pydicom_log_records_are_summarised(caplog, name, level):
    caplog.set_level(logging.DEBUG, logger="pydicom")
    with redacted_diagnostics():
        logging.getLogger(name).log(level, "read %s from /data/%s", SENTINEL, SENTINEL)
    assert [record.getMessage() for record in caplog.records] == [SUMMARY]
    assert SENTINEL not in caplog.text


def test_a_record_loses_its_traceback_and_stack(caplog):
    caplog.set_level(logging.DEBUG, logger="pydicom")
    with redacted_diagnostics():
        try:
            raise ValueError(SENTINEL)
        except ValueError:
            logging.getLogger("pydicom").exception("failed", stack_info=True)
    (record,) = caplog.records
    assert record.exc_info is None and record.stack_info is None
    assert SENTINEL not in caplog.text


def test_a_record_whose_arguments_do_not_fit_is_summarised(caplog):
    caplog.set_level(logging.DEBUG, logger="pydicom")
    with redacted_diagnostics():
        logging.getLogger("pydicom").warning(  # pylint: disable = logging-too-few-args
            "%s %s", SENTINEL
        )
    assert [record.getMessage() for record in caplog.records] == [SUMMARY]


def test_an_invalid_value_keeps_only_its_vr(caplog):
    caplog.set_level(logging.DEBUG, logger="pydicom")
    with redacted_diagnostics():
        # pydicom formats its messages before logging them.
        logging.getLogger("pydicom").warning(  # pylint: disable = logging-fstring-interpolation
            f"Invalid value for VR PN: '{SENTINEL}'"
        )
    assert [record.getMessage() for record in caplog.records] == [
        "Invalid value for VR PN: <value not shown>."
    ]


def test_other_loggers_are_left_alone(caplog):
    caplog.set_level(logging.DEBUG)
    with redacted_diagnostics():
        logging.getLogger("pydicomish").warning(SENTINEL)
        logging.getLogger("pymedphys").warning(SENTINEL)
    assert [record.getMessage() for record in caplog.records] == [SENTINEL] * 2


def test_debug_logging_of_a_read_quotes_no_value(caplog):
    dataset = pydicom.Dataset()
    dataset.PatientName = SENTINEL
    dataset.PatientID = SENTINEL
    buffer = io.BytesIO()
    pydicom.dcmwrite(buffer, dataset, implicit_vr=True, little_endian=True)
    # caplog restores the logger's level after the test, so it is set first.
    caplog.set_level(logging.DEBUG, logger="pydicom")
    pydicom.config.debug(True, default_handler=False)
    try:
        with redacted_diagnostics():
            read = pydicom.dcmread(io.BytesIO(buffer.getvalue()), force=True)
            assert read.PatientName == SENTINEL
    finally:
        pydicom.config.debug(False, default_handler=False)
    assert caplog.records
    assert SENTINEL not in caplog.text


def test_a_pydicom_warning_is_summarised():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with redacted_diagnostics():
            _warn_from_pydicom(f"bad value {SENTINEL} in /data/{SENTINEL}")
    assert [str(each.message) for each in caught] == [WARNING_SUMMARY]
    assert caught[0].category is UserWarning
    assert (caught[0].filename, caught[0].lineno) == ("<pydicom>", 0)


def test_a_warning_attributed_to_a_source_file_hides_its_path():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with redacted_diagnostics():
            warnings.warn_explicit(SENTINEL, UserWarning, f"/data/{SENTINEL}.dcm", 1)
    assert [(str(each.message), each.filename) for each in caught] == [
        (WARNING_SUMMARY, "<pydicom>")
    ]


def test_any_warning_within_the_context_is_summarised():
    # pydicom can attribute a warning to its caller's frame, so warnings
    # are not told apart by the module that issued them.
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with redacted_diagnostics():
            warnings.warn(SENTINEL, RuntimeWarning, stacklevel=1)
    assert [(str(each.message), each.category) for each in caught] == [
        (WARNING_SUMMARY, RuntimeWarning)
    ]


def test_a_warning_shown_on_a_stream_quotes_no_value():
    stream = io.StringIO()
    with warnings.catch_warnings():
        warnings.simplefilter("always")

        def show(  # pylint: disable = unused-argument
            message, category, filename, lineno, file=None, line=None
        ):
            stream.write(
                warnings.formatwarning(message, category, filename, lineno, line)
            )

        warnings.showwarning = show
        with redacted_diagnostics():
            _warn_from_pydicom(SENTINEL)
    assert WARNING_SUMMARY in stream.getvalue()
    assert SENTINEL not in stream.getvalue()


def test_the_callers_warning_filters_still_apply():
    before = list(warnings.filters)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("ignore")
        with redacted_diagnostics():
            _warn_from_pydicom(SENTINEL)
    assert not caught
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        with pytest.raises(UserWarning), redacted_diagnostics():
            _warn_from_pydicom(SENTINEL)
    assert warnings.filters == before


def test_no_warning_filter_is_added():
    with warnings.catch_warnings():
        before = list(warnings.filters)
        with redacted_diagnostics():
            assert warnings.filters == before
        assert warnings.filters == before


def test_outside_the_context_diagnostics_are_unchanged(caplog):
    caplog.set_level(logging.DEBUG, logger="pydicom")
    with redacted_diagnostics():
        pass
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _warn_from_pydicom(SENTINEL)
    assert [str(each.message) for each in caught] == [SENTINEL]
    assert [record.getMessage() for record in caplog.records] == [SENTINEL]


def test_contexts_nest():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with redacted_diagnostics():
            with redacted_diagnostics():
                warnings.warn(SENTINEL, stacklevel=1)
            warnings.warn(SENTINEL, stacklevel=1)
        warnings.warn(SENTINEL, stacklevel=1)
    assert [str(each.message) for each in caught] == [
        WARNING_SUMMARY,
        WARNING_SUMMARY,
        SENTINEL,
    ]


def test_only_the_thread_within_the_context_is_redacted(caplog):
    caplog.set_level(logging.DEBUG, logger="pydicom")
    entered, logged = threading.Event(), threading.Event()

    def inside():
        with redacted_diagnostics():
            entered.set()
            logged.wait(5)
            logging.getLogger("pydicom").warning("inside %s", SENTINEL)

    def outside():
        entered.wait(5)
        logging.getLogger("pydicom").warning("outside %s", SENTINEL)
        logged.set()

    threads = [threading.Thread(target=inside), threading.Thread(target=outside)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
    assert sorted(record.getMessage() for record in caplog.records) == sorted(
        [SUMMARY, f"outside {SENTINEL}"]
    )


def test_a_record_rebuilt_from_a_dictionary_does_not_fail():
    with redacted_diagnostics():
        record = logging.makeLogRecord({"name": "pydicom", "msg": "rebuilt"})
    assert record.getMessage() == "rebuilt"


def test_a_warning_recorded_by_a_block_entered_within_the_context_is_summarised():
    with redacted_diagnostics():
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _warn_from_pydicom(SENTINEL)
    assert [str(each.message) for each in caught] == [WARNING_SUMMARY]


def _in_threads(redacting, other):
    """Run ``redacting`` within the context while ``other`` runs in a second thread."""
    errors = []

    def run(target):
        try:
            target()
        except Exception as error:  # pylint: disable = broad-exception-caught
            errors.append(error)

    threads = [
        threading.Thread(target=run, args=(each,)) for each in (redacting, other)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
    assert not errors


def test_another_threads_recording_block_does_not_lift_the_redaction(capsys):
    # catch_warnings replaces warnings.showwarning for the whole process,
    # whichever thread enters it. With context-aware warnings, the warning
    # is shown, not recorded by the other thread's block.
    entered, recording, warned = (threading.Event() for _ in range(3))
    caught = []

    def redacting():
        with redacted_diagnostics():
            entered.set()
            recording.wait(5)
            _warn_from_pydicom(SENTINEL)
            warned.set()

    def other():
        entered.wait(5)
        with warnings.catch_warnings(record=True) as log:
            warnings.simplefilter("always")
            recording.set()
            warned.wait(5)
        caught.extend(log)

    _in_threads(redacting, other)
    shown = capsys.readouterr().err
    assert [str(each.message) for each in caught] in ([WARNING_SUMMARY], [])
    assert WARNING_SUMMARY in shown or caught
    assert SENTINEL not in shown


def test_another_thread_restoring_the_hooks_does_not_lift_the_redaction():
    # A block entered before the context was first entered restores, on
    # exit, the hooks it saved, which do not redact.
    stream = io.StringIO()
    entered, exited, warned = (threading.Event() for _ in range(3))

    def show(  # pylint: disable = unused-argument
        message, category, filename, lineno, file=None, line=None
    ):
        stream.write(warnings.formatwarning(message, category, filename, lineno, line))

    def redacting():
        entered.wait(5)
        with redacted_diagnostics():
            exited.wait(5)
            _warn_from_pydicom(SENTINEL)
            warned.set()

    def other():
        with warnings.catch_warnings():
            warnings.simplefilter("always")
            warnings.showwarning = show
            entered.set()
            time.sleep(0.2)
        warnings.simplefilter("always")
        warnings.showwarning = show
        exited.set()
        warned.wait(5)

    with warnings.catch_warnings():
        _in_threads(redacting, other)
    assert WARNING_SUMMARY in stream.getvalue()
    assert SENTINEL not in stream.getvalue()


def test_hooks_replaced_later_are_wrapped_again(caplog):
    caplog.set_level(logging.DEBUG, logger="pydicom")
    with redacted_diagnostics():
        pass
    factory = logging.getLogRecordFactory()

    def replacement(*args, **kwargs):
        return logging.LogRecord(*args, **kwargs)

    logging.setLogRecordFactory(replacement)
    original = warnings._showwarnmsg  # pylint: disable = protected-access

    def show(message):
        original(message)

    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            warnings._showwarnmsg = show  # pylint: disable = protected-access
            with redacted_diagnostics():
                _warn_from_pydicom(SENTINEL)
        assert [str(each.message) for each in caught] == [WARNING_SUMMARY]
        assert [record.getMessage() for record in caplog.records] == [SUMMARY]
    finally:
        logging.setLogRecordFactory(factory)
        warnings._showwarnmsg = original  # pylint: disable = protected-access


def test_exceptions_pass_through_unchanged():
    with pytest.raises(ValueError, match=SENTINEL), redacted_diagnostics():
        raise ValueError(SENTINEL)
    assert not diagnostics._redacting()  # pylint: disable = protected-access


def test_the_context_counts_what_it_redacted(caplog):
    caplog.set_level(logging.DEBUG, logger="pydicom")
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        with redacted_diagnostics() as counts:
            _warn_from_pydicom(SENTINEL)
            logging.getLogger("pydicom.pixels.utils").debug(SENTINEL)
            logging.getLogger("pymedphys").warning(SENTINEL)
    assert (counts.warnings, counts.log_records) == (1, 2)
    assert SENTINEL not in repr(counts)


def test_nested_contexts_each_count_what_they_saw():
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        with redacted_diagnostics() as outer:
            warnings.warn(SENTINEL, stacklevel=1)
            with redacted_diagnostics() as inner:
                warnings.warn(SENTINEL, stacklevel=1)
    assert (outer.warnings, inner.warnings) == (2, 1)


def test_a_warning_that_filters_ignore_is_not_counted():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with redacted_diagnostics() as counts:
            _warn_from_pydicom(SENTINEL)
    assert counts.warnings == 0
