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

"""Record reviewers' ROI Name decisions in the custodian's reviewed-names list.

Run as ``python -m pymedphys._dicom.deidentify.reviewed_names_command LIST
DECISIONS``. It is not registered with the ``pymedphys`` command: nothing
de-identification related joins the public command line before the first
supported release.

A reviewer reads the ROI Names that a run held for review in its
confidential QC pack, and writes a decision on each into a CSV file, which
this command records in the list (D-009). The file is UTF-8, with or without
a byte order mark, and has a header row naming its columns, in any order and
case:

- ``roi_name``: the ROI Name, as the QC pack gives it;
- ``decision``: ``keep``, ``map``, or ``empty``;
- ``to``: for ``map``, the name to write instead; otherwise empty. The
  column may be left out of a file without a mapping.

Other columns, such as a reviewer's notes, are ignored, as are rows whose
cells are all empty. Spaces around a cell are disregarded, as LO padding is
when the list is applied, so they are not part of a name.

The list is created at ``LIST`` on first use, readable only by its owner, as
:meth:`~.reviewed_roi_names.ReviewedNames.save` writes it, and never inside
the PyMedPhys configuration directory or a directory given with
``--protect``, such as a run's source, release, and QC pack directories.

Recording is all or nothing: the list is written only once every row has
been read and checked. A name given different decisions in the file is
refused, as is a decision on a listed name that differs from the list's,
unless ``--replace`` is given. The list holds source ROI Names verbatim, so
neither the summary nor any message quotes a name, a cell, or the list's or
the file's path; a message names a row by its line in the file.

Exit statuses:

- :data:`EXIT_RECORDED`, 0: every decision was recorded;
- :data:`EXIT_NOT_RECORDED`, 1: nothing was recorded, and the list is as it
  was;
- :data:`EXIT_USAGE`, 2: the arguments could not be parsed, and the message
  quotes none of them.
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import os
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import TextIO

from . import command
from .command import _Parser, _print
from .reviewed_roi_names import (
    Review,
    ReviewedName,
    ReviewedNames,
    ReviewedNamesError,
)

EXIT_RECORDED = 0
EXIT_NOT_RECORDED = 1
EXIT_USAGE = command.EXIT_USAGE

_REQUIRED = ("roi_name", "decision")
_COLUMNS = (*_REQUIRED, "to")
# Spaces around a cell, which a spreadsheet may add; NUL, which LO padding
# can hold, cannot be in a CSV file that is read as text.
_CELL_PADDING = " "


@dataclasses.dataclass(frozen=True)
class Decision:
    """A reviewer's decision on one ROI Name, read from a line of the file.

    Its ``repr`` leaves out the name.
    """

    line: int
    name: str = dataclasses.field(repr=False)
    decision: ReviewedName


@dataclasses.dataclass(frozen=True)
class Recorded:
    """What :func:`record_decisions` recorded, as counts without names.

    Attributes
    ----------
    created : bool
        Whether the list was started by this call.
    new, replaced, unchanged : int
        How many distinct names of the file the list did not hold, held with
        another decision, which was replaced, or held with the same decision.
    listed : int
        How many names the list holds afterwards.
    """

    created: bool
    new: int
    replaced: int
    unchanged: int
    listed: int

    def summary_lines(self) -> list[str]:
        """Return the summary that the command prints."""
        lines = ["started a new reviewed-names list"] if self.created else []
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
        lines.append(f"names in the list: {self.listed}")
        return lines


def read_decisions(path: str | os.PathLike) -> tuple[Decision, ...]:
    """Read the decisions in the CSV file at ``path``, as the module describes.

    A name given the same decision on several lines is returned once, from
    its first line.

    Raises
    ------
    ReviewedNamesError
        If the file cannot be read as UTF-8 CSV; if its header lacks a
        required column or repeats one; if it holds no decision; or if a row
        has more cells than the header, a name that the list cannot hold, a
        decision other than keep, map, or empty, a name to write that does not
        fit its decision, or a name given different decisions. The message
        names lines by number, never a name, a cell, or the path.
    """
    try:
        with open(path, encoding="utf-8-sig", newline="") as file:
            reader = csv.reader(file, strict=True)
            # Rows whose cells are all empty are left out, each other row
            # with the line it ends on.
            rows = [
                (reader.line_num, row)
                for row in reader
                if any(cell.strip(_CELL_PADDING) for cell in row)
            ]
    except UnicodeDecodeError:
        raise ReviewedNamesError("the decisions file is not UTF-8") from None
    except csv.Error:
        # Not chained, since the error can quote the file's text.
        raise ReviewedNamesError(
            "the decisions file could not be read as CSV"
        ) from None
    except OSError:
        raise ReviewedNamesError("the decisions file could not be read") from None
    if not rows:
        raise ReviewedNamesError("the decisions file has no header")
    (_, header), body = rows[0], rows[1:]
    columns = _columns(header)
    decisions: dict[str, Decision] = {}
    for line, cells in body:
        if len(cells) > len(header):
            raise ReviewedNamesError(f"line {line} has more cells than the header")
        decision = _decision(line, cells, columns)
        earlier = decisions.setdefault(decision.name, decision)
        if earlier.decision != decision.decision:
            raise ReviewedNamesError(
                f"lines {earlier.line} and {line} give one ROI Name different decisions"
            )
    if not decisions:
        raise ReviewedNamesError("the decisions file holds no decisions")
    return tuple(decisions.values())


def _columns(header: list[str]) -> dict[str, int]:
    names = [cell.strip(_CELL_PADDING).casefold() for cell in header]
    columns = {}
    for index, name in enumerate(names):
        if name in _COLUMNS:
            if name in columns:
                raise ReviewedNamesError("the decisions file's header repeats a column")
            columns[name] = index
    if not all(name in columns for name in _REQUIRED):
        raise ReviewedNamesError(
            "the decisions file needs the columns roi_name and decision, and to "
            "for a mapping"
        )
    return columns


def _decision(line: int, cells: list[str], columns: dict[str, int]) -> Decision:
    def cell(column: str) -> str:
        index = columns.get(column)
        if index is None or index >= len(cells):
            return ""
        return cells[index].strip(_CELL_PADDING)

    review = cell("decision").casefold()
    if review not in {r.value for r in Review}:
        raise ReviewedNamesError(
            f"line {line}: the decision must be keep, map, or empty"
        )
    try:
        decision = ReviewedName(Review(review), cell("to") or None)
        # Checks the name as the list does, without recording it.
        ReviewedNames.empty().record(cell("roi_name"), decision)
    except ReviewedNamesError as error:
        raise ReviewedNamesError(f"line {line}: {error}") from None
    return Decision(line, cell("roi_name"), decision)


def record_decisions(
    list_path: str | os.PathLike,
    decisions_path: str | os.PathLike,
    *,
    replace: bool = False,
    protected_dirs: Iterable[str | os.PathLike] = (),
) -> Recorded:
    """Record the decisions of a CSV file in the reviewed-names list.

    Parameters
    ----------
    list_path : str or os.PathLike
        The custodian's list, which is started if it does not exist.
    decisions_path : str or os.PathLike
        The CSV file, as :func:`read_decisions` reads it.
    replace : bool, optional
        Whether a decision may replace the list's different decision on the
        same name.
    protected_dirs : iterable of str or os.PathLike, optional
        Directories the list must not be inside, as for
        :meth:`~.reviewed_roi_names.ReviewedNames.open`.

    Returns
    -------
    Recorded

    Raises
    ------
    ReviewedNamesError
        If the list cannot be kept at ``list_path``, or cannot be read or
        written; if the file cannot be read, as for :func:`read_decisions`; or
        if a decision differs from the list's and ``replace`` is false. The
        list is then as it was, and the message quotes no name or path.
    """
    created = not os.path.lexists(list_path)
    names = ReviewedNames.open(list_path, protected_dirs=protected_dirs)
    decisions = read_decisions(decisions_path)
    counts = {"new": 0, "replaced": 0, "unchanged": 0}
    conflicts = []
    for decision in decisions:
        listed = names.get(decision.name)
        if listed is None:
            counts["new"] += 1
        elif listed == decision.decision:
            counts["unchanged"] += 1
        else:
            counts["replaced"] += 1
            conflicts.append(decision.line)
    if conflicts and not replace:
        where = (
            f"line {conflicts[0]} gives a ROI Name"
            if len(conflicts) == 1
            else f"line {conflicts[0]} and {len(conflicts) - 1} more give ROI Names"
        )
        raise ReviewedNamesError(
            f"{where} a decision other than the list's; give --replace to "
            "replace the list's decisions"
        )
    for decision in decisions:
        names.record(decision.name, decision.decision, replace=True)
    try:
        names.save()
    except OSError:
        raise ReviewedNamesError(
            "the reviewed-names list could not be written; its path is not "
            "shown because it can name a person"
        ) from None
    return Recorded(created=created, listed=len(names), **counts)


def build_parser(*, stderr: TextIO | None = None) -> argparse.ArgumentParser:
    """Return the parser of the command's arguments.

    An argument error prints the usage and a fixed message to ``stderr``,
    by default :data:`sys.stderr`, and exits with :data:`EXIT_USAGE`.
    """
    parser = _Parser(
        prog="python -m pymedphys._dicom.deidentify.reviewed_names_command",
        stderr=stderr,
        description=(
            "Record the keep, map, and empty decisions of a reviewer's CSV file "
            "in the custodian's reviewed-names list, which is started if it "
            "does not exist. For use before the first supported release."
        ),
    )
    parser.add_argument(
        "list",
        metavar="LIST",
        help="the reviewed-names list, kept by the custodian with the key",
    )
    parser.add_argument(
        "decisions",
        metavar="DECISIONS",
        help="the CSV file of decisions, with columns roi_name, decision, and to",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="replace the list's decision on a name that the file decides otherwise",
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
    except ReviewedNamesError as error:
        _print(f"error: {error}; nothing was recorded", stderr)
        return EXIT_NOT_RECORDED
    _print("\n".join(recorded.summary_lines()), stdout)
    return EXIT_RECORDED


if __name__ == "__main__":
    sys.exit(main())
