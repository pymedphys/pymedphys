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

"""Decode in a child process, so that a decoder that ends its process
withholds an instance rather than ending the run.

GDCM, which decodes JPEG and JPEG-LS, and OpenJPEG, which decodes JPEG 2000
and HTJ2K, are native libraries, and a malformed codestream can make one end
the process that called it, which no ``except`` can prevent. GDCM 3.2's JPEG
codec, for one, throws a C++ exception that nothing catches, so the process
aborts, whenever libjpeg warns while it reads a frame's header, other than
that it must scale the image down: for a JFIF segment of a version it does
not know, for example, or for bytes between two markers.

So :mod:`.pixel_decoding` hands each decode by those plugins to :func:`run`,
which calls it in one child process, started when first needed and kept
for the life of the process, so that each instance costs one exchange of
its bytes over a pipe, not a new interpreter. The child is the same Python,
started in isolated mode (``-I``) with the caller's module search path,
and imports only what a call needs: unlike :mod:`multiprocessing`'s
``spawn`` method, it never imports the caller's main module, which, in a
script without an ``if __name__ == "__main__":`` guard, would run the
script again.

The child returns the call's result, or only that it raised, never what it
raised, since an error's message can quote a value. It also returns the
warnings that the call gave, and the records of pydicom's loggers, and
:func:`run` issues them again in the caller, so that the caller's warning
filters, log handlers, and :func:`.diagnostics.redacted_diagnostics` apply
to them as they would in process: a warning that the caller's filters turn
into an error makes the call raise it. Each warning keeps its message and
line, its category where that is one of Python's built-in warning classes,
and else is a :class:`UserWarning`, and the module that issued it where
the caller has imported a plain module of that name, not a lazy one, whose
attributes would import what it stands for; nothing in the child shows or
handles either. The child takes from the caller whether pydicom imitates
its future behaviour, its validation mode for reading, and the level of
its logger, and reads with pydicom's configuration as it is when pydicom
is imported for the rest.

What the child sends back is read as JSON, never unpickled, and is checked
to have the form that :func:`_serve` gives it, in no more than 16 MiB, so
that a child whose decoder a codestream subverted can give the caller only
that data: through what it sends back, it cannot make the caller run code,
import a module, or change an object, and showing one of its warnings reads
at most a line of a module that the caller has already imported. A result
is therefore JSON's: ``None``, a bool, a number, a string, or a list or
dict of them, with a tuple returned as a list. What the child does other
than send data back is not contained: what a native library writes to the
standard output or error stream goes to the caller's standard error
stream, unredacted, as it would in process, and the child runs with the
caller's permissions. The child's core file size limit is zero, where the
platform has one, so that a decoder that aborts writes no core file
holding the file it was decoding. Where the system passes core files to a
program instead, as a ``core_pattern`` that starts with ``|`` does on
Linux, the kernel leaves that limit to the program: systemd-coredump keeps
no core file under it.

If the child ends during a call, :func:`run` raises :class:`DecoderEnded`,
and the next call starts a new child, as does a call after the child ended
between calls. If it cannot be started, or ends before it is ready for
calls, :func:`run` raises :class:`DecoderUnavailable`, and the first time
in a process that it does, logs a warning saying so, which names only the
type of the error. Before anything is imported in the child, its standard
output is set aside for results, so that nothing written as a module is
imported can be read as one. A process forked from the caller starts its
own child, rather than sharing the caller's pipes to it. As the caller
exits, the child is ended, so that a call that another thread is waiting
on raises :class:`DecoderEnded`, and any later call
:class:`DecoderUnavailable`. A call that does not return, such as a
decoder that loops forever, is otherwise waited for, as it would be in
process: a time limit would make the outcome depend on the machine's
speed. Calls are made one at a time, whichever thread makes them.
"""

from __future__ import annotations

import atexit
import builtins
import dataclasses
import json
import logging
import os

# Pickles are loaded only by the child, from the parent that started it. The
# parent reads what the child sends back as JSON.
import pickle  # nosec B403
import signal
import struct
import subprocess
import sys
import threading
import types
import warnings
from collections.abc import Callable, Sequence
from typing import IO, Any

