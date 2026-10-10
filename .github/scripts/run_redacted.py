"""Run a module's ``main`` and report a crash without its message.

Usage: ``python .github/scripts/run_redacted.py <module> [arguments...]``.

The MIDI-B benchmark workflow runs the de-identification tools over data
whose synthetic identifiers the project treats as real, and the logs of a
public repository's workflows are public. Those tools refuse with messages
that quote no value, but an unexpected exception's message, or a frame's
local variables, could quote one. So this runs ``<module>.main(arguments)``
and, on an exception other than ``SystemExit``, prints only the exception's
type and, for each frame of its traceback, the code's location: a path
inside an installed package or this checkout, a line number, and a function
name, never a message or a value. The caller sends standard error, where
libraries log, to a private file.

Exit status: the module's own; 2 when its ``main`` raised.
"""

from __future__ import annotations

import importlib
import sys
import traceback
from collections.abc import Callable, Sequence
from pathlib import PurePath

CRASHED = 2
_ROOTS = ("site-packages", "lib")


def code_location(filename: str) -> str:
    """The part of a source path that names code, not where it is installed.

    >>> code_location("/opt/venv/lib/python3.14/site-packages/pydicom/dataset.py")
    'pydicom/dataset.py'
    >>> code_location("/work/pymedphys/lib/pymedphys/_dicom/deidentify/run.py")
    'pymedphys/_dicom/deidentify/run.py'
    >>> code_location("/usr/lib/python3.14/concurrent/futures/_base.py")
    'concurrent/futures/_base.py'
    >>> code_location("<frozen runpy>")
    '<frozen runpy>'
    >>> code_location("/data/somewhere/else.py")
    '<elsewhere>'
    """
    if filename.startswith("<") and filename.endswith(">"):
        return filename
    parts = PurePath(filename).parts
    for root in _ROOTS:
        if root in parts:
            index = len(parts) - 1 - parts[::-1].index(root)
            rest = parts[index + 1 :]
            if rest and rest[0].startswith("python"):
                rest = rest[1:]  # the standard library
            if rest:
                return "/".join(rest)
    return "<elsewhere>"


def describe(error: BaseException) -> list[str]:
    """Lines naming the exception's type and each frame's code location."""
    kind = type(error)
    lines = [f"{kind.__module__}.{kind.__qualname__} was raised at:"]
    for frame in traceback.extract_tb(error.__traceback__):
        lines.append(
            f"  {code_location(frame.filename)}:{frame.lineno} in {frame.name}"
        )
    cause = error.__cause__ or (
        None if error.__suppress_context__ else error.__context__
    )
    if cause is not None:
        lines.append("while handling:")
        lines.extend(describe(cause))
    return lines


def run(main: Callable[[Sequence[str]], int | None], arguments: Sequence[str]) -> int:
    """Call ``main(arguments)`` and return its exit status, redacting a crash."""
    try:
        status = main(arguments)
    except SystemExit as error:
        # A tool's own refusal: its message quotes no value, by contract.
        if isinstance(error.code, str):
            print(error.code, flush=True)
            return 1
        return 0 if error.code is None else int(error.code)
    except BaseException as error:  # pylint: disable = broad-exception-caught
        print("\n".join(describe(error)), flush=True)
        return CRASHED
    return 0 if status is None else int(status)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: run_redacted.py <module> [arguments...]")
    sys.exit(run(importlib.import_module(sys.argv[1]).main, sys.argv[2:]))
