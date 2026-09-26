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

REDACTED = "<value not shown>"

# pydicom quotes values inconsistently: with repr() in some messages and in
# bare single or double quotes in others, so a value can contain the quote
# character that surrounds it. Everything from the first quote to the last is
# therefore replaced, together with a bytes prefix.
_QUOTED = re.compile(r"""(?:\bb)?['"].*['"]""", re.DOTALL)


def redact_quoted(text: str) -> str:
    """Replace everything from the first quote character to the last."""
    return _QUOTED.sub(REDACTED, text)


class _RedactQuotedText(logging.Filter):
    """Redact quoted text, and drop any traceback, from each log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_quoted(record.getMessage())
        record.args = ()
        record.exc_info = None
        record.exc_text = None
        record.stack_info = None
        return True


class _PydicomLogRedaction:
    """Redact the ``pydicom`` logger's records while any caller needs it.

    Streamlit runs each session in its own thread, so the filter is counted
    rather than removed by whichever caller finishes first.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._users = 0
        self._filter = _RedactQuotedText()

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
    """Keep DICOM values out of pydicom's warnings and log records.

    pydicom reports each invalid value it reads or converts twice, in a log
    record on the ``pydicom`` logger and in a ``UserWarning`` from
    ``pydicom.valuerep``, and both quote the value. Within this context, the
    log record keeps its message with the quoted text replaced by
    ``<value not shown>``.

    The warning is ignored for the rest of the process, since the log record
    carries the same report. Python's warning filters are process-wide, and
    ``warnings.catch_warnings`` is not thread-safe, so the filter cannot be
    removed again safely.
    """
    warnings.filterwarnings("ignore", category=UserWarning, module=r"pydicom\.valuerep")
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