from pymedphys._imports import pydicom

_LOGGER = "pydicom"
_log = logging.getLogger(__name__)
# The warning categories that the child can name: Python's built-in warning
# classes, found by name in this fixed table rather than looked up, which
# could import a module. pydicom defines none of its own.
_CATEGORIES: dict[str, type[Warning]] = {
    name: value
    for name, value in vars(builtins).items()
    if isinstance(value, type) and issubclass(value, Warning)
}
# The largest line that a warning can be issued from.
_LINES = (1 << 31) - 1
# Where a warning is said to be from when the caller has not imported the
# module that the child names.
_ELSEWHERE = "<decoding process>"
# Far more than any result, with its warnings and log records, needs.
_RESULT_BYTES = 1 << 24
# Where the warnings that the child returns are registered as shown, for each
# module that they are said to be from, as its own registry would register
# them in process.
_REGISTRIES: dict[str, dict] = {}
_LENGTH = struct.Struct("<Q")
# Run by the child. Results go to what was standard output, and anything
# else written to it, as by a module as it is imported or by a native
# library, goes to standard error. The child then reads the module search
# path, framed as _send frames it, and only then imports anything that the
# path could find elsewhere.
_BOOTSTRAP = (
    "import os, pickle, struct, sys\n"
    "results = os.fdopen(os.dup(1), 'wb')\n"
    "os.dup2(2, 1)\n"
    "stream = sys.stdin.buffer\n"
    "(length,) = struct.unpack('<Q', stream.read(8))\n"
    "sys.path[:] = pickle.loads(stream.read(length))\n"
    "from pymedphys._dicom.deidentify import isolated_decoding\n"
    "isolated_decoding._serve(results)\n"
)
# What the child sends once it is ready for calls.
_READY = "ready"


class DecodingFailed(Exception):
    """The call raised an :class:`Exception` in the child; what it raised is
    not passed on."""


class DecoderEnded(DecodingFailed):
    """The child ended during the call, as by an abort or a signal."""


class DecoderUnavailable(DecoderEnded):
    """The child could not be started, or ended before it was ready for
    calls, so that no call can be made."""


class _Child:
    """The child process, which reads calls from its standard input and
    writes their results to what was its standard output."""

    def __init__(self) -> None:
        self.process = subprocess.Popen(  # pylint: disable = consider-using-with
            [sys.executable, "-I", "-c", _BOOTSTRAP],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
        )
        try:
            _send(self.stdin, [path for path in sys.path if isinstance(path, str)])
            if self.result() != _READY:
                raise EOFError()
        except BaseException:
            self.close()
            raise

    @property
    def stdin(self) -> IO[bytes]:
        """Where calls are written."""
        assert self.process.stdin is not None
        return self.process.stdin

    @property
    def stdout(self) -> IO[bytes]:
        """Where results are read."""
        assert self.process.stdout is not None
        return self.process.stdout

    def call(self, task: Callable[..., Any], args: tuple) -> _Returned:
        """Return what ``task(*args)`` gave in the child."""
        _send(self.stdin, (task, args, _configuration()))
        return _returned(self.result())

    def result(self) -> Any:
        """Read what the child sent, as JSON.

        Raises
        ------
        EOFError
            If the child ended first, or sent more than 16 MiB.
        ValueError
            If what it sent is not JSON.
        RecursionError
            If what it sent is JSON nested too deeply to read.
        """
        return json.loads(_received(self.stdout, _RESULT_BYTES))

    def close(self) -> None:
        """End the child, if it has not ended, and close its pipes.

        The child is ended first, since a thread that is reading its result
        holds the lock that closing the pipe waits for, until the read ends.
        """
        if self.process.poll() is None:
            self.process.kill()
        for stream in (self.stdin, self.stdout):
            try:
                stream.close()
            except OSError:
                pass
        self.process.wait()


@dataclasses.dataclass(frozen=True)
class _Warned:
    """A warning that a call gave in the child."""

    text: str
    category: type[Warning]
    module: str | None
    lineno: int


