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
``--reviewed-series``, and ``--reviewed-high-risk-instances``. It is not
registered with the ``pymedphys`` command: nothing de-identification related
joins the public command line before the first supported release.

``PACK`` is the directory that a run wrote its QC pack into, which holds
``qc-pack.json`` and the pack's marker. The command writes the attestation
there with :func:`~.qc_attestation.attest`, bound to the pack and its
previews by their SHA-256, and only once: a pack that has been attested, a
directory that holds no QC pack, a pack of another format, a pack whose
previews are missing or changed, and an outcome of attested without all
three reviews are each refused, and nothing is written.

The release report published with the run is not changed. It records the
outcome when the run wrote it, not attested, since no reviewer had seen the
pack; the attestation is kept with the pack, where
:func:`~.qc_attestation.attestation_record` reads the reference and outcome
that a release report records (D-016).

The reviewer's name and the pack's path can identify people, so neither the
summary nor any message quotes them; the summary gives the outcome, the
reviews done, and the pack's opaque reference.

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
from .qc_attestation import Attestation, Coverage, Outcome, attest
from .qc_pack import QcPackError

EXIT_RECORDED = 0
EXIT_NOT_RECORDED = 1
EXIT_USAGE = command.EXIT_USAGE

# The outcomes that a reviewer can record, by their values.
_OUTCOMES = {outcome.value: outcome for outcome in (Outcome.ATTESTED, Outcome.REJECTED)}


def summary_lines(attestation: Attestation) -> list[str]:
    """Return the summary that the command prints, which names no one.

    It gives the pack's reference, the outcome, whether each review that
    D-017 requires was done, and that the published release report is
    unchanged.
    """
    coverage = attestation.coverage
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
        "the release report published with the run is unchanged",
    ]


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
    return parser


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
        )
    except QcPackError as error:
        # QcPackError and the OSErrors it replaces name a check, never a path.
        _print(f"error: {error}; nothing was recorded", stderr)
        return EXIT_NOT_RECORDED
    _print("\n".join(summary_lines(attestation)), stdout)
    return EXIT_RECORDED


if __name__ == "__main__":
    sys.exit(main())
