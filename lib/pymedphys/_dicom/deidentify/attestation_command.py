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

"""Record a QC reviewer's attestation of a run's QC pack.

Run as ``python -m pymedphys._dicom.deidentify.attestation_command PACK
--reviewer NAME --outcome attested|rejected``, with a flag for each review
that D-017 requires and the reviewer did: ``--reviewed-retained-strings``,
``--reviewed-series``, and ``--reviewed-high-risk-instances``. The person
releasing the data may add their confirmations, each ``yes`` or ``no``:
``--intended-use-checked``, that the output was checked for its intended
use, and ``--residual-risk-accepted``, that its residual risk was accepted
under the institution's governance; either left out is recorded as not
stated. The reviewer may give a face verdict on any of the pack's series, by
the run position of its first instance: ``--face-absent POSITION`` where
they saw no recognisable face in its previews, and ``--face-present
POSITION`` where they saw one, each repeatable. Likewise, they may give a
redaction verdict on any instance whose Pixel Data the Clean Pixel Data
Option cleaned, by its run position: ``--redaction-accepted POSITION`` where
the pack's regions cover every burned-in text, ``--redaction-rejected
POSITION`` where the instance is not to be released, and
``--redaction-revised POSITION`` where their own regions are to be blacked
out instead, each given as ``--redaction-region POSITION FRAME TOP LEFT
BOTTOM RIGHT``, in pixels from the frame's top left corner with the bottom
row and right column excluded; a revised instance without a region has none
blacked out. Each is repeatable. It is not
registered with the ``pymedphys`` command: nothing de-identification related
joins the public command line before the first supported release.

``PACK`` is the directory that a run wrote its QC pack into, which holds
``qc-pack.json`` and the pack's marker. The command writes the attestation
there with :func:`~.qc_attestation.attest`, bound to the pack and its
previews by their SHA-256, and only once: a pack that has been attested, a
directory that holds no QC pack, a pack of another format, a pack whose
previews are missing or changed, an outcome of attested without all three
reviews, a face verdict on a position that begins none of the pack's series,
a series given both verdicts, a redaction verdict on a position that the
pack does not list as cleaned, an instance given more than one redaction
verdict, and a region that is empty, in a frame that the instance does not
hold, or given for an instance not revised are each refused, and nothing is
written.

The release report published with the run is not changed. It records the
outcome when the run wrote it, not attested, since no reviewer had seen the
pack; the attestation is kept with the pack, where
:func:`~.qc_attestation.attestation_record` reads the reference and outcome
that a release report records (D-016).

The reviewer's name and the pack's path can identify people, so neither the
summary nor any message quotes them; the summary gives the outcome, the
reviews done, how many series have each face verdict, how many instances
have each redaction verdict, and the pack's opaque reference.

Exit statuses:

- :data:`EXIT_RECORDED`, 0: the attestation was written;
- :data:`EXIT_NOT_RECORDED`, 1: nothing was written;
- :data:`EXIT_USAGE`, 2: the arguments could not be parsed, and the message
  quotes none of them.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

from . import command
from .command import _Parser, _print
from .qc_attestation import (
    Attestation,
    Coverage,
    Face,
    Outcome,
    Redaction,
    RedactionVerdict,
    attest,
)
from .qc_pack import QcPackError
from .text_detection import TextBox

EXIT_RECORDED = 0
EXIT_NOT_RECORDED = 1
EXIT_USAGE = command.EXIT_USAGE

# The outcomes that a reviewer can record, by their values.
_OUTCOMES = {outcome.value: outcome for outcome in (Outcome.ATTESTED, Outcome.REJECTED)}
# The releaser's answers, by their words.
_ANSWERS = {"yes": True, "no": False}


def summary_lines(attestation: Attestation) -> list[str]:
    """Return the summary that the command prints, which names no one.

    It gives the pack's reference, the outcome, whether each review that
    D-017 requires was done, the releaser's confirmations, how many series
    have each face verdict, how many instances have each redaction verdict,
    and that the published release report is unchanged.
    """
    coverage = attestation.coverage
    faces = [verdict.face for verdict in attestation.faces]
    redactions = [verdict.redaction for verdict in attestation.redactions]
    return [
        f"QC pack {attestation.reference}: {attestation.outcome.value}",
        *(
            f"  {review}: {'reviewed' if done else 'not reviewed'}"
            for review, done in (
                ("every distinct retained string", coverage.retained_strings),
                ("every series", coverage.series),
                (
                    "every instance in high-risk categories",
                    coverage.high_risk_instances,
                ),
            )
        ),
        *(
            f"  {confirmation}: {_answer(given)}"
            for confirmation, given in (
                ("checked for its intended use", attestation.intended_use_checked),
                ("residual risk accepted", attestation.residual_risk_accepted),
            )
        ),
        f"  series without a recognisable face: {faces.count(Face.ABSENT)}",
        f"  series with a recognisable face: {faces.count(Face.PRESENT)}",
        *(
            f"  cleaned instances {verdict}: {redactions.count(redaction)}"
            for verdict, redaction in (
                ("with their regions accepted", Redaction.ACCEPTED),
                ("with the reviewer's regions", Redaction.REVISED),
                ("rejected", Redaction.REJECTED),
            )
        ),
        "the release report published with the run is unchanged",
    ]


def _answer(given: bool | None) -> str:
    return "not stated" if given is None else ("yes" if given else "no")


def build_parser(*, stderr: TextIO | None = None) -> argparse.ArgumentParser:
    """Return the parser of the command's arguments.

    An argument error prints the usage and a fixed message to ``stderr``,
    by default :data:`sys.stderr`, and exits with :data:`EXIT_USAGE`.
    """
    parser = _Parser(
        prog="python -m pymedphys._dicom.deidentify.attestation_command",
        stderr=stderr,
        description=(
            "Record a QC reviewer's attestation of a run's QC pack, beside the "
            "pack, once. For use before the first supported release."
        ),
    )
    parser.add_argument(
        "pack", metavar="PACK", help="the directory that holds the run's QC pack"
    )
    parser.add_argument(
        "--reviewer",
        required=True,
        metavar="NAME",
        help="who attests, as they name themselves",
    )
    parser.add_argument(
        "--outcome",
        required=True,
        choices=tuple(_OUTCOMES),
        help=(
            "attested if the output is fit for release, which needs all three "
            "reviews; otherwise rejected"
        ),
    )
    for flag, review in (
        ("--reviewed-retained-strings", "every distinct retained string"),
        ("--reviewed-series", "every series, by its previews"),
        (
            "--reviewed-high-risk-instances",
            "every instance in high-risk categories",
        ),
    ):
        parser.add_argument(flag, action="store_true", help=f"you reviewed {review}")
    parser.add_argument(
        "--intended-use-checked",
        choices=tuple(_ANSWERS),
        help=(
            "the releaser's confirmation that the output was checked for its "
            "intended use; not stated if left out"
        ),
    )
    parser.add_argument(
        "--residual-risk-accepted",
        choices=tuple(_ANSWERS),
        help=(
            "the releaser's confirmation that the residual risk was accepted "
            "under the institution's governance; not stated if left out"
        ),
    )
    for flag, seen in (
        ("--face-absent", "no recognisable face"),
        ("--face-present", "a recognisable face"),
    ):
        parser.add_argument(
            flag,
            action="append",
            type=int,
            default=[],
            metavar="POSITION",
            help=(
                f"you saw {seen} in the previews of the series whose first "
                "instance is at this run position; repeatable"
            ),
        )
    for flag, verdict in (
        ("--redaction-accepted", "its regions cover every burned-in text"),
        ("--redaction-revised", "your regions are to be blacked out instead"),
        ("--redaction-rejected", "it is not to be released"),
    ):
        parser.add_argument(
            flag,
            action="append",
            type=int,
            default=[],
            metavar="POSITION",
            help=(
                "for the instance at this run position, whose Pixel Data Clean "
                f"Pixel Data cleaned, {verdict}; repeatable"
            ),
        )
    parser.add_argument(
        "--redaction-region",
        action="append",
        nargs=6,
        type=int,
        default=[],
        metavar=("POSITION", "FRAME", "TOP", "LEFT", "BOTTOM", "RIGHT"),
        help=(
            "a region to black out in a frame, by index from 0, of an instance "
            "given --redaction-revised, in pixels from the frame's top left "
            "corner, the bottom row and right column excluded; repeatable"
        ),
    )
    return parser


def _redaction_verdicts(arguments: argparse.Namespace) -> list[RedactionVerdict]:
    """Return the redaction verdicts that the arguments give.

    Raises
    ------
    ValueError
        If an instance is given more than one verdict, or a region is empty
        or given for an instance not revised. The message quotes no
        argument.
    """
    given = {
        Redaction.ACCEPTED: arguments.redaction_accepted,
        Redaction.REVISED: arguments.redaction_revised,
        Redaction.REJECTED: arguments.redaction_rejected,
    }
    positions = [position for each in given.values() for position in each]
    if len(positions) != len(set(positions)):
        raise ValueError("an instance is given more than one redaction verdict")
    regions: dict[int, dict[int, set[TextBox]]] = {
        position: {} for position in given[Redaction.REVISED]
    }
    for position, frame, *box in arguments.redaction_region:
        if position not in regions:
            raise ValueError("a region is given for an instance that is not revised")
        if frame < 0:
            raise ValueError("a region is given in a frame before the first")
        try:
            regions[position].setdefault(frame, set()).add(TextBox(*box))
        except ValueError:
            raise ValueError("a region has no rows or no columns") from None
    return [
        RedactionVerdict(
            position,
            redaction,
            (
                tuple(
                    (frame, tuple(sorted(boxes)))
                    for frame, boxes in sorted(regions[position].items())
                )
                if redaction is Redaction.REVISED
                else ()
            ),
        )
        for redaction, each in given.items()
        for position in each
    ]


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Parse the arguments, write the attestation, and print a summary.

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
    absent, present = set(arguments.face_absent), set(arguments.face_present)
    if absent & present:
        _print(
            "error: a series is given both face verdicts; nothing was recorded",
            stderr,
        )
        return EXIT_NOT_RECORDED
    try:
        redactions = _redaction_verdicts(arguments)
    except ValueError as error:
        _print(f"error: {error}; nothing was recorded", stderr)
        return EXIT_NOT_RECORDED
    try:
        attestation = attest(
            Path(arguments.pack),
            reviewer=arguments.reviewer,
            outcome=_OUTCOMES[arguments.outcome],
            coverage=Coverage(
                retained_strings=arguments.reviewed_retained_strings,
                series=arguments.reviewed_series,
                high_risk_instances=arguments.reviewed_high_risk_instances,
            ),
            intended_use_checked=_ANSWERS.get(arguments.intended_use_checked),
            residual_risk_accepted=_ANSWERS.get(arguments.residual_risk_accepted),
            faces={
                **{series: Face.ABSENT for series in absent},
                **{series: Face.PRESENT for series in present},
            },
            redactions=redactions,
        )
    except QcPackError as error:
        # QcPackError and the OSErrors it replaces name a check, never a path.
        _print(f"error: {error}; nothing was recorded", stderr)
        return EXIT_NOT_RECORDED
    _print("\n".join(summary_lines(attestation)), stdout)
    return EXIT_RECORDED


if __name__ == "__main__":
    sys.exit(main())
