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
threads run, so warnings are still shown, recorded, or raised as the
caller's filters say, and every other thread, and this one outside the
context, sees the original messages. It works through two hooks, each
wrapped once with a function that redacts only within the context and
otherwise passes everything on unchanged: the log record factory
(:func:`logging.setLogRecordFactory`), and the function to which CPython's
:mod:`warnings` passes each warning to be shown or recorded,
``warnings._showwarnmsg``. That hook, unlike :func:`warnings.showwarning`,
is not replaced by :class:`warnings.catch_warnings`, which replaces
``showwarning`` for the whole process whichever thread enters it, so a
warning recorded by such a block, in any thread, is recorded redacted. A
hook that other code replaces is wrapped in turn when the context is next
entered.

What it does not cover: a warning that the caller's filters turn into an
exception, which the engine replaces without chaining wherever it calls
pydicom; a record rebuilt by :func:`logging.makeLogRecord`, which names it
only after creating it; and, while the context is active, a log record
factory or ``warnings._showwarnmsg`` that another thread installs, until
the context is next entered.
"""

from __future__ import annotations

import contextlib
import dataclasses
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


@dataclasses.dataclass
class RedactionCounts:
    """How many diagnostics a :func:`redacted_diagnostics` context redacted.

    It holds counts only, never a message, so it can be reported.

    Attributes
    ----------
    warnings : int
        Warnings shown or recorded within the context; a warning that the
        caller's filters ignore, or turn into an exception, is not counted.
    log_records : int
        Records of the ``pydicom`` logger and the loggers below it created
        within the context, which are those at or above the logger's
        effective level.
    """

    warnings: int = 0
    log_records: int = 0


class _Scope(threading.local):
    """The :func:`redacted_diagnostics` contexts the current thread is within."""

    def __init__(self) -> None:
        super().__init__()
        self.active: list[RedactionCounts] = []


_SCOPE = _Scope()
_LOCK = threading.Lock()


def _redacting() -> bool:
    return bool(_SCOPE.active)


def _wrapped_factory(
    factory: Callable[..., logging.LogRecord],
) -> Callable[..., logging.LogRecord]:
    """Wrap a log record factory to summarise pydicom's records within the context."""

    def make_record(*args, **kwargs) -> logging.LogRecord:
        record = factory(*args, **kwargs)
        # logging.makeLogRecord creates a record without a name, and sets
        # its name and message afterwards.
        name = record.name if isinstance(record.name, str) else ""
        if _redacting() and (name == _LOGGER or name.startswith(f"{_LOGGER}.")):
            try:
                message = record.getMessage()
            # A record whose arguments do not fit its message cannot be
            # formatted, and the error would quote them.
            except Exception:  # pylint: disable = broad-exception-caught
                message = ""
            record.msg = safe_summary(message)
            for counts in _SCOPE.active:
                counts.log_records += 1
            record.args = ()
            record.exc_info = None
            record.exc_text = None
            record.stack_info = None
        return record

    make_record.redacts = True  # type: ignore[attr-defined]
    return make_record


def _wrapped_showwarnmsg(
    show: Callable[[warnings.WarningMessage], None],
) -> Callable[[warnings.WarningMessage], None]:
    """Wrap ``warnings._showwarnmsg`` to summarise warnings within the context."""

    def showwarnmsg(message: warnings.WarningMessage) -> None:
        if _redacting():
            # The location can be the source file's path when pydicom warns
            # from code that a caller passed in, so it is not shown either.
            message = warnings.WarningMessage(
                safe_summary(str(message.message), WARNING_SUMMARY),
                message.category,
                "<pydicom>",
                0,
                message.file,
                "",
            )
            for counts in _SCOPE.active:
                counts.warnings += 1
        show(message)

    showwarnmsg.redacts = True  # type: ignore[attr-defined]
    return showwarnmsg


def _install() -> None:
    """Make each hook redact, wrapping any that other code has replaced."""
    factory = logging.getLogRecordFactory()
    if not getattr(factory, "redacts", False):
        logging.setLogRecordFactory(_wrapped_factory(factory))
    # CPython passes every warning that its filters do not ignore or raise
    # to the warnings module's _showwarnmsg, looked up for each warning,
    # which then calls showwarning or, within catch_warnings(record=True),
    # records it. Unlike showwarning, which catch_warnings replaces and
    # restores for the whole process whichever thread enters it, nothing in
    # the standard library replaces _showwarnmsg.
    show = warnings._showwarnmsg  # type: ignore[attr-defined]  # pylint: disable = protected-access
    if not getattr(show, "redacts", False):
        warnings._showwarnmsg = _wrapped_showwarnmsg(show)  # type: ignore[attr-defined]  # pylint: disable = protected-access


@contextlib.contextmanager
def redacted_diagnostics() -> Iterator[RedactionCounts]:
    """Keep file paths and DICOM values out of pydicom's warnings and log records.

    Within the context, in the thread that entered it, each record of the
    ``pydicom`` logger or a logger below it, at any level, has its message
    replaced by :func:`safe_summary`, without arguments, traceback, or
    stack; and each warning, whichever module issued it, is shown with its
    message replaced and its location hidden. Contexts can be nested and
    entered by several threads at once. Exceptions pass through unchanged.

    The context yields the :class:`RedactionCounts` of what it redacted,
    which are complete once it exits.

    >>> import logging
    >>> with redacted_diagnostics() as counts:
    ...     record = logging.getLogger("pydicom").makeRecord(
    ...         "pydicom", logging.DEBUG, "", 0, "read %s", ("Doe^Jane",), None
    ...     )
    >>> record.getMessage() == SUMMARY
    True
    >>> counts
    RedactionCounts(warnings=0, log_records=1)
    """
    with _LOCK:
        _install()
    counts = RedactionCounts()
    _SCOPE.active.append(counts)
    try:
        yield counts
    finally:
        # By identity: counts that are equal belong to different contexts.
        _SCOPE.active[:] = [each for each in _SCOPE.active if each is not counts]
