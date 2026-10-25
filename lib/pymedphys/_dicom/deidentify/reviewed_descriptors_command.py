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

"""Record reviewers' descriptor decisions in the custodian's reviewed descriptors list.

Run as ``python -m pymedphys._dicom.deidentify.reviewed_descriptors_command
LIST DECISIONS``. It is not registered with the ``pymedphys`` command:
nothing de-identification related joins the public command line before the
first supported release.

A reviewer reads the descriptor values that a run held for review, and
writes a decision on each into a CSV file, which this command records in the
list (D-009). The file is read as the reviewed-names command reads its own
(:mod:`.reviewed_names_command`), with these columns:

- ``attribute``: the attribute, by its keyword, such as
  ``SeriesDescription``, or its tag, such as ``(0008,103E)``, which holds a
  comma, so is quoted in the file, as ``"(0008,103E)"``; or private text,
  under the Retain Safe Private Option, by its key
  (:func:`~.reviewed_descriptors.private_descriptor`), as the QC pack gives
  it, such as ``(0019,"GEMS_ACQU_01",9E) LO``, which is quoted in the file
  with each of its quotation marks doubled, as
  ``"(0019,""GEMS_ACQU_01"",9E) LO"``;
- ``value``: one value of the attribute, without padding;
- ``decision``: ``keep``, ``map``, or ``empty``;
- ``to``: for ``map``, the value to write instead; otherwise empty. The
  column may be left out of a file without a mapping.

Only the attributes that
:func:`~.reviewed_descriptors.descriptor_attributes` gives, and private
text, can be decided on.
The list is started at ``LIST`` on first use, and never inside the PyMedPhys
configuration directory or a directory given with ``--protect``. Recording is
all or nothing, as for ROI Names: a value of one attribute given different
decisions in the file is refused, as is a decision that differs from the
list's, unless ``--replace`` is given. Neither the summary nor any message
quotes a value, a cell, or the list's or the file's path.

Exit statuses are those of :mod:`.reviewed_names_command`.
"""

from __future__ import annotations

import argparse
import dataclasses
import functools
import os
import re
import sys
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import TextIO

from .command import _Parser, _print
from .reviewed_descriptors import (
    MAX_CHARACTERS,
    ReviewedDescriptor,
    ReviewedDescriptors,
    ReviewedDescriptorsError,
    descriptor_attributes,
    is_private_descriptor,
)
from .reviewed_names_command import (
    EXIT_NOT_RECORDED,
    EXIT_RECORDED,
    EXIT_USAGE,
    read_cell,
    read_columns,
    read_rows,
)
from .reviewed_roi_names import Review
from .standard import load_data_dictionary

__all__ = ["EXIT_NOT_RECORDED", "EXIT_RECORDED", "EXIT_USAGE"]

_REQUIRED = ("attribute", "value", "decision")
_COLUMNS = (*_REQUIRED, "to")
# The most characters a cell may hold: enough for the longest UC or UT value,
# but no more than a C long holds on every platform, which bounds the csv
# module's limit; a value that long would be a CSV file of 2 GiB.
FIELD_SIZE_LIMIT = min(max(MAX_CHARACTERS.values()), 2**31 - 1)
_TAG = re.compile(r"\(([0-9A-Fa-f]{4}),([0-9A-Fa-f]{4})\)")


@dataclasses.dataclass(frozen=True)
class Decision:
    """A reviewer's decision on one value, read from a line of the file.

    Its ``repr`` leaves out the value.
    """

    line: int
    tag: str
    value: str = dataclasses.field(repr=False)
    decision: ReviewedDescriptor


@dataclasses.dataclass(frozen=True)
class Recorded:
    """What :func:`record_decisions` recorded, as counts without values.

    Attributes
    ----------
    created : bool
        Whether the list was started by this call.
    new, replaced, unchanged : int
        How many distinct values of the file the list did not hold, held with
        another decision, which was replaced, or held with the same decision.
    listed : int
        How many values the list holds afterwards.
    """

    created: bool
    new: int
    replaced: int
    unchanged: int
    listed: int

    def summary_lines(self) -> list[str]:
        """Return the summary that the command prints."""
        lines = ["started a new reviewed descriptors list"] if self.created else []
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
        lines.append(f"values in the list: {self.listed}")
        return lines


@functools.cache
def _keywords() -> Mapping[str, str]:
    attributes = descriptor_attributes()
    return {
        row.keyword: row.tag
        for row in load_data_dictionary().attributes
        if row.tag in attributes
    }


def attribute_tag(text: str) -> str | None:
    """Return the tag of a descriptor attribute named by its tag or keyword, or None.

    A tag is given as ``(gggg,eeee)``, in either case; a keyword in its own
    case. Private text's key is given as
    :func:`~.reviewed_descriptors.private_descriptor` writes it, and returned
    as it is.
    """
    if is_private_descriptor(text):
        return text
    match = _TAG.fullmatch(text)
    tag = f"({match[1]},{match[2]})".upper() if match else _keywords().get(text)
    return tag if tag in descriptor_attributes() else None


