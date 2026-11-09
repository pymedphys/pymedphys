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

"""Record reviewers' annotation decisions in the custodian's reviewed annotations list.

Run as ``python -m pymedphys._dicom.deidentify.reviewed_annotations_command
LIST DECISIONS``. It is not registered with the ``pymedphys`` command:
nothing de-identification related joins the public command line before the
first supported release.

A reviewer reads the text and the drawing of each graphic annotation of a
Presentation State that a run under the Clean Graphics Option held for
review, from its QC pack, and writes a decision on each into a CSV file,
which this command records in the list (D-062). The file is read as the
reviewed-names command reads its own (:mod:`.reviewed_names_command`), with
these columns:

- ``digest``: the annotation's digest, 64 lowercase hexadecimal digits, as
  the QC pack gives it;
- ``decision``: ``keep``, to write the annotation as it was received but
  for its UIDs, or ``remove``, to remove it with everything in it.

The list is started at ``LIST`` on first use, and never inside the PyMedPhys
configuration directory or a directory given with ``--protect``. Recording is
all or nothing, as for ROI Names: an annotation given different decisions
in the file is refused, as is a decision that differs from the list's,
unless ``--replace`` is given. Neither the summary nor any message quotes a
digest, a cell, or the list's or the file's path.

Exit statuses are those of :mod:`.reviewed_names_command`.
"""

from __future__ import annotations

import argparse
import dataclasses
import os
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import TextIO

from .command import _Parser, _print
from .reviewed_annotations import Review, ReviewedAnnotations, ReviewedAnnotationsError
from .reviewed_names_command import (
    EXIT_NOT_RECORDED,
    EXIT_RECORDED,
    EXIT_USAGE,
    read_cell,
    read_columns,
    read_rows,
)

__all__ = ["EXIT_NOT_RECORDED", "EXIT_RECORDED", "EXIT_USAGE"]

_COLUMNS = ("digest", "decision")


@dataclasses.dataclass(frozen=True)
class Decision:
    """A reviewer's decision on one annotation, read from a line of the file."""

    line: int
    digest: str = dataclasses.field(repr=False)
    review: Review


@dataclasses.dataclass(frozen=True)
class Recorded:
    """What :func:`record_decisions` recorded, as counts without digests.

    Attributes
    ----------
    created : bool
        Whether the list was started by this call.
    new, replaced, unchanged : int
        How many distinct annotations of the file the list did not hold,
        held with another decision, which was replaced, or held with the
        same decision.
    listed : int
        How many annotations the list holds afterwards.
    """

    created: bool
    new: int
    replaced: int
    unchanged: int
    listed: int

    def summary_lines(self) -> list[str]:
        """Return the summary that the command prints."""
        lines = ["started a new reviewed annotations list"] if self.created else []
        lines.append(f"decisions recorded: {self.new + self.replaced + self.unchanged}")
        lines += [
            f"  {label}: {count}"
            for label, count in (
                ("new", self.new),
                ("replaced", self.replaced),
                ("unchanged", self.unchanged),
            )
            if count
        ]
        lines.append(f"annotations in the list: {self.listed}")
        return lines


def read_decisions(path: str | os.PathLike) -> tuple[Decision, ...]:
    """Read the decisions in the CSV file at ``path``, as the module describes.

    An annotation given the same decision on several lines is returned once,
    from its first line.

    Raises
    ------
    ReviewedAnnotationsError
        If the file cannot be read as UTF-8 CSV; if its header lacks a
        column or repeats one; if it holds no decision; or if a row has more
        cells than the header, a digest that is not 64 lowercase hexadecimal
        digits, a decision other than keep or remove, or an annotation given
        different decisions. The message names lines by number, never a
        digest, a cell, or the path.
    """
    header, body = read_rows(path, ReviewedAnnotationsError)
    columns = read_columns(
        header,
        _COLUMNS,
        _COLUMNS,
        ReviewedAnnotationsError(
            "the decisions file needs the columns digest and decision"
        ),
    )
    decisions: dict[str, Decision] = {}
    for line, cells in body:
        if len(cells) > len(header):
            raise ReviewedAnnotationsError(
                f"line {line} has more cells than the header"
            )
        decision = _decision(line, cells, columns)
        earlier = decisions.setdefault(decision.digest, decision)
        if earlier.review is not decision.review:
            raise ReviewedAnnotationsError(
                f"lines {earlier.line} and {line} give one annotation different "
                "decisions"
            )
    if not decisions:
        raise ReviewedAnnotationsError("the decisions file holds no decisions")
    return tuple(decisions.values())