@dataclasses.dataclass(frozen=True)
class _Logged:
    """A record of one of pydicom's loggers that a call gave in the child."""

    name: str
    level: int
    text: str


@dataclasses.dataclass(frozen=True)
class _Returned:
    """What a call gave in the child: whether it returned, what, and the
    warnings and log records it gave."""

    succeeded: bool
    result: Any
    warned: Sequence[_Warned]
    logged: Sequence[_Logged]


_LOCK = threading.Lock()
_child: _Child | None = None
# Whether a failure to start the child has been logged in this process.
_unavailable_logged = False
# Whether the process is exiting, so that no child is to be started.
_exiting = False
# The children of the processes that this one was forked from, which it
# leaves to them.
_inherited: list[_Child] = []


def _after_fork() -> None:
    """Start afresh in a forked process, which shares its parent's pipes to
    the child, and may have been forked while another thread held the lock."""
    global _LOCK, _child, _unavailable_logged  # pylint: disable = global-statement
    _LOCK = threading.Lock()
    _unavailable_logged = False
    if _child is not None:
        _inherited.append(_child)
    _child = None


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_after_fork)


def run(task: Callable[..., Any], *args: Any) -> Any:
    """Return ``task(*args)``, called in the child, as JSON gives it back.

    ``task`` must be a function defined at the top level of a module, and
    ``args`` must be picklable. A result that JSON cannot encode makes the
    call fail; a tuple is returned as a list, and the caller checks the
    result's type before relying on it.

    Raises
    ------
    DecodingFailed
        If the call raised an :class:`Exception`.
    DecoderEnded
        If the child ended during the call, or sent back something other
        than :func:`_serve` gives.
    DecoderUnavailable
        If the child could not be started, or the process is exiting.
    """
    global _child, _unavailable_logged  # pylint: disable = global-statement
    with _LOCK:
        if _exiting:
            raise DecoderUnavailable()
        # A child that ended between calls, as by the system ending it,
        # ended during none of them.
        if _child is not None and _child.process.poll() is not None:
            _discard()
        if _child is None:
            try:
                _child = _Child()
            # As where Python cannot be run, or cannot import this package,
            # or a daemonic process may not start another.
            except Exception as error:  # pylint: disable = broad-exception-caught
                if not _unavailable_logged:
                    _unavailable_logged = True
                    _log.warning(
                        "The process that decodes with GDCM and pylibjpeg "
                        "could not be started (%s), so instances that need "
                        "them are withheld.",
                        type(error).__name__,
                    )
                raise DecoderUnavailable() from None
        # Bound here, as the exit hook can discard the child without the lock.
        child = _child
        try:
            returned = child.call(task, args)
        # RecursionError is for JSON nested too deeply to read.
        except (EOFError, OSError, ValueError, RecursionError):
            _discard()
            raise DecoderEnded() from None
        # A call cut short, as by KeyboardInterrupt, would leave its result
        # in the pipe, to be read as the next call's.
        except BaseException:
            _discard()
            raise
    _reissue(returned)
    if not returned.succeeded:
        raise DecodingFailed()
    return returned.result


def _configuration() -> tuple[bool, int, int]:
    """Return what of pydicom's configuration the child takes from the caller:
    whether it imitates its future behaviour, its validation mode for
    reading, and the effective level of its logger."""
    # pydicom has no public getter for the future behaviour.
    future = bool(pydicom.config._use_future)  # pylint: disable = protected-access
    return (
        future,
        pydicom.config.settings.reading_validation_mode,
        logging.getLogger(_LOGGER).getEffectiveLevel(),
    )


def _configure(configuration: tuple[bool, int, int]) -> None:
    """Configure pydicom in the child as :func:`_configuration` gives it."""
    future, reading, level = configuration
    pydicom.config.future_behavior(future)
    pydicom.config.settings.reading_validation_mode = reading
    logging.getLogger(_LOGGER).setLevel(level)