def read_decisions(path: str | os.PathLike) -> tuple[Decision, ...]:
    """Read the decisions in the CSV file at ``path``, as the module describes.

    A value given the same decision on several lines is returned once, from
    its first line.

    Raises
    ------
    ReviewedDescriptorsError
        If the file cannot be read as UTF-8 CSV; if its header lacks a
        required column or repeats one; if it holds no decision; or if a row
        has more cells than the header, an attribute that is not a descriptor
        that a reviewer can decide on, a value that the list cannot hold, a
        decision other than keep, map, or empty, a value to write that does
        not fit its decision or VR, or a value given different decisions. The
        message names lines by number, never a value, a cell, or the path.
    """
    header, body = read_rows(
        path, ReviewedDescriptorsError, field_size_limit=FIELD_SIZE_LIMIT
    )
    columns = read_columns(
        header,
        _COLUMNS,
        _REQUIRED,
        ReviewedDescriptorsError(
            "the decisions file needs the columns attribute, value, and "
            "decision, and to for a mapping"
        ),
    )
    decisions: dict[tuple[str, str], Decision] = {}
    for line, cells in body:
        if len(cells) > len(header):
            raise ReviewedDescriptorsError(
                f"line {line} has more cells than the header"
            )
        decision = _decision(line, cells, columns)
        earlier = decisions.setdefault((decision.tag, decision.value), decision)
        if earlier.decision != decision.decision:
            raise ReviewedDescriptorsError(
                f"lines {earlier.line} and {line} give one value different decisions"
            )
    if not decisions:
        raise ReviewedDescriptorsError("the decisions file holds no decisions")
    return tuple(decisions.values())


def _decision(line: int, cells: list[str], columns: dict[str, int]) -> Decision:
    tag = attribute_tag(read_cell(cells, columns, "attribute"))
    if tag is None:
        raise ReviewedDescriptorsError(
            f"line {line}: the attribute is not a descriptor that Clean "
            "Descriptors cleans"
        )
    review = read_cell(cells, columns, "decision").casefold()
    if review not in {r.value for r in Review}:
        raise ReviewedDescriptorsError(
            f"line {line}: the decision must be keep, map, or empty"
        )
    value = read_cell(cells, columns, "value")
    try:
        decision = ReviewedDescriptor(
            Review(review), read_cell(cells, columns, "to") or None
        )
        # Checks the value as the list does, without recording it.
        ReviewedDescriptors.empty().record(tag, value, decision)
    except ReviewedDescriptorsError as error:
        raise ReviewedDescriptorsError(f"line {line}: {error}") from None
    return Decision(line, tag, value, decision)


def record_decisions(
    list_path: str | os.PathLike,
    decisions_path: str | os.PathLike,
    *,
    replace: bool = False,
    protected_dirs: Iterable[str | os.PathLike] = (),
) -> Recorded:
    """Record the decisions of a CSV file in the reviewed descriptors list.

    Parameters
    ----------
    list_path : str or os.PathLike
        The custodian's list, which is started if it does not exist.
    decisions_path : str or os.PathLike
        The CSV file, as :func:`read_decisions` reads it.
    replace : bool, optional
        Whether a decision may replace the list's different decision on the
        same value of the same attribute.
    protected_dirs : iterable of str or os.PathLike, optional
        Directories the list must not be inside, as for
        :meth:`~.reviewed_descriptors.ReviewedDescriptors.open`.

    Returns
    -------
    Recorded

    Raises
    ------
    ReviewedDescriptorsError
        If the list cannot be kept at ``list_path``, or cannot be read or
        written; if the file cannot be read, as for :func:`read_decisions`;
        or if a decision differs from the list's and ``replace`` is false.
        The list is then as it was, and the message quotes no value or path.
    """
    created = not os.path.lexists(list_path)
    reviewed = ReviewedDescriptors.open(list_path, protected_dirs=protected_dirs)
    decisions = read_decisions(decisions_path)
    counts = {"new": 0, "replaced": 0, "unchanged": 0}
    conflicts = []
    for decision in decisions:
        listed = reviewed.get(decision.tag, decision.value)
        if listed is None:
            counts["new"] += 1
        elif listed == decision.decision:
            counts["unchanged"] += 1
        else:
            counts["replaced"] += 1
            conflicts.append(decision.line)
    if conflicts and not replace:
        where = (
            f"line {conflicts[0]} gives a value"
            if len(conflicts) == 1
            else f"line {conflicts[0]} and {len(conflicts) - 1} more give values"
        )
        raise ReviewedDescriptorsError(
            f"{where} a decision other than the list's; give --replace to "
            "replace the list's decisions"
        )
    for decision in decisions:
        reviewed.record(decision.tag, decision.value, decision.decision, replace=True)
    try:
        reviewed.save()
    except OSError:
        raise ReviewedDescriptorsError(
            "the reviewed descriptors list could not be written; its path is "
            "not shown because it can name a person"
        ) from None
    return Recorded(created=created, listed=len(reviewed), **counts)


def build_parser(*, stderr: TextIO | None = None) -> argparse.ArgumentParser:
    """Return the parser of the command's arguments.

    An argument error prints the usage and a fixed message to ``stderr``,
    by default :data:`sys.stderr`, and exits with :data:`EXIT_USAGE`.
    """
    parser = _Parser(
        prog="python -m pymedphys._dicom.deidentify.reviewed_descriptors_command",
        stderr=stderr,
        description=(
            "Record the keep, map, and empty decisions of a reviewer's CSV file "
            "in the custodian's reviewed descriptors list, which is started if "
            "it does not exist. For use before the first supported release."
        ),
    )
    parser.add_argument(
        "list",
        metavar="LIST",
        help="the reviewed descriptors list, kept by the custodian with the key",
    )
    parser.add_argument(
        "decisions",
        metavar="DECISIONS",
        help=(
            "the CSV file of decisions, with columns attribute, value, decision, and to"
        ),
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="replace the list's decision on a value that the file decides otherwise",
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
    except ReviewedDescriptorsError as error:
        _print(f"error: {error}; nothing was recorded", stderr)
        return EXIT_NOT_RECORDED
    _print("\n".join(recorded.summary_lines()), stdout)
    return EXIT_RECORDED


if __name__ == "__main__":
    sys.exit(main())