def _decision(line: int, cells: list[str], columns: dict[str, int]) -> Decision:
    review = read_cell(cells, columns, "decision").casefold()
    if review not in {each.value for each in Review}:
        raise ReviewedAnnotationsError(
            f"line {line}: the decision must be keep or remove"
        )
    digest = read_cell(cells, columns, "digest")
    try:
        # Checks the digest as the list does, without recording it.
        ReviewedAnnotations.empty().record(digest, Review(review))
    except ReviewedAnnotationsError as error:
        raise ReviewedAnnotationsError(f"line {line}: {error}") from None
    return Decision(line, digest, Review(review))


def record_decisions(
    list_path: str | os.PathLike,
    decisions_path: str | os.PathLike,
    *,
    replace: bool = False,
    protected_dirs: Iterable[str | os.PathLike] = (),
) -> Recorded:
    """Record the decisions of a CSV file in the reviewed annotations list.

    Parameters
    ----------
    list_path : str or os.PathLike
        The custodian's list, which is started if it does not exist.
    decisions_path : str or os.PathLike
        The CSV file, as :func:`read_decisions` reads it.
    replace : bool, optional
        Whether a decision may replace the list's different decision on the
        same annotation.
    protected_dirs : iterable of str or os.PathLike, optional
        Directories the list must not be inside, as for
        :meth:`~.reviewed_annotations.ReviewedAnnotations.open`.

    Returns
    -------
    Recorded

    Raises
    ------
    ReviewedAnnotationsError
        If the list cannot be kept at ``list_path``, or cannot be read or
        written; if the file cannot be read, as for :func:`read_decisions`;
        or if a decision differs from the list's and ``replace`` is false.
        The list is then as it was, and the message quotes no digest or
        path.
    """
    created = not os.path.lexists(list_path)
    reviewed = ReviewedAnnotations.open(list_path, protected_dirs=protected_dirs)
    decisions = read_decisions(decisions_path)
    counts = {"new": 0, "replaced": 0, "unchanged": 0}
    conflicts = []
    for decision in decisions:
        listed = reviewed.get(decision.digest)
        if listed is None:
            counts["new"] += 1
        elif listed is decision.review:
            counts["unchanged"] += 1
        else:
            counts["replaced"] += 1
            conflicts.append(decision.line)
    if conflicts and not replace:
        where = (
            f"line {conflicts[0]} gives an annotation"
            if len(conflicts) == 1
            else f"line {conflicts[0]} and {len(conflicts) - 1} more give annotations"
        )
        raise ReviewedAnnotationsError(
            f"{where} a decision other than the list's; give --replace to "
            "replace the list's decisions"
        )
    for decision in decisions:
        reviewed.record(decision.digest, decision.review, replace=True)
    try:
        reviewed.save()
    except OSError:
        raise ReviewedAnnotationsError(
            "the reviewed annotations list could not be written; its path is "
            "not shown because it can name a person"
        ) from None
    return Recorded(created=created, listed=len(reviewed), **counts)


def build_parser(*, stderr: TextIO | None = None) -> argparse.ArgumentParser:
    """Return the parser of the command's arguments.

    An argument error prints the usage and a fixed message to ``stderr``,
    by default :data:`sys.stderr`, and exits with :data:`EXIT_USAGE`.
    """
    parser = _Parser(
        prog="python -m pymedphys._dicom.deidentify.reviewed_annotations_command",
        stderr=stderr,
        description=(
            "Record the keep and remove decisions of a reviewer's CSV file in "
            "the custodian's reviewed annotations list, which is started if it "
            "does not exist. For use before the first supported release."
        ),
    )
    parser.add_argument(
        "list",
        metavar="LIST",
        help="the reviewed annotations list, kept by the custodian with the key",
    )
    parser.add_argument(
        "decisions",
        metavar="DECISIONS",
        help="the CSV file of decisions, with columns digest and decision",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help=(
            "replace the list's decision on an annotation that the file "
            "decides otherwise"
        ),
    )
    parser.add_argument(
        "--protect",
        action="append",
        default=[],
        metavar="DIRECTORY",
        help=(
            "a directory that LIST must not be inside, such as a run's source, "
            "release, or QC pack; may be given more than once"
        ),
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Parse the arguments, record the decisions, and print a summary.

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
    stdout = sys.stdout if stdout is None else stdout
    stderr = sys.stderr if stderr is None else stderr
    arguments = build_parser(stderr=stderr).parse_args(argv)
    try:
        recorded = record_decisions(
            Path(arguments.list),
            Path(arguments.decisions),
            replace=arguments.replace,
            protected_dirs=arguments.protect,
        )
    except ReviewedAnnotationsError as error:
        _print(f"error: {error}; nothing was recorded", stderr)
        return EXIT_NOT_RECORDED
    _print("\n".join(recorded.summary_lines()), stdout)
    return EXIT_RECORDED


if __name__ == "__main__":
    sys.exit(main())
