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

"""Pilot a preset or option set that is not yet enabled on a local export.

Run as ``python -m pymedphys._dicom.deidentify.pilot_command SOURCE
--preset PRESET``, or with ``--option OPTION`` once for each option of a
custom option set (D-033). It is not registered with the ``pymedphys``
command: nothing de-identification related joins the public command line
before the first supported release.

The Roadmap's pilot criterion asks for a maintainer's run on a
representative local export, summarised by reason counts, under each preset
(design document, Roadmap). The run command refuses every preset and option
set until it is enabled, and one is enabled only once it is validated, so
this command runs one that is not, as the MIDI-B benchmark does: through
the whole pipeline, with the release gate, the transform's release report,
and the reference graph's second pass, under a new run-scoped key
(:func:`~pymedphys._dicom.deidentify.command.transform_for` with
``unvalidated_policy``). It takes what the run command takes for Clean
Descriptors, Clean Pixel Data, Clean Recognizable Visual Features, and
Retain Safe Private, but no project key, which a run refuses until project
keys are enabled.

The release is written to the new directory given with ``--release``, such
as one whose files are to be imported into a treatment planning system
under ``tps-import``, and the QC pack to the directory given with
``--qc-pack``, such as one to attest for a later run's face review. Without
either, the command writes it into a new temporary directory that only its
owner can read, and deletes that directory before it exits. A release of a
policy that is not enabled is for validation only.

Standard output gives only counts: of the inputs by status, of the reasons
that withheld them by type (:func:`~pymedphys._dicom.deidentify.command.summary_lines`),
and, from the run's release report, of the sequestered instances by each
reason's stage, code, and attribute tags or IOD, and of the instances held
for review by stage and code, so that the summary can be shared. It names
no source value, path, or identifier: not the release directory, the
release report's output names or labels, the QC pack's reference, or the
run's method digest. A message about a run that failed or left its staging
area names the release directory, its staging area, the QC pack, and the
temporary directory only as ``RELEASE``, ``STAGING``, ``QC-PACK``, and
``TEMPORARY``, except that a temporary directory that could not be deleted
is named in full, so that it can be deleted by hand.

Exit statuses are those of
:mod:`~pymedphys._dicom.deidentify.command`, and
:data:`~pymedphys._dicom.deidentify.command.EXIT_STAGING_LEFT` also where
the temporary directory could not be deleted.
"""

from __future__ import annotations

import argparse
import collections
import io
import json
import os
import shutil
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TextIO

from . import command, instance_transform, policy, run
from .command import _Parser, _print
from .diagnostics import RedactionCounts, redacted_diagnostics
from .keys import DeidKey
from .run_report import RELEASE_REPORT
from .safe_private import SafePrivateList
from .standard import ALL_OPTIONS

EXIT_RELEASED = command.EXIT_RELEASED
EXIT_WITHHELD = command.EXIT_WITHHELD
EXIT_USAGE = command.EXIT_USAGE
EXIT_NOT_RUN = command.EXIT_NOT_RUN
EXIT_STAGING_LEFT = command.EXIT_STAGING_LEFT
EXIT_INTERNAL_ERROR = command.EXIT_INTERNAL_ERROR

PROG = "python -m pymedphys._dicom.deidentify.pilot_command"

_ROI_NAME_OPTIONS = (
    "error: --tg263, --reviewed-names, --empty-held-roi-names, --roi-list, and "
    "--reviewed-descriptors apply only under Clean Descriptors"
)
_PIXEL_DATA_OPTIONS = (
    "error: --redaction-review and --region-rules apply only under Clean Pixel Data"
)
_FACE_REVIEW_OPTION = (
    "error: --face-review applies only under Clean Recognizable Visual Features"
)
_TEMPORARY_LEFT = (
    "error: the temporary directory {work} could not be deleted; it may hold "
    "output that still identifies people, so delete it by hand"
)
_REPORT_UNREAD = "release report: could not be read, so its reason counts are not shown"
# A sequestration reason's fields, in the order the summary gives them.
_REASON_FIELDS = ("stage", "code", "iod", "attribute", "action", "vr")


