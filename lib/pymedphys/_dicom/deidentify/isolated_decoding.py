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
aborts, whenever libjpeg warns while it reads a frame's header: for a JFIF
segment of a version it does not know, for example, or for bytes between
two markers.

So :mod:`.pixel_decoding` hands each decode by those plugins to :func:`run`,
which calls it in one child process, started when first needed and kept
for the life of the process, so that each instance costs one exchange of
its bytes over a pipe, not a new interpreter. The child is the same Python,
started in isolated mode (``-I``) with the caller's module search path,
and imports only what a call needs: unlike :mod:`multiprocessing`'s
``spawn`` method, it never imports the caller's main module, which, in a
script without an ``if __name__ == "__main__":`` guard, would run the
script again. The child returns only the call's result, or that it raised:
never an error message, a warning, or a log record, since any of them can
quote a value. It ignores its warnings and drops its log records, and reads
with pydicom's configuration as it is when pydicom is imported, from its
environment, not as the caller may have changed it since. What a native
library writes to the standard output or error stream goes to the caller's
standard error stream, unredacted, as it would in process.

If the child ends during a call, or cannot be started, :func:`run` raises
:class:`DecoderEnded`, and the next call starts a new child. A call that
does not return, such as a decoder that loops forever, is waited for, as it
would be in process: a time limit would make the outcome depend on the
machine's speed. Calls are made one at a time, whichever thread makes them.
"""

from __future__ import annotations

import logging
import os
import pickle
import signal
import struct
import subprocess
import sys
import threading
import warnings
from collections.abc import Callable
from typing import IO, Any, TypeVar

_Result = TypeVar("_Result")
_LENGTH = struct.Struct("<Q")
# Run by the child: it reads the module search path, framed as _send frames
# it, and only then imports anything that the path could find elsewhere.
_BOOTSTRAP = (
    "import pickle, struct, sys\n"
    "stream = sys.stdin.buffer\n"
    "(length,) = struct.unpack('<Q', stream.read(8))\n"
    "sys.path[:] = pickle.loads(stream.read(length))\n"
    "from pymedphys._dicom.deidentify import isolated_decoding\n"
    "isolated_decoding._serve()\n"
)


class DecodingFailed(Exception):
    """The call raised in the child; what it raised is not passed on."""


class DecoderEnded(DecodingFailed):
    """The child ended during the call, as by an abort or a signal, or could
    not be started."""


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

    def call(self, task: Callable[..., Any], args: tuple) -> tuple[bool, Any]:
        """Return whether ``task(*args)`` returned, and what."""
        _send(self.stdin, (task, args))
        return _receive(self.stdout)

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


def run(task: Callable[..., _Result], *args: Any) -> _Result:
    """Return ``task(*args)``, called in the child.

    ``task`` must be a function defined at the top level of a module, and
    ``args`` and the result must be picklable.

    Raises
    ------
    DecodingFailed
        If the call raised an :class:`Exception`.
    DecoderEnded
        If the child ended during the call, or could not be started.
    """
    global _child  # pylint: disable = global-statement
    with _LOCK:
        try:
            if _child is None:
                _child = _Child()
            succeeded, result = _child.call(task, args)
        except (EOFError, OSError):
            _discard()
            raise DecoderEnded() from None
        # A call cut short, as by KeyboardInterrupt, would leave its result
        # in the pipe, to be read as the next call's.
        except BaseException:
            _discard()
            raise
    if not succeeded:
        raise DecodingFailed()
    return result


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


def _receive(stream: IO[bytes]) -> Any:
    """Read a message that :func:`_send` wrote.

    Raises
    ------
    EOFError
        If the stream ends first.
    """
    header = stream.read(_LENGTH.size)
    if len(header) < _LENGTH.size:
        raise EOFError()
    (length,) = _LENGTH.unpack(header)
    pickled = stream.read(length)
    if len(pickled) < length:
        raise EOFError()
    return pickle.loads(pickled)


def _serve() -> None:
    """Make each call that the parent sends, until it closes the pipe."""
    # An interrupt is the parent's to handle, which ends the child.
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    warnings.simplefilter("ignore")
    logging.disable(logging.CRITICAL)
    # Results go to what was standard output, and anything else written to
    # it, as by a native library, goes to standard error.
    results = os.fdopen(os.dup(sys.stdout.fileno()), "wb")
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    calls = sys.stdin.buffer
    while True:
        try:
            task, args = _receive(calls)
        except EOFError:
            return
        try:
            result = (True, task(*args))
        # The parent is told only that the call raised, since a message can
        # quote a value.
        except Exception:  # pylint: disable = broad-exception-caught
            result = (False, None)
        _send(results, result)
