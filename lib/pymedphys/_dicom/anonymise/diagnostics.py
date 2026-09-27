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

"""Keep source values and paths out of the anonymisation entry points' diagnostics.

The ``pymedphys dicom anonymise`` and ``pymedphys experimental dicom
pseudonymise`` commands and the DICOM Pseudonymisation app use these helpers.
The library functions they call are unchanged: their exceptions, and pydicom's
warnings and log records, can still quote file paths and DICOM values.
"""

from __future__ import annotations

import contextlib
import functools
import logging
import re
import sys
import threading
import warnings
from collections.abc import Callable, Iterator
from typing import Any

from pymedphys._imports import pydicom

REDACTED = "<value not shown>"
SUMMARY = (
    "pydicom reported a problem. Details are not shown because they can "
    "contain file paths or DICOM values."
)

# pydicom's messages can quote values, and can include file paths without
# quotes, so only messages recognised here keep any detail, and only fields
# checked against a closed set.
_INVALID_VALUE = re.compile(r"Invalid value for VR (?P<vr>[A-Z]{2})\b")


@functools.cache
def _value_representations() -> frozenset[str]:
    return frozenset(vr.value for vr in pydicom.valuerep.VR)


def safe_summary(message: str) -> str:
    """Return a pydicom diagnostic with nothing that could identify anyone.

    A report of an invalid value keeps the VR, when it is one that PS3.5
    defines. Any other message is replaced by :data:`SUMMARY`.
    """
    match = _INVALID_VALUE.match(message)
    if match and match["vr"] in _value_representations():
        return f"Invalid value for VR {match['vr']}: {REDACTED}."
    return SUMMARY


class _SummariseRecord(logging.Filter):
    """Replace each log record's message with its safe summary, without traceback."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = safe_summary(record.getMessage())
        record.args = ()
        record.exc_info = None
        record.exc_text = None
        record.stack_info = None
        return True


class _PydicomLogRedaction:
    """Summarise the ``pydicom`` logger's records while any caller needs it.

    Streamlit runs each session in its own thread, so the filter is counted
    rather than removed by whichever caller finishes first.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._users = 0
        self._filter = _SummariseRecord()

    @contextlib.contextmanager
    def active(self) -> Iterator[None]:
        logger = logging.getLogger("pydicom")
        with self._lock:
            if self._users == 0:
                logger.addFilter(self._filter)
            self._users += 1
        try:
            yield
        finally:
            with self._lock:
                self._users -= 1
                if self._users == 0:
                    logger.removeFilter(self._filter)


_PYDICOM_LOG_REDACTION = _PydicomLogRedaction()


@contextlib.contextmanager
def redacted_pydicom_diagnostics() -> Iterator[None]:
    """Keep file paths and DICOM values out of pydicom's warnings and log records.

    pydicom sends each of its warnings to the ``pydicom`` logger as well as
    issuing it as a Python warning, and either can quote a value or name a
    file. Within this context, each ``pydicom`` log record's message is
    replaced by :func:`safe_summary`.

    Warnings from pydicom's modules are ignored for the rest of the process,
    since the log record carries the same report. Python's warning filters
    are process-wide, and ``warnings.catch_warnings`` is not thread-safe, so
    the filter cannot be removed again safely. Other code in the same
    process, such as the other GUI apps, therefore no longer sees pydicom's
    warnings. pydicom's log records are summarised only while this context is
    active, so outside it they still carry the original message.
    """
    warnings.filterwarnings("ignore", module=r"pydicom(\.|$)")
    with _PYDICOM_LOG_REDACTION.active():
        yield


def report_errors_by_type(
    command: Callable[[Any], None],
) -> Callable[[Any], None]:
    """Report a command's errors by exception type only, and exit with status 1.

    Exception messages and tracebacks can quote file paths and DICOM values,
    so neither is shown. Directory commands also log the number of the file
    that failed. The command runs within :func:`redacted_pydicom_diagnostics`.
    """

    @functools.wraps(command)
    def run_command(args: Any) -> None:
        with redacted_pydicom_diagnostics():
            try:
                command(args)
            except Exception as error:  # pylint: disable = broad-exception-caught
                print(
                    f"Error: {type(error).__name__}. Details are not shown "
                    "because they can contain file paths or DICOM values.",
                    file=sys.stderr,
                )
                raise SystemExit(1) from None

    return run_command
