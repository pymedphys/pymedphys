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
POSITION`` where they saw one, each repeatable. They may confirm the face
block of any series that the pack lists in its ``eye_checks``, which the
run defaced and held because its eye ROIs disagree with the globes that its
block was found from, by the run position of its first instance there:
``--block-confirmed POSITION`` where the pack's sheet of the globes found
beside the eye ROIs shows that the globes are the patient's eyes,
repeatable; a later run given the attestation then defaces the series with
that block without holding it for its eyes. They may choose what a later
run does with any RT Dose that the pack lists in its ``dose_checks``, whose
dose in a defaced series' face block is more than the run sets to zero, by
its run position: ``--dose-as-written POSITION`` to write it as received,
to be released on a verdict of absent on its series from its own
dose-levels previews, and ``--dose-set-to-zero POSITION`` to set it to zero
in the block anyway, to be released only on a verdict on the later run's
previews of the grid as set to zero, each repeatable. They may give a face
verdict of its own on any instance that the pack lists in its
``undefaced_instances`` as shown, which lies in a defaced series' Frame of
Reference, names none, or refers to a defaced slice, and whose outline or
pixel data the run did not clean of the face, by its run position, from
its own previews, which a verdict on its series does not cover:
``--instance-face-absent POSITION`` where they saw no recognisable face in
them, and ``--instance-face-present POSITION`` where they saw one, each
repeatable. Their redaction verdicts on the instances whose Pixel Data the
Clean Pixel Data Option cleaned are read from the file that the redaction
review app (:mod:`~pymedphys._dicom.deidentify.redaction_review_app`) saved
as they worked, given as ``--redaction-verdicts``, by default the app's file
in the pack's directory: each instance accepted, revised by the regions that
they dropped and drew, or rejected, with the frames that they were shown
(D-048, D-059). The regions are drawn on the frames, never typed, so that
none can be given for another frame or with its coordinates transposed. An
instance that the file gives no verdict has none. An outcome of rejected
takes no verdict, since its verdicts would release nothing. It is not
registered with the ``pymedphys`` command: nothing de-identification related
joins the public command line before the first supported release.

``PACK`` is the directory that a run wrote its QC pack into, which holds
``qc-pack.json`` and the pack's marker. The command writes the attestation
there with :func:`~.qc_attestation.attest`, bound to the pack and its
previews by their SHA-256, and only once: a pack that has been attested, a
directory that holds no QC pack, a pack of another format, a pack whose
previews are missing or changed, an outcome of attested without all three
reviews, a face verdict on a position that begins none of the pack's series,
a series given both verdicts, a confirmed block on a position that begins
none of the pack's eye checks, or one without a sheet of its eyes, a dose
choice on a position that the pack's ``dose_checks`` does not list, an RT
Dose given both choices, an instance's own face verdict on a position that
the pack's ``undefaced_instances`` does not list, or lists as not shown, an
instance given both of its own face verdicts, a verdict, a confirmation, or
a choice with an outcome of rejected, a verdicts file for another pack, or
for this pack before it changed, a redaction verdict on a position that the
pack does not list as cleaned and previewed, a region dropped that the pack
does not list for its frame or that a region rule gave, a region drawn in a
frame that the instance does not hold or past the Rows or Columns that the
pack records for it, and an accepted or revised verdict that was not shown
every frame that its review requires are each refused, and nothing is written. The run that applies the verdicts
checks each region against its frame again, and sequesters an instance
whose region goes past it.

The release report published with the run is not changed. It records the
outcome when the run wrote it, not attested, since no reviewer had seen the
pack; the attestation is kept with the pack, where
:func:`~.qc_attestation.attestation_record` reads the reference and outcome
that a release report records (D-016).

The reviewer's name and the pack's path can identify people, so neither the
summary nor any message quotes them; the summary gives the outcome, the
reviews done, how many series have each face verdict, how many blocks were
confirmed, how many RT Doses were given each dose choice, how many
undefaced instances have each face verdict of their own, how many instances
have each redaction verdict, and each region that a revised verdict drops
or draws, by run position and frame, with the preview of that frame, and
the pack's opaque reference. A drawn region in the right frame but in the
wrong place, or a dropped region that covered text, would leave text that
the instance claims to be clean of, so the check of the summary is the
reviewer's (D-048).

Exit statuses:

- :data:`EXIT_RECORDED`, 0: the attestation was written;
- :data:`EXIT_NOT_RECORDED`, 1: nothing was written;
- :data:`EXIT_USAGE`, 2: the arguments could not be parsed, and the message
  quotes none of them.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TextIO

from . import command, redaction_verdicts
from .command import _Parser, _print
from .qc_attestation import (
    Attestation,
    Coverage,
    Face,
    Outcome,
    Redaction,
    RedactionVerdict,
    attest,
    pack_reference,
    redaction_previews,
)
from .qc_pack import QcPackError
from .reasons import DoseChoice

EXIT_RECORDED = 0
EXIT_NOT_RECORDED = 1
EXIT_USAGE = command.EXIT_USAGE

# The outcomes that a reviewer can record, by their values.
_OUTCOMES = {outcome.value: outcome for outcome in (Outcome.ATTESTED, Outcome.REJECTED)}
# The releaser's answers, by their words.
_ANSWERS = {"yes": True, "no": False}