def build_parser(*, stderr: TextIO | None = None) -> argparse.ArgumentParser:
    """Return the parser of the command's arguments.

    An argument error prints the usage and a fixed message to ``stderr``,
    by default :data:`sys.stderr`, and exits with :data:`EXIT_USAGE`.
    """
    parser = _Parser(
        prog=PROG,
        stderr=stderr,
        description=(
            "De-identify the DICOM files below SOURCE under a preset or "
            "option set that need not be enabled, for a pilot, and print "
            "only counts. For use before the first supported release; a "
            "release of a policy that is not enabled is for validation only."
        ),
    )
    parser.add_argument("source", help="the directory of source files")
    parser.add_argument(
        "--release",
        metavar="DIRECTORY",
        help=(
            "the release directory to create, which must not exist; by "
            "default, one in a temporary directory that is deleted"
        ),
    )
    parser.add_argument(
        "--qc-pack",
        metavar="DIRECTORY",
        help=(
            "the confidential directory for the run's QC pack, outside the "
            "release, which must not exist or must be empty; by default, one "
            "in a temporary directory that is deleted"
        ),
    )
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument(
        "--preset",
        choices=tuple(policy.PRESETS),
        help="the preset to pilot: " + ", ".join(policy.PRESETS),
    )
    selection.add_argument(
        "--option",
        action="append",
        choices=ALL_OPTIONS,
        dest="options",
        metavar="OPTION",
        help=(
            "in place of --preset, a PS3.15 option to apply with the Basic "
            "Profile, given once for each option: " + ", ".join(ALL_OPTIONS)
        ),
    )
    _add_input_arguments(parser)
    return parser


def _add_input_arguments(parser: argparse.ArgumentParser) -> None:
    """Add what the run command takes for its options, with its meanings."""
    parser.add_argument(
        "--tg263",
        metavar="SPREADSHEET",
        help=(
            "under Clean Descriptors, a copy of the pinned TG-263 "
            "spreadsheet to read; by default, PyMedPhys's cached download"
        ),
    )
    parser.add_argument(
        "--reviewed-names",
        metavar="FILE",
        help=(
            "under Clean Descriptors, the custodian's reviewed-names list, "
            "outside SOURCE, the release, and the QC pack; by default, none"
        ),
    )
    parser.add_argument(
        "--empty-held-roi-names",
        action="store_true",
        help=(
            "under Clean Descriptors, empty each ROI Name that would be "
            "held for review, so that its instance can be released"
        ),
    )
    parser.add_argument(
        "--roi-list",
        metavar="FILE",
        help=(
            "under Clean Descriptors, an institutional list of ROI names "
            "converted by python -m pymedphys._nomenclature roi-list"
        ),
    )
    parser.add_argument(
        "--reviewed-descriptors",
        metavar="FILE",
        help=(
            "under Clean Descriptors, the custodian's reviewed descriptors "
            "list, outside SOURCE, the release, and the QC pack; by default, "
            "none"
        ),
    )
    parser.add_argument(
        "--redaction-review",
        metavar="DIRECTORY",
        help=(
            "under Clean Pixel Data, the QC pack of an earlier run of the "
            "same files under the option, attested with redaction verdicts"
        ),
    )
    parser.add_argument(
        "--region-rules",
        metavar="FILE",
        help=(
            "under Clean Pixel Data, the custodian's reviewed region rules, "
            "outside SOURCE, the release, and the QC pack"
        ),
    )
    parser.add_argument(
        "--face-review",
        metavar="DIRECTORY",
        help=(
            "under Clean Recognizable Visual Features, which needs it, the QC "
            "pack of an earlier run of the same files, attested with face "
            "verdicts"
        ),
    )
    parser.add_argument(
        "--safe-private-list",
        choices=[each.value for each in SafePrivateList],
        default=SafePrivateList.REVIEWED.value,
        help=(
            "under Retain Safe Private, the list whose rules settle private "
            "attributes: the reviewed rules (reviewed, the default) or TCIA's "
            "Private Tag Dictionary (tcia)"
        ),
    )


