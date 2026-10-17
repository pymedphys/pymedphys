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
into an error makes the call raise it. Each warning keeps its message, its
category where the caller has imported its module, and where it was
issued; nothing in the child shows or handles either. The child takes from
the caller whether pydicom imitates its future behaviour, its validation
mode for reading, and the level of its logger, and reads with pydicom's
configuration as it is when pydicom is imported for the rest. A result is
unpickled allowing no class but :class:`~.reasons.TransformReason`, and no
more than 16 MiB, so that a child whose decoder a codestream subverted
cannot make the caller run code. What a native library writes to the
standard output or error stream goes to the caller's standard error
stream, unredacted, as it would in process. The child's core file size
limit is zero, where the platform has one, so that a decoder that aborts
writes no core file holding the file it was decoding.

If the child ends during a call, :func:`run` raises :class:`DecoderEnded`,
and the next call starts a new child, as does a call after the child ended
between calls. If it cannot be started, or ends before it is ready for
calls, :func:`run` raises :class:`DecoderUnavailable`. Before anything is
imported in the child, its standard output is set aside for results, so
that nothing written as a module is imported can be read as one. A process
forked from the caller starts its own child, rather than sharing the
caller's pipes to it. A call that
does not return, such as a decoder that loops forever, is waited for, as it
would be in process: a time limit would make the outcome depend on the
machine's speed. Calls are made one at a time, whichever thread makes them.
"""

from __future__ import annotations

import io
import logging
import os

# Calls are unpickled only by the child, from the parent that started it, and
# results only by _Results, which loads no class but those it allows.
import pickle  # nosec B403
import signal
import struct
import subprocess
import sys
import threading
import warnings
from collections.abc import Callable, Sequence
from typing import IO, Any, TypeVar

from pymedphys._imports import pydicom

_Result = TypeVar("_Result")
_LOGGER = "pydicom"
# The only class that a result may hold, besides values that pickle builds
# without one, such as None, bool, int, and tuple, so that a child whose
# decoder a codestream subverted cannot make the parent run code.
_RESULT_CLASSES = frozenset(
    {("pymedphys._dicom.deidentify.reasons", "TransformReason")}
)
# Far more than any result, with its warnings and log records, needs.
_RESULT_BYTES = 1 << 24
# Where the warnings that the child returns are registered as shown, as each
# module's own registry would register them in process.
_REGISTRY: dict = {}
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

    def call(
        self, task: Callable[..., Any], args: tuple
    ) -> tuple[bool, Any, Sequence[tuple], Sequence[tuple]]:
        """Return whether ``task(*args)`` returned, what, and the warnings
        and log records it gave, as :func:`_serve` describes them."""
        _send(self.stdin, (task, args, _configuration()))
        return self.result()

    def result(self) -> Any:
        """Read what the child sent, allowing only :data:`_RESULT_CLASSES`."""
        return _Results(io.BytesIO(_received(self.stdout, _RESULT_BYTES))).load()

    def close(self) -> None:
        """End the child, if it has not ended, and close its pipes."""
        for stream in (self.stdin, self.stdout):
            try:
                stream.close()
            except OSError:
                pass
        if self.process.poll() is None:
            self.process.kill()
        self.process.wait()


_LOCK = threading.Lock()
_child: _Child | None = None
# The children of the processes that this one was forked from, which it
# leaves to them.
_inherited: list[_Child] = []


def _after_fork() -> None:
    """Start afresh in a forked process, which shares its parent's pipes to
    the child, and may have been forked while another thread held the lock."""
    global _LOCK, _child  # pylint: disable = global-statement
    _LOCK = threading.Lock()
    if _child is not None:
        _inherited.append(_child)
    _child = None


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_after_fork)


def run(task: Callable[..., _Result], *args: Any) -> _Result:
    """Return ``task(*args)``, called in the child.

    ``task`` must be a function defined at the top level of a module, and
    ``args`` and the result must be picklable.

    Raises
    ------
    DecodingFailed
        If the call raised an :class:`Exception`.
    DecoderEnded
        If the child ended during the call, or returned a result of a class
        that results may not hold.
    DecoderUnavailable
        If the child could not be started.
    """
    global _child  # pylint: disable = global-statement
    with _LOCK:
        # A child that ended between calls, as by the system ending it,
        # ended during none of them.
        if _child is not None and _child.process.poll() is not None:
            _discard()
        if _child is None:
            try:
                _child = _Child()
            # As where Python cannot be run, or cannot import this package,
            # or a daemonic process may not start another.
            except Exception:  # pylint: disable = broad-exception-caught
                raise DecoderUnavailable() from None
        try:
            succeeded, result, warned, logged = _child.call(task, args)
        except (EOFError, OSError, pickle.UnpicklingError):
            _discard()
            raise DecoderEnded() from None
        # A call cut short, as by KeyboardInterrupt, would leave its result
        # in the pipe, to be read as the next call's.
        except BaseException:
            _discard()
            raise
    _reissue(warned, logged)
    if not succeeded:
        raise DecodingFailed()
    return result


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


def _reissue(warned: Sequence[tuple], logged: Sequence[tuple]) -> None:
    """Issue in the caller the warnings and log records that a call gave in
    the child, so that the caller's filters, handlers, and redaction apply to
    them as they would have in process.

    A warning's category is found among the modules that the caller has
    imported, and is :class:`UserWarning` where it is not; its message is
    issued as text. A warning that the caller's filters turn into an
    exception raises it, as in process.
    """
    for text, (module, qualname), filename, lineno, origin in warned:
        category = _category(module, qualname)
        try:
            message = category(text)
        # A category whose constructor needs other arguments.
        except Exception:  # pylint: disable = broad-exception-caught
            message = UserWarning(text)
        warnings.warn_explicit(
            message, type(message), filename, lineno, origin, _REGISTRY
        )
    for name, level, text in logged:
        if name == _LOGGER or name.startswith(f"{_LOGGER}."):
            logging.getLogger(name).log(level, "%s", text)


def _category(module: str, qualname: str) -> type[Warning]:
    """Return the warning category of that name, if the caller has imported
    its module, or else :class:`UserWarning`."""
    found: object = sys.modules.get(module)
    for part in qualname.split("."):
        found = getattr(found, part, None)
    if isinstance(found, type) and issubclass(found, Warning):
        return found
    return UserWarning


def _discard() -> None:
    """End the child, if there is one, so that the next call starts another."""
    global _child  # pylint: disable = global-statement
    if _child is not None:
        _child.close()
        _child = None


def _send(stream: IO[bytes], message: object) -> None:
    """Write ``message`` pickled, after its length."""
    pickled = pickle.dumps(message, protocol=pickle.HIGHEST_PROTOCOL)
    stream.write(_LENGTH.pack(len(pickled)))
    stream.write(pickled)
    stream.flush()


class _Results(pickle.Unpickler):
    """Unpickles a result, refusing any class but :data:`_RESULT_CLASSES`."""

    def find_class(self, module: str, name: str) -> Any:
        if (module, name) not in _RESULT_CLASSES:
            raise pickle.UnpicklingError("a result may not hold that class")
        return super().find_class(module, name)


def _received(stream: IO[bytes], limit: int | None = None) -> bytes:
    """Read a pickled message that :func:`_send` wrote.

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
    pickled = stream.read(length)
    if len(pickled) < length:
        raise EOFError()
    return pickled


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

    Each result is whether the call returned, what it returned or ``None``,
    the warnings it gave, as their message's text, their category's module
    and qualified name, and where they were issued, and the records of
    pydicom's loggers that it gave, as their logger's name, level, and
    message.
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
    _send(results, _READY)
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
            (
                str(each.message),
                (each.category.__module__, each.category.__qualname__),
                each.filename,
                each.lineno,
                _module_named(each.filename),
            )
            for each in caught
        ]
        _send(results, (succeeded, result, warned, records.kept))


def _module_named(filename: str) -> str | None:
    """Return the name of the imported module that ``filename`` holds, if any."""
    for name, module in list(sys.modules.items()):
        if getattr(module, "__file__", None) == filename:
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