def _returned(sent: Any) -> _Returned:
    """Return what :func:`_serve` sent, once checked to have its form.

    Raises
    ------
    ValueError
        If it does not have that form.
    """
    if not (isinstance(sent, list) and len(sent) == 4):
        raise ValueError()
    succeeded, result, warned, logged = sent
    if not (
        isinstance(succeeded, bool)
        and isinstance(warned, list)
        and isinstance(logged, list)
    ):
        raise ValueError()
    return _Returned(
        succeeded,
        result,
        [_warned(entry) for entry in warned],
        [_logged(entry) for entry in logged],
    )


def _warned(entry: Any) -> _Warned:
    """Return a warning that :func:`_serve` sent, once checked."""
    if not (isinstance(entry, list) and len(entry) == 4):
        raise ValueError()
    text, category, module, lineno = entry
    if not (
        isinstance(text, str)
        and isinstance(category, str)
        and (module is None or isinstance(module, str))
        and _is_int(lineno)
        and 0 <= lineno <= _LINES
    ):
        raise ValueError()
    return _Warned(text, _CATEGORIES.get(category, UserWarning), module, lineno)


def _logged(entry: Any) -> _Logged:
    """Return a log record that :func:`_serve` sent, once checked."""
    if not (isinstance(entry, list) and len(entry) == 3):
        raise ValueError()
    name, level, text = entry
    if not (
        isinstance(name, str)
        and (name == _LOGGER or name.startswith(f"{_LOGGER}."))
        and _is_int(level)
        and isinstance(text, str)
    ):
        raise ValueError()
    return _Logged(name, level, text)


def _is_int(value: object) -> bool:
    """Return whether ``value`` is an int, and not a bool."""
    return isinstance(value, int) and not isinstance(value, bool)


def _reissue(returned: _Returned) -> None:
    """Issue in the caller the warnings and log records that a call gave in
    the child, so that the caller's filters, handlers, and redaction apply to
    them as they would have in process.

    A warning is issued as from the module that the child names, and from
    the file that the caller imported it from, where the caller has imported
    a plain module of that name, so that filters on modules match it;
    otherwise it is issued as from :data:`_ELSEWHERE`. A warning that the
    caller's filters turn into an exception raises it, as in process.
    """
    for warned in returned.warned:
        filename = _file_of(sys.modules.get(warned.module)) if warned.module else None
        if filename is not None:
            module = warned.module
        else:
            module = filename = _ELSEWHERE
        warnings.warn_explicit(
            warned.category(warned.text),
            warned.category,
            filename,
            warned.lineno,
            module,
            _REGISTRIES.setdefault(module, {}),
        )
    for logged in returned.logged:
        _logger_named(logged.name).log(logged.level, "%s", logged.text)


def _logger_named(name: str) -> logging.Logger:
    """Return the caller's logger of that name, if it has one, or else
    pydicom's, so that the names the child sends create no loggers."""
    logger = logging.Logger.manager.loggerDict.get(name)
    return logger if isinstance(logger, logging.Logger) else logging.getLogger(_LOGGER)


def _file_of(module: object) -> str | None:
    """Return the file that ``module`` was imported from, if it is a plain
    module that has one.

    Only a plain module's own attributes are read: a lazy module, such as
    those of :mod:`pymedphys._imports`, imports what it stands for when an
    attribute of it is read.
    """
    if type(module) is not types.ModuleType:  # pylint: disable = unidiomatic-typecheck
        return None
    filename = module.__dict__.get("__file__")
    return filename if isinstance(filename, str) else None


def _discard() -> None:
    """End the child, if there is one, so that the next call starts another."""
    global _child  # pylint: disable = global-statement
    # Taken first, so that another thread discarding it at the same time,
    # as one that was reading its result as the process exits, finds none.
    child, _child = _child, None
    if child is not None:
        child.close()


def _exit() -> None:
    """End the child as the process exits, rather than as the interpreter is
    torn down, and start no other."""
    global _exiting  # pylint: disable = global-statement
    _exiting = True
    _discard()


atexit.register(_exit)


def _send(stream: IO[bytes], message: object) -> None:
    """Write ``message`` pickled, after its length."""
    pickled = pickle.dumps(message, protocol=pickle.HIGHEST_PROTOCOL)
    stream.write(_LENGTH.pack(len(pickled)))
    stream.write(pickled)
    stream.flush()


