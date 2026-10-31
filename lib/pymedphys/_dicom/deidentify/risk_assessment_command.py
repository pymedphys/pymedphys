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

"""Record an external statistical risk assessment beside a run's QC pack.

Run as ``python -m pymedphys._dicom.deidentify.risk_assessment_command PACK
REPORT STATEMENT``, or with ``--check`` to make every check and record
nothing. It is not registered with the ``pymedphys`` command: nothing
de-identification related joins the public command line before the first
supported release, which publishes it as ``pymedphys dicom
deidentify-assess``, as the maintainer decided on 31 October 2026.

``PACK`` is the directory that a run wrote its QC pack into, ``REPORT`` the
``release-report.json`` that the same run published, which names the pack
by its reference, and ``STATEMENT`` a file of what the assessor states of
their assessment of that run's collection. The command records it with
:func:`~.risk_assessment.record_assessment`, which binds it to the pack, the
collection, the policy, and the reviewed lists and region rules that the
run applied, and writes it beside the pack, once (D-053). Each refusal that
:func:`~.risk_assessment.record_assessment` makes is the command's too, and
nothing is written: a directory that holds no QC pack, a pack of another
format, a pack that records no digest of the reviewed lists, or no source
file, a release report that cannot be read, is not of its format, or names
another pack, and a pack that already has a risk assessment. A record is
never overwritten, so ``--check`` lets the assessor find any of these, and
any fault of the statement, before recording.

The statement is a UTF-8 JSON object, with or without a byte order mark,
labelled with its format, :data:`STATEMENT_FORMAT`, whose members are those
of :class:`~.risk_assessment.Assessment`, each required, and no other, as
D-017 requires the assessment to state:

- ``format``: :data:`STATEMENT_FORMAT`;
- ``model``: an object of ``name``, ``version``, ``implementation``, and
  ``implementation_version``, each text: the model that estimated the risk,
  and the software that computed it, each with its version;
- ``attacker``: an object of ``knowledge``, text, what the attacker is
  assumed to know and from which sources, and ``membership_known``, true or
  false, whether they are assumed to know who is in the collection;
- ``population``: an object of ``reference`` and ``sampling``, each text,
  the reference population and how the collection was sampled from it; or
  of ``in_cohort``, text, why the assessment is within the release cohort;
  never both, and the form not taken may be left out or given as null;
- ``matching_variables``: an array of text, at least one, each once,
  ignoring case and surrounding spaces, including any derived from the
  pixel data;
- ``pixel_derived``: text, how characteristics that can be derived from the
  pixel data, such as body habitus or implants, were considered;
- ``generalisation``, ``missing_data``, ``uncertainty``, and
  ``exclusions``: text, how values were generalised, how missing data were
  handled, the uncertainty of the estimate, and what was excluded and why;
- ``linked_records`` and ``earlier_releases``: text, how linked
  longitudinal records, and earlier releases that can be linked to this
  one, were accounted for;
- ``device_identity``: text, whether keeping machine identity, such as
  Station Name and Device Serial Number, would raise the risk above the
  threshold;
- ``institutional_identity``: text, how the residual risk of the
  institutional identity that the policy keeps, such as the codes of local
  coding schemes, was assessed, and whether the assessment supports keeping
  it;
- ``facial_reconstruction``: true or false, whether re-identification from
  faces reconstructed from the images was among the channels assessed;
- ``subjects``: a whole number of at least 1, the distinct subjects
  assessed, not images, frames, or visits;
- ``threshold``: 0.09, or 0.05 for a more sensitive collection;
- ``maximum_risk``: a number from 0 to 1, the maximum per-subject
  re-identification probability;
- ``assessor``: text, who assessed it, as they name themselves;
- ``assessed_at``: when, as an ISO 8601 date and time with its UTC offset,
  such as ``2026-10-23T09:30:00Z`` or ``2026-10-23T20:30:00+11:00``, not in
  the future; it is recorded in UTC.

Text is a JSON string that is not empty or only spaces. A member named
twice, a number that is not finite, and a member that the format does not
define are refused, as is a statement whose format is another's, such as a
record's: a record cannot be given again for another pack. The engine
checks that each statement is given, not that it is adequate, which is the
assessor's responsibility. For example::

    {
      "format": "pymedphys-deid-risk-statement/1",
      "model": {
        "name": "Population uniqueness",
        "version": "2",
        "implementation": "An estimator of the assessor's choosing",
        "implementation_version": "1.4.0"
      },
      "attacker": {
        "knowledge": "Public registries and news reports",
        "membership_known": true
      },
      "population": {"in_cohort": "Every subject assessed is in the release"},
      "matching_variables": ["sex", "age at study", "body habitus from images"],
      "pixel_derived": "Body habitus and implants were matched on",
      "generalisation": "Ages in 5-year bands",
      "missing_data": "Missing values match any value",
      "uncertainty": "95% interval from 1,000 bootstrap samples",
      "exclusions": "None",
      "linked_records": "Each subject's studies were assessed together",
      "earlier_releases": "No earlier release",
      "device_identity": "Not kept; keeping it was not assessed",
      "institutional_identity": "Local codes were matched on as the site",
      "facial_reconstruction": false,
      "subjects": 3,
      "threshold": 0.09,
      "maximum_risk": 0.04,
      "assessor": "The assessor's name",
      "assessed_at": "2026-10-23T09:30:00Z"
    }

The statement and the record can describe the cohort, and name the
assessor, so they are confidential, as the QC pack is (D-016): the record is
written owner-only beside the pack, and the statement, which the command
neither moves nor removes, is kept or disposed of as the pack is, never with
the release. The release report published with the run is not changed; a
later ``public-release`` run given the pack checks the record in its
statistical gate (D-017). Neither the summary nor any message quotes a
statement, a member that the format does not define, or a path: the
summary gives the record's opaque reference and the pack's, how many
distinct subjects and matching variables were assessed, the threshold,
whether the maximum probability is within it, and whether faces were
assessed.

Exit statuses:

- :data:`EXIT_RECORDED`, 0: the assessment was recorded, or, with
  ``--check``, would be;
- :data:`EXIT_NOT_RECORDED`, 1: nothing was recorded, and with ``--check``
  recording would refuse it;
- :data:`EXIT_USAGE`, 2: the arguments could not be parsed, and the message
  quotes none of them.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TextIO

from . import command, qc_store
from .command import _Parser, _print
from .qc_pack import QcPackError
from .risk_assessment import (
    Assessment,
    AssessmentRecord,
    Attacker,
    Model,
    Population,
    RiskAssessmentError,
    bind_assessment,
    record_assessment,
)

EXIT_RECORDED = 0
EXIT_NOT_RECORDED = 1
EXIT_USAGE = command.EXIT_USAGE

# The format of a statement. A change to its members takes a new label.
STATEMENT_FORMAT = "pymedphys-deid-risk-statement/1"
# The members of a statement, in the order of the Assessment's fields.
MEMBERS = (
    "format",
    "model",
    "attacker",
    "population",
    "matching_variables",
    "pixel_derived",
    "generalisation",
    "missing_data",
    "uncertainty",
    "exclusions",
    "linked_records",
    "earlier_releases",
    "device_identity",
    "institutional_identity",
    "facial_reconstruction",
    "subjects",
    "threshold",
    "maximum_risk",
    "assessor",
    "assessed_at",
)
# The members of each section, by the section's member.
SECTIONS: Mapping[str, tuple[str, ...]] = {
    "model": ("name", "version", "implementation", "implementation_version"),
    "attacker": ("knowledge", "membership_known"),
    "population": ("reference", "sampling", "in_cohort"),
}
# The members of a statement given to the Assessment as they are read, which
# it checks: every one but the format, the sections, the matching variables,
# and the time, which are read first.
_AS_READ = tuple(
    member
    for member in MEMBERS
    if member not in {"format", *SECTIONS, "matching_variables", "assessed_at"}
)


def read_statement(path: os.PathLike | str) -> Assessment:
    """Read an assessor's statement from the file at ``path``.

    Returns
    -------
    ~pymedphys._dicom.deidentify.risk_assessment.Assessment

    Raises
    ------
    RiskAssessmentError
        If the file is not UTF-8 JSON, names a member twice, holds a number
        that is not finite, or is not a statement, as :func:`assessment_of`
        raises. The message names a member, never a value or the path.
    QcPackError
        If the file cannot be read, giving the operating system's reason
        but not the path.
    """
    try:
        content = Path(path).read_bytes()
    except OSError as error:
        raise qc_store.os_error("the statement could not be read", error) from None
    try:
        document = json.loads(
            content.decode("utf-8-sig"),
            object_pairs_hook=_unique_members,
            parse_constant=_not_finite,
        )
    except RiskAssessmentError:
        raise
    # UnicodeError and JSONDecodeError are ValueErrors; a document nested
    # too deeply for the parser raises RecursionError.
    except (ValueError, RecursionError):
        raise RiskAssessmentError("the statement is not UTF-8 JSON") from None
    return assessment_of(document)


def _unique_members(pairs: list[tuple[str, object]]) -> dict[str, object]:
    document = dict(pairs)
    if len(document) != len(pairs):
        raise RiskAssessmentError("the statement names a member twice")
    return document


def _not_finite(_constant: str) -> object:
    raise RiskAssessmentError("the statement holds a number that is not finite")


def assessment_of(document: object) -> Assessment:
    """Return the assessment that a statement's JSON values state.

    Parameters
    ----------
    document : object
        The statement, as :func:`json.loads` gives it, which is not changed.

    Returns
    -------
    ~pymedphys._dicom.deidentify.risk_assessment.Assessment

    Raises
    ------
    RiskAssessmentError
        If the document is not an object labelled :data:`STATEMENT_FORMAT`;
        if it, or its model, attacker, or population, lacks a member or has
        one that the format does not define; if a section is not an object;
        if ``assessed_at`` is not a date and time with its UTC offset; or if
        the Assessment refuses what it states. The message names members,
        never a value or a member that the format does not define.
    """
    if not isinstance(document, dict) or document.get("format") != STATEMENT_FORMAT:
        raise RiskAssessmentError(
            f"the statement is not of its format, {STATEMENT_FORMAT}"
        )
    _check_members("the statement", document, MEMBERS, MEMBERS)
    sections = {}
    for name, members in SECTIONS.items():
        section = document[name]
        what = f"the statement's {name}"
        if not isinstance(section, dict):
            raise RiskAssessmentError(f"{what} is not a JSON object")
        # Either form of the population may be left out; the Population
        # checks that one is given.
        _check_members(what, section, members, () if name == "population" else members)
        sections[name] = section
    variables = document["matching_variables"]
    return Assessment(
        model=Model(**sections["model"]),
        attacker=Attacker(**sections["attacker"]),
        population=Population(**sections["population"]),
        # Only an array is read as a tuple; anything else is given as it
        # is, for the Assessment to refuse, since a string would read as a
        # tuple of its characters.
        matching_variables=tuple(variables)
        if isinstance(variables, list)
        else variables,
        assessed_at=_utc(document["assessed_at"]),
        **{name: document[name] for name in _AS_READ},
    )


def _check_members(
    what: str,
    document: Mapping[str, object],
    members: Sequence[str],
    required: Sequence[str],
) -> None:
    missing = [member for member in required if member not in document]
    if missing:
        listed = (
            missing[0]
            if len(missing) == 1
            else ", ".join(missing[:-1]) + f", and {missing[-1]}"
        )
        plural = "member" if len(missing) == 1 else "members"
        raise RiskAssessmentError(f"{what} needs its {plural} {listed}")
    undefined = sum(1 for member in document if member not in members)
    if undefined:
        plural = "member" if undefined == 1 else "members"
        raise RiskAssessmentError(
            f"{what} has {undefined} {plural} that its format does not define"
        )


def _utc(value: object) -> datetime.datetime:
    """Return the time that a statement gives, in UTC."""
    error = RiskAssessmentError(
        "the statement needs its assessed_at as an ISO 8601 date and time with "
        "its UTC offset, such as 2026-10-23T09:30:00Z"
    )
    if not isinstance(value, str):
        raise error
    try:
        when = datetime.datetime.fromisoformat(value)
    except ValueError:
        raise error from None
    if when.utcoffset() is None:
        raise error
    try:
        return when.astimezone(datetime.timezone.utc)
    except OverflowError:  # such as midnight on 1 January 1 at UTC+01:00
        raise RiskAssessmentError(
            "the statement's assessed_at is outside the years 1 to 9999 in UTC"
        ) from None


def summary_lines(record: AssessmentRecord, *, recorded: bool = True) -> list[str]:
    """Return the summary that the command prints, which quotes no statement.

    It gives the record's reference, or, where nothing was ``recorded``, as
    with ``--check``, says so without one, since a record written later has
    a reference of its own; then the pack's reference, how many distinct
    subjects and matching variables were assessed, the threshold, whether
    the maximum per-subject probability is within it, whether faces
    reconstructed from the images were assessed, and that the published
    release report is unchanged.
    """
    assessment = record.assessment
    return [
        (
            f"risk assessment {record.reference}: recorded beside QC pack {record.pack}"
            if recorded
            else f"risk assessment checked against QC pack {record.pack}; nothing "
            "was recorded"
        ),
        f"  distinct subjects assessed: {assessment.subjects}",
        f"  matching variables: {len(assessment.matching_variables)}",
        f"  threshold: {assessment.threshold}",
        "  maximum per-subject probability: "
        + (
            "within the threshold"
            if assessment.within_threshold
            else "above the threshold, so the statistical gate fails"
        ),
        "  faces reconstructed from the images: "
        + ("assessed" if assessment.facial_reconstruction else "not assessed"),
        "the release report published with the run is unchanged",
    ]


# The members of a statement, as the help lists them.
_DESCRIBED = {
    "format": f"format ({STATEMENT_FORMAT})",
    "population": "population (reference and sampling, or in_cohort)",
    "assessed_at": (
        "assessed_at (an ISO 8601 date and time with its UTC offset, such as "
        "2026-10-23T09:30:00Z)"
    ),
}
_EPILOG = (
    "The statement's members, each required: "
    + ", ".join(
        _DESCRIBED.get(
            member,
            f"{member} ({', '.join(SECTIONS[member])})"
            if member in SECTIONS
            else member,
        )
        for member in MEMBERS
    )
    + "."
)


def build_parser(*, stderr: TextIO | None = None) -> argparse.ArgumentParser:
    """Return the parser of the command's arguments.

    An argument error prints the usage and a fixed message to ``stderr``,
    by default :data:`sys.stderr`, and exits with :data:`EXIT_USAGE`.
    """
    parser = _Parser(
        prog="python -m pymedphys._dicom.deidentify.risk_assessment_command",
        stderr=stderr,
        description=(
            "Record an external statistical risk assessment of a run's "
            "collection beside the run's QC pack, once, from the assessor's "
            f"statement, a JSON object labelled {STATEMENT_FORMAT}. For use "
            "before the first supported release, which makes it pymedphys "
            "dicom deidentify-assess."
        ),
        epilog=_EPILOG,
    )
    parser.add_argument(
        "pack", metavar="PACK", help="the directory that holds the run's QC pack"
    )
    parser.add_argument(
        "report",
        metavar="REPORT",
        help="the release-report.json that the same run published",
    )
    parser.add_argument(
        "statement",
        metavar="STATEMENT",
        help=(
            "the assessor's statement, a UTF-8 JSON object of the members listed below"
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "make every check that recording makes, print the summary, and "
            "record nothing"
        ),
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Parse the arguments, record the assessment, and print a summary.

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
    bind = bind_assessment if arguments.check else record_assessment
    try:
        assessment = read_statement(Path(arguments.statement))
        record = bind(Path(arguments.pack), Path(arguments.report), assessment)
    except QcPackError as error:
        # RiskAssessmentError is a QcPackError, and neither, nor the
        # OSErrors that they replace, names a value or a path.
        _print(f"error: {error}; nothing was recorded", stderr)
        return EXIT_NOT_RECORDED
    _print("\n".join(summary_lines(record, recorded=not arguments.check)), stdout)
    return EXIT_RECORDED


if __name__ == "__main__":
    sys.exit(main())