def pilot_lines(result: run.RunResult, redacted: RedactionCounts) -> list[str]:
    """Return the pilot's summary of a run, as counts alone.

    They are :func:`~pymedphys._dicom.deidentify.command.summary_lines`'s,
    without the release directory, then the reason counts of the release
    report that the run published: how many sequestered instances have each
    reason, each instance once for each, by the reason's stage, code, and
    IOD or attribute tags, action, and VR where it gives them, and how many
    instances were held for review by stage and code.
    """
    # The first line names the release directory.
    lines = command.summary_lines(result, redacted)[1:]
    try:
        document = json.loads(
            (result.release / RELEASE_REPORT).read_text(encoding="utf-8")
        )
        sequestered = collections.Counter(
            _reason_key(reason)
            for instance in document["sequestered"]
            for reason in instance["reasons"]
        )
        held = [
            (f"stage={each['stage']} code={each['code']}", each["count"])
            for each in document["held_for_review"]
        ]
    except (OSError, ValueError, KeyError, TypeError):
        return [*lines, _REPORT_UNREAD]
    lines.append("release report, sequestered instances by reason:")
    lines += _counted(sorted(sequestered.items()))
    lines.append("release report, instances held for review by reason:")
    lines += _counted(held)
    return lines


def _reason_key(reason: Mapping[str, object]) -> str:
    return " ".join(
        f"{field}={reason[field]}"
        for field in _REASON_FIELDS
        if reason.get(field) is not None
    )


def _counted(entries: Sequence[tuple[str, int]]) -> list[str]:
    return [f"  {name}: {count}" for name, count in entries] or ["  none"]


def _masked(text: str, places: Mapping[str, Path | None]) -> str:
    """Name each of ``places`` in ``text`` by its placeholder alone."""
    forms: dict[str, str] = {}
    for placeholder, place in places.items():
        if place is not None:
            for form in _spellings(place):
                forms.setdefault(form, placeholder)
    # The longest first, so that a directory inside another is named as
    # itself, not by its parent's placeholder and the rest of its path.
    for form in sorted(forms, key=len, reverse=True):
        text = text.replace(form, forms[form])
    return text


def _spellings(place: Path) -> set[str]:
    """Return the spellings of ``place`` that a run's messages can give.

    A run gives its directories absolute or resolved, and the QC store
    gives the QC destination with ``~`` expanded, then resolved.
    """
    spellings = set()
    for spelling in (
        place.absolute,
        place.resolve,
        lambda: place.expanduser().absolute(),
        lambda: place.expanduser().resolve(),
    ):
        try:
            spellings.add(str(spelling()))
        except (OSError, RuntimeError):  # RuntimeError: no home, or a loop
            continue
    return spellings


def _policy_name(arguments: argparse.Namespace) -> str:
    if arguments.options is None:
        return f"the {arguments.preset} preset"
    return "the custom option set " + ", ".join(sorted(set(arguments.options)))


def _usage_problem(arguments: argparse.Namespace) -> str | None:
    """Return why the options do not fit the policy, or None if they do."""
    preset, options = arguments.preset, arguments.options
    roi_name_options = (
        arguments.tg263 is not None
        or arguments.reviewed_names is not None
        or arguments.empty_held_roi_names
        or arguments.roi_list is not None
        or arguments.reviewed_descriptors is not None
    )
    if roi_name_options and not command.roi_name_options_apply(preset, options):
        return _ROI_NAME_OPTIONS
    pixel_data_options = (
        arguments.redaction_review is not None or arguments.region_rules is not None
    )
    if pixel_data_options and not command.pixel_data_options_apply(preset, options):
        return _PIXEL_DATA_OPTIONS
    if arguments.face_review is not None and not command.face_review_applies(
        preset, options
    ):
        return _FACE_REVIEW_OPTION
    return None