def _send_json(stream: IO[bytes], message: object) -> None:
    """Write ``message`` as JSON, after its length, as :func:`_send` does.

    Raises
    ------
    TypeError, ValueError
        If JSON cannot encode ``message``.
    """
    encoded = json.dumps(message).encode()
    stream.write(_LENGTH.pack(len(encoded)))
    stream.write(encoded)
    stream.flush()


def _received(stream: IO[bytes], limit: int | None = None) -> bytes:
    """Read a message that :func:`_send` or :func:`_send_json` wrote.

    Raises
    ------
    EOFError
        If the stream ends first, or the message is longer than ``limit``.
    """
    header = stream.read(_LENGTH.size)
    if len(header) < _LENGTH.size:
        raise EOFError()
    (length,) = _LENGTH.unpack(header)
    if limit is not None and length > limit:
        raise EOFError()
    message = stream.read(length)
    if len(message) < length:
        raise EOFError()
    return message


class _Records(logging.Handler):
    """Keeps the name, level, and message of each record it handles."""

    def __init__(self) -> None:
        super().__init__()
        self.kept: list[tuple[str, int, str]] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            text = record.getMessage()
        # A record whose arguments do not fit its message.
        except Exception:  # pylint: disable = broad-exception-caught
            text = ""
        self.kept.append((record.name, record.levelno, text))


def _serve(results: IO[bytes]) -> None:
    """Make each call that the parent sends, until it closes the pipe.

    Each result is sent as JSON: a list of whether the call returned, what
    it returned or ``None``, the warnings it gave, and the records of
    pydicom's loggers that it gave. Each warning is a list of its message's
    text, its category's name where that is a built-in warning class, or
    else ``""``, the name of the module that issued it, or ``None``, and its
    line. Each record is a list of its logger's name, its level, and its
    message. A call whose result JSON cannot encode is sent as one that
    raised.
    """
    _no_core_files()
    # An interrupt is the parent's to handle, which ends the child.
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    # Records of pydicom's loggers are returned, and handled nowhere here:
    # pydicom adds its handler as it is imported.
    pydicom_logger = logging.getLogger(_LOGGER)
    pydicom.config.settings  # pylint: disable = pointless-statement
    for handler in list(pydicom_logger.handlers):
        pydicom_logger.removeHandler(handler)
    pydicom_logger.propagate = False
    records = _Records()
    pydicom_logger.addHandler(records)
    calls = sys.stdin.buffer
    _send_json(results, _READY)
    while True:
        try:
            # From the parent that started the child, which is trusted.
            task, args, configuration = pickle.loads(_received(calls))  # nosec B301
        except EOFError:
            return
        records.kept = []
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            try:
                _configure(configuration)
                succeeded, result = True, task(*args)
            # The parent is told only that the call raised, since a message
            # can quote a value.
            except Exception:  # pylint: disable = broad-exception-caught
                succeeded, result = False, None
        warned = [
            [
                str(each.message),
                _category_name(each.category),
                _module_named(each.filename),
                each.lineno,
            ]
            for each in caught
        ]
        logged = [list(record) for record in records.kept]
        try:
            _send_json(results, [succeeded, result, warned, logged])
        except (TypeError, ValueError):
            _send_json(results, [False, None, warned, logged])


def _category_name(category: type[Warning]) -> str:
    """Return the name of ``category`` if it is a built-in warning class,
    or else ``""``."""
    name = category.__name__
    return name if _CATEGORIES.get(name) is category else ""


def _module_named(filename: str) -> str | None:
    """Return the name of the imported module that ``filename`` holds, if any."""
    for name, module in list(sys.modules.items()):
        if _file_of(module) == filename:
            return name
    return None


def _no_core_files() -> None:
    """Set the child's core file size limit to zero, where the platform has
    one, so that a decoder that aborts writes no core file of what it was
    decoding."""
    if sys.platform == "win32":
        return
    import resource  # pylint: disable = import-outside-toplevel, import-error

    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