def summary_lines(
    attestation: Attestation, previews: Mapping[tuple[int, int], str] | None = None
) -> list[str]:
    """Return the summary that the command prints, which names no one.

    It gives the pack's reference, the outcome, whether each review that
    D-017 requires was done, the releaser's confirmations, how many series
    have each face verdict, how many blocks the reviewer confirmed, how
    many RT Doses have each dose choice, how many undefaced instances have
    each face verdict of their own, how many instances have each redaction
    verdict, each region that a revised verdict drops or draws, with the
    file in the pack that previews its frame where ``previews``, by run
    position and frame, names one, and that the published release report is
    unchanged.
    """
    previews = {} if previews is None else previews
    coverage = attestation.coverage
    faces = [verdict.face for verdict in attestation.faces]
    redactions = [verdict.redaction for verdict in attestation.redactions]
    doses = [verdict.choice for verdict in attestation.dose_choices]
    own = [verdict.face for verdict in attestation.instance_faces]
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
        f"  face blocks confirmed: {len(attestation.confirmed_blocks)}",
        *(
            f"  RT Doses with dose in a face block {chosen}: {doses.count(choice)}"
            for chosen, choice in (
                ("to write as received", DoseChoice.AS_WRITTEN),
                ("to set to zero", DoseChoice.SET_TO_ZERO),
            )
        ),
        "  undefaced instances without a recognisable face in their own "
        f"previews: {own.count(Face.ABSENT)}",
        "  undefaced instances with a recognisable face in their own "
        f"previews: {own.count(Face.PRESENT)}",
        *(
            f"  cleaned instances {verdict}: {redactions.count(redaction)}"
            for verdict, redaction in (
                ("with their regions accepted", Redaction.ACCEPTED),
                ("with their regions revised", Redaction.REVISED),
                ("rejected", Redaction.REJECTED),
            )
        ),
        *(
            f"    instance {verdict.position}, frame {index}"
            + (
                f", shown in {previews[verdict.position, index]}"
                if (verdict.position, index) in previews
                else ""
            )
            + f": {action} "
            + ", ".join(
                f"[{box.top}, {box.left}, {box.bottom}, {box.right}]" for box in boxes
            )
            for verdict in attestation.redactions
            for action, regions in (
                ("drops", verdict.dropped),
                ("draws", verdict.regions),
            )
            for index, boxes in regions
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
    parser.add_argument(
        "--block-confirmed",
        action="append",
        type=int,
        default=[],
        metavar="POSITION",
        help=(
            "the globes found are the patient's eyes, in the QC pack's sheet of "
            "the eye check whose first instance is at this run position, so its "
            "face block is confirmed; repeatable"
        ),
    )
    for flag, chosen in (
        (
            "--dose-as-written",
            "write it as received, to be released on a verdict of absent on its "
            "own dose-levels previews",
        ),
        (
            "--dose-set-to-zero",
            "set it to zero in the face block anyway, to be released only on a "
            "verdict on the later run's previews of it as set to zero",
        ),
    ):
        parser.add_argument(
            flag,
            action="append",
            type=int,
            default=[],
            metavar="POSITION",
            help=(
                "for the RT Dose at this run position in the QC pack's dose "
                f"checks, a later run is to {chosen}; repeatable"
            ),
        )
    for flag, seen in (
        ("--instance-face-absent", "no recognisable face"),
        ("--instance-face-present", "a recognisable face"),
    ):
        parser.add_argument(
            flag,
            action="append",
            type=int,
            default=[],
            metavar="POSITION",
            help=(
                f"you saw {seen} in the own previews of the instance at this run "
                "position in the QC pack's undefaced instances; repeatable"
            ),
        )
    parser.add_argument(
        "--redaction-verdicts",
        nargs="?",
        const="",
        default=None,
        metavar="FILE",
        help=(
            "read your redaction verdicts on the instances that Clean Pixel "
            "Data cleaned from the file that the redaction review app saved; "
            "by default the app's file in the pack's directory"
        ),
    )
    return parser


def _redaction_verdicts(arguments: argparse.Namespace) -> list[RedactionVerdict]:
    """Return the redaction verdicts of the file that the arguments name.

    Raises
    ------
    QcPackError
        If the pack or the file cannot be read, or the file is not of its
        format or is bound to another pack. The message names no path.
    """
    if arguments.redaction_verdicts is None:
        return []
    pack = Path(arguments.pack)
    path = (
        pack / redaction_verdicts.VERDICTS_FILE
        if arguments.redaction_verdicts == ""
        else Path(arguments.redaction_verdicts)
    )
    reference, digest = pack_reference(pack)
    return list(
        redaction_verdicts.read_redaction_verdicts(
            path, reference=reference, pack_digest=digest
        ).verdicts()
    )


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
    as_written = set(arguments.dose_as_written)
    set_to_zero = set(arguments.dose_set_to_zero)
    if as_written & set_to_zero:
        _print(
            "error: an RT Dose is given both dose choices; nothing was recorded",
            stderr,
        )
        return EXIT_NOT_RECORDED
    own_absent = set(arguments.instance_face_absent)
    own_present = set(arguments.instance_face_present)
    if own_absent & own_present:
        _print(
            "error: an instance is given both face verdicts of its own; nothing "
            "was recorded",
            stderr,
        )
        return EXIT_NOT_RECORDED
    try:
        redactions = _redaction_verdicts(arguments)
        previews = redaction_previews(Path(arguments.pack))
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
            confirmed_blocks=arguments.block_confirmed,
            dose_choices={
                **dict.fromkeys(as_written, DoseChoice.AS_WRITTEN),
                **dict.fromkeys(set_to_zero, DoseChoice.SET_TO_ZERO),
            },
            instance_faces={
                **dict.fromkeys(own_absent, Face.ABSENT),
                **dict.fromkeys(own_present, Face.PRESENT),
            },
        )
    except QcPackError as error:
        # QcPackError and the OSErrors it replaces name a check, never a path.
        _print(f"error: {error}; nothing was recorded", stderr)
        return EXIT_NOT_RECORDED
    _print("\n".join(summary_lines(attestation, previews)), stdout)
    return EXIT_RECORDED


if __name__ == "__main__":
    sys.exit(main())