def _transform(
    arguments: argparse.Namespace, release: Path, qc_pack: Path
) -> instance_transform.InstanceTransform:
    """Return the pilot's transform, for a new run-scoped key."""
    return command.transform_for(
        arguments.preset,
        DeidKey.generate(),
        options=arguments.options,
        source=arguments.source,
        release=release,
        qc_pack=qc_pack,
        tg263_spreadsheet=arguments.tg263,
        reviewed_names=arguments.reviewed_names,
        empty_held_roi_names=arguments.empty_held_roi_names,
        roi_list_path=arguments.roi_list,
        reviewed_descriptors=arguments.reviewed_descriptors,
        redaction_review=arguments.redaction_review,
        region_rules=arguments.region_rules,
        safe_private_list=SafePrivateList(arguments.safe_private_list),
        face_review=arguments.face_review,
        unvalidated_policy=True,
    )


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Parse the command's arguments, and pilot the policy that they give.

    Parameters
    ----------
    argv : sequence of str, optional
        The arguments, by default ``sys.argv[1:]``.
    stdout, stderr : text file, optional
        Where to print the summary, and why the run failed or what it left
        behind. By default, :data:`sys.stdout` and :data:`sys.stderr`.

    Returns
    -------
    int
        The exit status, as the module describes.

    Raises
    ------
    SystemExit
        With :data:`EXIT_USAGE` if the arguments cannot be parsed, having
        printed the usage and a message that quotes no argument to
        ``stderr``, or 0 for ``--help``, as :mod:`argparse` does.
    """
    arguments = build_parser(stderr=stderr).parse_args(argv)
    stdout = sys.stdout if stdout is None else stdout
    stderr = sys.stderr if stderr is None else stderr
    problem = _usage_problem(arguments)
    if problem is not None:
        _print(problem, stderr)
        return EXIT_USAGE
    given_release = None if arguments.release is None else Path(arguments.release)
    given_qc_pack = None if arguments.qc_pack is None else Path(arguments.qc_pack)
    work = (
        None
        if given_release is not None and given_qc_pack is not None
        else Path(tempfile.mkdtemp(prefix="pymedphys-pilot-"))
    )
    release = given_release or Path(work, "release")
    qc_pack = given_qc_pack or Path(work, "qc")
    places = {
        "STAGING": run.staging_path(release.absolute()),
        "RELEASE": release,
        "QC-PACK": qc_pack,
        "TEMPORARY": work,
    }
    errors = io.StringIO()
    try:
        status = _pilot(arguments, release, qc_pack, stdout, errors)
    finally:
        # Deleted first, so that no failure to mask or print a message
        # leaves the temporary directory behind.
        removed = work is None or _removed(work)
        _print_errors(_masked(errors.getvalue(), places), stderr)
    if not removed:
        _print(_TEMPORARY_LEFT.format(work=work), stderr)
        return EXIT_STAGING_LEFT
    return status


def _pilot(
    arguments: argparse.Namespace,
    release: Path,
    qc_pack: Path,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    """Build the transform and run it, printing the summary and any error."""
    try:
        with redacted_diagnostics():
            transform = _transform(arguments, release, qc_pack)
    except command.TransformNotBuilt as error:
        _print(f"error: {error}", stderr)
        return EXIT_NOT_RUN
    except Exception as error:  # pylint: disable = broad-exception-caught
        _print(
            f"error: the transform could not be built, failing with "
            f"{type(error).__name__}; its details are not shown because they "
            "can contain file paths or values",
            stderr,
        )
        return EXIT_INTERNAL_ERROR
    _print(
        f"pilot of {_policy_name(arguments)}, which need not be enabled: "
        "its release is for validation only",
        stdout,
    )
    return command.deidentify_directory(
        arguments.source,
        release,
        transform=transform,
        gate=instance_transform.ReleaseGate(),
        qc_destination=qc_pack,
        reporter=transform.reporter,
        written_check=transform.written_check,
        summary=pilot_lines,
        stdout=stdout,
        stderr=stderr,
    )


def _print_errors(text: str, stream: TextIO) -> None:
    if text:
        _print(text.rstrip("\n"), stream)


def _removed(work: Path) -> bool:
    """Delete the temporary directory, and return whether it is gone."""
    shutil.rmtree(work, ignore_errors=True)
    return not os.path.lexists(work)


if __name__ == "__main__":
    sys.exit(main())
