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

"""Keep source values and paths out of the diagnostics of the engine's reads.

pydicom reports a problem both as a Python warning and as a record of the
``pydicom`` logger, and its loggers below ``pydicom``, such as
``pydicom.pixels.decoders.base``, log records of their own. Any of them can
quote a value or name a file, and with ``pydicom.config.debug(True)`` the
debug records quote every element read. Within :func:`redacted_diagnostics`,
in the thread that entered it, each such warning and record says only that
there was a problem, and never what was read.

The redaction is scoped, not a filter: it adds nothing to Python's warning
filters, which are process-wide and cannot be removed safely while other
threads run, so warnings are still shown, counted, or raised as the
caller's filters say, and every other thread, and this one outside the
context, sees the original messages. It works through the two documented
hooks, :func:`warnings.showwarning` and the log record factory
(:func:`logging.setLogRecordFactory`), each wrapped once with a function
that redacts only within the context and otherwise passes everything on
unchanged. A hook that other code installs later is wrapped in turn when
the context is next entered.

What it does not cover: a warning that the caller's filters turn into an
exception, which the engine replaces without chaining wherever it calls
pydicom; and a warning recorded by a :class:`warnings.catch_warnings` block
entered after the context, which holds the original message for the code
that recorded it.
"""

from __future__ import annotations

import contextlib
import functools
import logging
import re
import threading
import warnings
from collections.abc import Callable, Iterator

from pymedphys._imports import pydicom

REDACTED = "<value not shown>"
SUMMARY = (
    "pydicom reported a problem. Details are not shown because they can "
    "contain file paths or DICOM values."
)
WARNING_SUMMARY = (
    "A warning was issued while reading DICOM data. Details are not shown "
    "because they can contain file paths or DICOM values."
)

# pydicom's messages can quote values, and can include file paths without
# quotes, so only messages recognised here keep any detail, and only fields
# checked against a closed set.
_INVALID_VALUE = re.compile(r"Invalid value for VR (?P<vr>[A-Z]{2})\b")
_LOGGER = "pydicom"


@functools.cache
def _value_representations() -> frozenset[str]:
    return frozenset(vr.value for vr in pydicom.valuerep.VR)


def safe_summary(message: str, default: str = SUMMARY) -> str:
    """Return a diagnostic with nothing that could identify anyone.

    A report of an invalid value keeps the VR, when it is one that PS3.5
    defines. Any other message is replaced by `default`.

    >>> safe_summary("Invalid value for VR PN: 'Doe^Jane'")
    'Invalid value for VR PN: <value not shown>.'
    >>> safe_summary("Invalid value for VR XX: 'Doe^Jane'") == SUMMARY
    True
    """
    match = _INVALID_VALUE.match(message)
    if match and match["vr"] in _value_representations():
        return f"Invalid value for VR {match['vr']}: {REDACTED}."
    return default


class _Scope(threading.local):
    """How deeply the current thread is within :func:`redacted_diagnostics`."""

    depth = 0


_SCOPE = _Scope()
_LOCK = threading.Lock()


def _redacting() -> bool:
    return _SCOPE.depth > 0


def _wrapped_factory(
    factory: Callable[..., logging.LogRecord],
) -> Callable[..., logging.LogRecord]:
    """Wrap a log record factory to summarise pydicom's records within the context."""

    def make_record(*args, **kwargs) -> logging.LogRecord:
        record = factory(*args, **kwargs)
        if _redacting() and (
            record.name == _LOGGER or record.name.startswith(f"{_LOGGER}.")
        ):
            try:
                message = record.getMessage()
            # A record whose arguments do not fit its message cannot be
            # formatted, and the error would quote them.
            except Exception:  # pylint: disable = broad-exception-caught
                message = ""
            record.msg = safe_summary(message)
            record.args = ()
            record.exc_info = None
            record.exc_text = None
            record.stack_info = None
        return record

    make_record.redacts = True  # type: ignore[attr-defined]
    return make_record


def _wrapped_showwarning(show: Callable[..., None]) -> Callable[..., None]:
    """Wrap :func:`warnings.showwarning` to summarise warnings within the context."""

    def showwarning(message, category, filename, lineno, file=None, line=None):
        if _redacting():
            # The location can be the source file's path when pydicom warns
            # from code that a caller passed in, so it is not shown either.
            message = safe_summary(str(message), WARNING_SUMMARY)
            filename, lineno, line = "<pydicom>", 0, ""
        show(message, category, filename, lineno, file, line)

    showwarning.redacts = True  # type: ignore[attr-defined]
    return showwarning


def _install() -> None:
    """Make each hook redact, wrapping any that other code has replaced."""
    factory = logging.getLogRecordFactory()
    if not getattr(factory, "redacts", False):
        logging.setLogRecordFactory(_wrapped_factory(factory))
    if not getattr(warnings.showwarning, "redacts", False):
        warnings.showwarning = _wrapped_showwarning(warnings.showwarning)


@contextlib.contextmanager
def redacted_diagnostics() -> Iterator[None]:
    """Keep file paths and DICOM values out of pydicom's warnings and log records.

    Within the context, in the thread that entered it, each record of the
    ``pydicom`` logger or a logger below it, at any level, has its message
    replaced by :func:`safe_summary`, without arguments, traceback, or
    stack; and each warning, whichever module issued it, is shown with its
    message replaced and its location hidden. Contexts can be nested and
    entered by several threads at once. Exceptions pass through unchanged.

    >>> import logging
    >>> with redacted_diagnostics():
    ...     record = logging.getLogger("pydicom").makeRecord(
    ...         "pydicom", logging.DEBUG, "", 0, "read %s", ("Doe^Jane",), None
    ...     )
    >>> record.getMessage() == SUMMARY
    True
    """
    with _LOCK:
        _install()
    _SCOPE.depth += 1
    try:
        yield
    finally:
        _SCOPE.depth -= 1
