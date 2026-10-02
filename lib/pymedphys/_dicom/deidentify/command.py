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

"""The command line's entry point: de-identify a directory, and say what happened.

:func:`deidentify_directory` is the thin layer that the command line puts
over the library (design document, Scope). It discovers the source
directory's inputs with :func:`~pymedphys._dicom.deidentify.run.discover`,
runs them through :func:`~pymedphys._dicom.deidentify.run.run`, prints a
summary of the outcomes to standard output, and returns an exit status. The
whole of it runs within
:func:`~pymedphys._dicom.deidentify.diagnostics.redacted_diagnostics`, so
no warning or log record of pydicom's, or of the transform's or gate's,
shows a source value or path, and the summary says how many were redacted.
:func:`main` parses the source and release directories from the command
line's arguments, for the ``pymedphys`` command to call once the engine is
public; nothing registers it yet.

The summary and every message name inputs only by count, reasons only by
their type and member name, and directories only where the caller chose
them: the release directory and its staging area. A failure that the run
does not expect is reported by its exception's type alone, since its
message could quote a value.

Exit statuses:

- :data:`EXIT_RELEASED`, 0: every input was released, or is an identical
  copy of one that was;
- :data:`EXIT_WITHHELD`, 1: the release was published, but at least one
  input was refused, sequestered, or held for review;
- :data:`EXIT_USAGE`, 2: the arguments could not be parsed, as for any
  :mod:`argparse` command;
- :data:`EXIT_NOT_RUN`, 3: the run could not start, or the first pass
  stopped it, and nothing was published;
- :data:`EXIT_STAGING_LEFT`, 4: the staging area could not be deleted, and
  may hold output that still identifies people, whatever else happened;
- :data:`EXIT_INTERNAL_ERROR`, 70: anything else failed, and nothing was
  published (``EX_SOFTWARE`` of BSD's ``sysexits.h``).
"""

from __future__ import annotations

import argparse
import collections
import enum
import os
import sys
from collections.abc import Sequence
from typing import TextIO

from . import run
from .diagnostics import RedactionCounts, redacted_diagnostics

EXIT_RELEASED = 0
EXIT_WITHHELD = 1
EXIT_USAGE = 2
EXIT_NOT_RUN = 3
EXIT_STAGING_LEFT = 4
EXIT_INTERNAL_ERROR = 70

_RELEASED = (run.Status.RELEASED, run.Status.DUPLICATE)


def deidentify_directory(
    source: str | os.PathLike[str],
    release: str | os.PathLike[str],
    *,
    transform: run.Transform,
    gate: run.Gate,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """De-identify a source directory into a new release directory.

    Parameters
    ----------
    source : str or os.PathLike
        The source directory, as :func:`~pymedphys._dicom.deidentify.run.discover`
        takes it.
    release : str or os.PathLike
        The release directory, which must not exist, as
        :func:`~pymedphys._dicom.deidentify.run.run` takes it.
    transform : Transform
        The run's transform.
    gate : Gate
        The run's release gate.
    stdout, stderr : text file, optional
        Where to print the summary, and the reason the run failed or left
        its staging area behind. By default, :data:`sys.stdout` and
        :data:`sys.stderr`.

    Returns
    -------
    int
        The exit status, as the module describes.
    """
    stdout = sys.stdout if stdout is None else stdout
    stderr = sys.stderr if stderr is None else stderr
    with redacted_diagnostics() as counts:
        try:
            result = run.run(run.discover(source), release, transform, gate)
        except (run.RunError, run.RunStopped) as error:
            # Each names only the caller's directories, or counts.
            print(f"error: {error}", file=stderr)
            return EXIT_NOT_RUN
        except Exception as error:  # pylint: disable = broad-exception-caught
            print(
                f"error: the run failed with {type(error).__name__}, and "
                "nothing was published; its details are not shown because "
                "they can contain file paths or DICOM values",
                file=stderr,
            )
            return EXIT_INTERNAL_ERROR
    print("\n".join(summary_lines(result, counts)), file=stdout)
    if not result.staging_removed:
        print(
            f"error: the staging area {run.staging_path(result.release)} "
            "could not be deleted; it may hold output that still identifies "
            "people, so delete it by hand",
            file=stderr,
        )
    return exit_status(result)


def exit_status(result: run.RunResult) -> int:
    """Return the exit status of a run that published its release directory."""
    if not result.staging_removed:
        return EXIT_STAGING_LEFT
    if all(outcome.status in _RELEASED for outcome in result.outcomes):
        return EXIT_RELEASED
    return EXIT_WITHHELD


def summary_lines(result: run.RunResult, redacted: RedactionCounts) -> list[str]:
    """Return a summary of a run, without a source value or path.

    It gives the release directory; the number of inputs, and of each status
    that any input has; how many inputs each reason withheld; how many
    first-pass findings there were of each kind; and, if any were, how many
    warnings and log records were redacted.
    """
    statuses = collections.Counter(outcome.status for outcome in result.outcomes)
    reasons = collections.Counter(
        _reason_name(reason)
        for outcome in result.outcomes
        for reason in dict.fromkeys(outcome.reasons)
    )
    findings = collections.Counter(
        _reason_name(finding.kind) for finding in result.findings
    )
    lines = [
        f"release directory: {result.release}",
        f"inputs: {len(result.outcomes)}",
    ]
    lines += [
        f"  {status.value}: {statuses[status]}"
        for status in run.Status
        if statuses[status]
    ]
    if reasons:
        lines.append("reasons inputs were withheld:")
        lines += [f"  {name}: {count}" for name, count in sorted(reasons.items())]
    if findings:
        lines.append("first-pass findings:")
        lines += [f"  {name}: {count}" for name, count in sorted(findings.items())]
    if redacted.warnings or redacted.log_records:
        lines.append(
            f"redacted diagnostics: {redacted.warnings} warnings, "
            f"{redacted.log_records} log records"
        )
    return lines


def _reason_name(reason: object) -> str:
    # A reason's fields could hold anything a transform or gate put there,
    # so only an enum member's name, which the code defines, is shown.
    if isinstance(reason, enum.Enum):
        return f"{type(reason).__name__}.{reason.name}"
    return type(reason).__name__


def build_parser(prog: str | None = None) -> argparse.ArgumentParser:
    """Return the parser of the command line's arguments."""
    parser = argparse.ArgumentParser(
        prog=prog,
        description=(
            "De-identify the DICOM files below SOURCE into the new directory "
            "RELEASE, which is published whole once every file has been "
            "checked, or not at all."
        ),
    )
    parser.add_argument("source", help="the directory of source files")
    parser.add_argument(
        "release", help="the release directory to create, which must not exist"
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    transform: run.Transform,
    gate: run.Gate,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Parse the command line's arguments, and de-identify as they say.

    Parameters
    ----------
    argv : sequence of str, optional
        The arguments, by default ``sys.argv[1:]``.
    transform, gate, stdout, stderr
        As for :func:`deidentify_directory`.

    Returns
    -------
    int
        The exit status, as the module describes.

    Raises
    ------
    SystemExit
        With :data:`EXIT_USAGE` if the arguments cannot be parsed, or 0 for
        ``--help``, as :mod:`argparse` does.
    """
    arguments = build_parser().parse_args(argv)
    return deidentify_directory(
        arguments.source,
        arguments.release,
        transform=transform,
        gate=gate,
        stdout=stdout,
        stderr=stderr,
    )
