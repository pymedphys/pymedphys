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

# pylint: disable = too-many-lines
# One module parses, loads, and reports every argument of a run, so it is long.

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
:func:`main` parses the source and release directories, the QC
destination, the preset or custom option set (D-033), under Clean
Descriptors what ROI Names and free-text descriptors are cleaned with, and,
under Clean Pixel Data, the attested QC pack whose redaction verdicts apply
and the custodian's region rules, and, under Clean Recognizable Visual
Features, the attested QC pack whose face verdicts apply, from the command
line's arguments. It builds the policy's transform for a new run-scoped key
with :func:`build_transform`, with the text detector under Clean Pixel Data,
and runs it with the release gate, the transform's release report, and the
reference graph's second pass under its key, for the ``pymedphys`` command
to call once the engine is public; nothing registers it yet. No preset or
option is enabled yet, so until one is, the command refuses to run.

The summary and every message name inputs only by count, reasons only by
their type and the names of enum members (their own, or those of a
dataclass reason's fields), and directories only where the caller chose
them: the release directory, its staging area, and the QC destination. A
failure that the run does not expect is reported by its exception's type
alone, since its message could quote a value.

Exit statuses:

- :data:`EXIT_RELEASED`, 0: every input was released, or is an identical
  copy of one that was;
- :data:`EXIT_WITHHELD`, 1: the release was published, but at least one
  input was refused, sequestered, or held for review;
- :data:`EXIT_USAGE`, 2: the arguments could not be parsed, as for any
  :mod:`argparse` command, though the message quotes none of them, or
  they give ROI name or descriptor options without Clean Descriptors, a
  redaction review or region rules without Clean Pixel Data, or a face
  review without Clean Recognizable Visual Features;
- :data:`EXIT_NOT_RUN`, 3: the run could not start, because its preset or
  option set is not enabled, it has no face review under Clean
  Recognizable Visual Features, or what it cleans ROI Names or descriptors
  with, its text detector, redaction review, region rules, or face review,
  or its project key or profile store, cannot be used, among other
  reasons, the first pass stopped it, or its QC pack or profile store could
  not be written, and nothing was published;
- :data:`EXIT_STAGING_LEFT`, 4: the staging area could not be deleted, and
  may hold output that still identifies people, whatever else happened;
- :data:`EXIT_INTERNAL_ERROR`, 70: anything else failed, and nothing was
  published (``EX_SOFTWARE`` of BSD's ``sysexits.h``).
"""

from __future__ import annotations

import argparse
import collections
import dataclasses
import enum
import os
import sys
from collections.abc import Callable, Collection, Sequence
from pathlib import Path
from typing import NoReturn, TextIO

from pymedphys._nomenclature import roi_list, tg263, tg263_published

from . import instance_transform, keys, policy, run, run_report
from .descriptor_cleaning import CLEAN_DESCRIPTORS, DescriptorCleaning
from .diagnostics import RedactionCounts, redacted_diagnostics
from .face_review import FaceReview, read_face_review
from .keys import DeidKey, DeidKeyError, custodian_location_problem, read_key_file
from .pixel_cleaning import TextFinder
from .pixel_region_rules import PixelRegionRules, PixelRegionRulesError
from .policy import CLEAN_PIXEL_DATA
from .profiles import ProfileError, ProfileStore
from .qc_pack import QcPackError
from .redaction_review import RedactionReview, read_redaction_review
from .reviewed_descriptors import ReviewedDescriptors, ReviewedDescriptorsError
from .reviewed_roi_names import ReviewedNames, ReviewedNamesError
from .safe_private import SafePrivateList
from .standard import ALL_OPTIONS
from .text_detection import TextDetectionError, TextDetector

EXIT_RELEASED = 0
EXIT_WITHHELD = 1
EXIT_USAGE = 2
EXIT_NOT_RUN = 3
EXIT_STAGING_LEFT = 4
EXIT_INTERNAL_ERROR = 70

_RELEASED = (run.Status.RELEASED, run.Status.DUPLICATE)
# The presets that the command takes: every preset, each refused until it is
# enabled (design document, Scope).
_PRESETS = tuple(policy.PRESETS)
# What each preset is for, as the command's help gives it.
_PRESET_USES = {
    "basic": "the Basic Profile alone, the default",
    "basic-clean-descriptors": "with Clean Descriptors",
    "tps-import": "for copies in non-clinical treatment planning systems",
    "public-release": "for collections being assessed for public sharing",
}
_ROI_NAME_OPTIONS = (
    "error: --tg263, --reviewed-names, --empty-held-roi-names, --roi-list, and "
    "--reviewed-descriptors apply only under Clean Descriptors: with --preset "
    + ", ".join(
        preset
        for preset, options in policy.PRESETS.items()
        if CLEAN_DESCRIPTORS in options
    )
    + ", or --option clean_descriptors"
)
_TG263_UNLOADED = (
    "the TG-263 edition could not be loaded; its details are not "
    "shown because they can contain file paths"
)
_REVIEWED_MISSING = (
    "the reviewed-names list does not exist; its path is not shown "
    "because it can name a person"
)
_ROI_LIST_UNUSABLE = (
    "the institutional list of ROI names could not be used; its "
    "details are not shown because they can contain file paths or ROI names"
)
_REVIEWED_UNUSABLE = (
    "the reviewed-names list could not be used; its details are not "
    "shown because they can contain file paths or ROI names"
)
_DESCRIPTORS_MISSING = (
    "the reviewed descriptors list does not exist; its path is not shown "
    "because it can name a person"
)
_DESCRIPTORS_UNUSABLE = (
    "the reviewed descriptors list could not be used; its details are not "
    "shown because they can contain file paths or descriptor values"
)
_PIXEL_DATA_OPTIONS = (
    "error: --redaction-review and --region-rules apply only under Clean Pixel "
    "Data: with --option clean_pixel_data"
)
_DETECTOR_UNMADE = "the text detector could not be made: {error}"
_MODEL_UNREAD = (
    "the text detector's model could not be downloaded or read; its details "
    "are not shown because they can contain file paths"
)
_REVIEW_UNREAD = "the redaction review could not be read: {error}"
_REVIEW_UNOPENED = (
    "the redaction review could not be read; its details are not shown "
    "because they can contain file paths"
)
_RULES_MISSING = (
    "the region rules do not exist; their path is not shown because it can "
    "name a person"
)
_RULES_UNUSABLE = (
    "the region rules could not be used; their details are not shown "
    "because they can contain file paths or equipment names"
)
_PROJECT_KEY_HALF = (
    "a project key's key file and profile store are given together, or neither"
)
_PROJECT_KEYS_NOT_ENABLED = (
    "project keys are not enabled: until they are, each run has a run-scoped key"
)
_KEY_FILE_UNUSABLE = (
    "the key file could not be used; its path is not shown, and nothing of the key is"
)
_PROFILES_UNUSABLE = (
    "the profile store could not be used; its details are not shown because "
    "they can contain file paths"
)
_PROFILES_UNSAVED = (
    "the profile store could not be saved, so nothing was published; its "
    "details are not shown because they can contain file paths"
)
_FACE_REVIEW_NEEDED = (
    "a run under Clean Recognizable Visual Features needs a face review: the QC "
    "pack of an earlier run of the same files, attested with face verdicts"
)
_FACE_REVIEW_OPTION = (
    "error: --face-review applies only under Clean Recognizable Visual "
    "Features: with --option clean_recognizable_visual_features"
)
_FACE_REVIEW_UNREAD = "the face review could not be read: {error}"
_FACE_REVIEW_UNOPENED = (
    "the face review could not be read; its details are not shown because "
    "they can contain file paths"
)


def deidentify_directory(
    source: str | os.PathLike[str],
    release: str | os.PathLike[str],
    *,
    transform: run.Transform,
    gate: run.Gate,
    qc_destination: str | os.PathLike[str],
    reporter: run_report.Reporter | None = None,
    written_check: run.WrittenCheck | None = None,
    before_publish: Callable[[], object] | None = None,
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
    qc_destination : str or os.PathLike
        Where the run writes its confidential QC pack, as
        :func:`~pymedphys._dicom.deidentify.run.run` takes it.
    reporter : Reporter, optional
        The run's release report, as
        :func:`~pymedphys._dicom.deidentify.run.run` takes it, such as an
        :class:`~pymedphys._dicom.deidentify.instance_transform.InstanceTransform`'s
        ``reporter``. Without one, the release has no report or conformance
        statement.
    written_check : WrittenCheck, optional
        The reference graph's second pass, as
        :func:`~pymedphys._dicom.deidentify.run.run` takes it, such as an
        :class:`~pymedphys._dicom.deidentify.instance_transform.InstanceTransform`'s
        ``written_check``. Without one, what was written is not checked.
    before_publish : callable, optional
        As :func:`~pymedphys._dicom.deidentify.run.run` takes it, such as
        :func:`profile_saver`'s, which raises a
        :class:`~pymedphys._dicom.deidentify.profiles.ProfileError` that
        names nothing if the store cannot be saved.
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
    staging = run.staging_path(Path(release).absolute())
    # One that is already there is an earlier run's, which run refuses.
    earlier_staging = os.path.lexists(staging)
    with redacted_diagnostics() as counts:
        try:
            result = run.run(
                run.discover(source),
                release,
                transform,
                gate,
                qc_destination=qc_destination,
                reporter=reporter,
                written_check=written_check,
                before_publish=before_publish,
            )
        except (run.RunError, run.RunStopped, QcPackError, ProfileError) as error:
            # Each names only the caller's directories, counts, or the
            # check of the QC destination that failed.
            _print(f"error: {error}", stderr)
            return _left_behind(staging, earlier_staging, stderr) or EXIT_NOT_RUN
        except Exception as error:  # pylint: disable = broad-exception-caught
            _print(
                f"error: the run failed with {type(error).__name__}, and "
                "nothing was published; its details are not shown because "
                "they can contain file paths or DICOM values",
                stderr,
            )
            return _left_behind(staging, earlier_staging, stderr) or EXIT_INTERNAL_ERROR
    # The warning comes first, so that nothing printed after it can lose it.
    if not result.staging_removed:
        _print(_STAGING_LEFT.format(staging=staging), stderr)
    _print("\n".join(summary_lines(result, counts)), stdout)
    return exit_status(result)


_STAGING_LEFT = (
    "error: the staging area {staging} could not be deleted; it may hold "
    "output that still identifies people, so delete it by hand"
)


def _left_behind(staging: Path, earlier: bool, stderr: TextIO) -> int:
    """Return EXIT_STAGING_LEFT, having said so, if a failed run left its staging area."""
    if earlier or not os.path.lexists(staging):
        return 0
    _print(_STAGING_LEFT.format(staging=staging), stderr)
    return EXIT_STAGING_LEFT


def _print(text: str, stream: TextIO) -> None:
    # A directory's name can hold characters that the stream cannot
    # encode, such as on a Windows console, or undecodable bytes from the
    # command line; they are escaped rather than failing after a release.
    encoding = getattr(stream, "encoding", None) or "utf-8"
    print(text.encode(encoding, "backslashreplace").decode(encoding), file=stream)


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
    first-pass findings, and second-pass findings of what was written, there
    were of each kind; and, if any were, how many warnings and log records
    were redacted.
    """
    statuses = collections.Counter(outcome.status for outcome in result.outcomes)
    # Each input counts once for each type of reason it has, and reasons
    # need not be hashable.
    reasons = collections.Counter(
        name
        for outcome in result.outcomes
        for name in {_reason_name(reason) for reason in outcome.reasons}
    )
    findings = collections.Counter(
        _reason_name(finding.kind) for finding in result.findings
    )
    written = collections.Counter(
        _reason_name(finding.kind) for finding in result.written_findings
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
    if written:
        lines.append("second-pass findings:")
        lines += [f"  {name}: {count}" for name, count in sorted(written.items())]
    if redacted.warnings or redacted.log_records:
        lines.append(
            f"redacted diagnostics: {redacted.warnings} warnings, "
            f"{redacted.log_records} log records"
        )
    return lines


def _reason_name(reason: object) -> str:
    # A reason's fields could hold anything a transform or gate put there,
    # so only enum members' names, which the code defines, are shown: the
    # reason's own, or those of a dataclass reason's fields, such as a
    # release gate's decision and code.
    if isinstance(reason, enum.Enum):
        return _member(reason)
    name = type(reason).__name__
    if dataclasses.is_dataclass(reason) and not isinstance(reason, type):
        members = [
            f"{field.name}={_member(value)}"
            for field in dataclasses.fields(reason)
            if isinstance(value := getattr(reason, field.name, None), enum.Enum)
        ]
        if members:
            return f"{name}({', '.join(members)})"
    return name


def _member(member: enum.Enum) -> str:
    return f"{type(member).__name__}.{member.name}"


class _Parser(argparse.ArgumentParser):
    """A parser whose errors quote no argument.

    argparse repeats an unexpected argument in its error message, and an
    argument can be a source path.
    """

    def __init__(self, *args, stderr: TextIO | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.stderr = stderr

    def error(self, message: str) -> NoReturn:
        stream = sys.stderr if self.stderr is None else self.stderr
        self.print_usage(stream)
        _print(
            "error: the arguments could not be parsed; they are not shown "
            "because they can contain file paths; see --help",
            stream,
        )
        sys.exit(EXIT_USAGE)


def build_parser(
    prog: str | None = None, *, stderr: TextIO | None = None
) -> argparse.ArgumentParser:
    """Return the parser of the command line's arguments.

    An argument error prints the usage and a fixed message to ``stderr``,
    by default :data:`sys.stderr`, and exits with :data:`EXIT_USAGE`.
    """
    parser = _Parser(
        prog=prog,
        stderr=stderr,
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
    parser.add_argument(
        "--qc-pack",
        required=True,
        metavar="DIRECTORY",
        help=(
            "the confidential directory for the run's QC pack, outside "
            "RELEASE, which must not exist or must be empty"
        ),
    )
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument(
        "--preset",
        choices=_PRESETS,
        help=(
            "the de-identification policy, one of the presets: "
            + "; ".join(f"{preset}, {_PRESET_USES[preset]}" for preset in _PRESETS)
            + "; a run is refused unless its preset is enabled"
        ),
    )
    selection.add_argument(
        "--option",
        action="append",
        choices=ALL_OPTIONS,
        dest="options",
        metavar="OPTION",
        help=(
            "in place of --preset, a PS3.15 option to apply with the Basic "
            "Profile, given once for each option: "
            + ", ".join(ALL_OPTIONS)
            + "; a run is refused unless each option it gives is enabled"
        ),
    )
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
            "under Clean Descriptors, the custodian's reviewed-names "
            "list, outside SOURCE, RELEASE, and the QC pack; by default, none, "
            "so every ROI Name that cleaning does not rename is held for "
            "review; python -m pymedphys._dicom.deidentify.reviewed_names_command "
            "records a reviewer's decisions in it"
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
            "converted by python -m pymedphys._nomenclature roi-list; it "
            "renames nothing, and the QC pack shows the reviewer of a held "
            "ROI Name the list's names it matches"
        ),
    )
    parser.add_argument(
        "--reviewed-descriptors",
        metavar="FILE",
        help=(
            "under Clean Descriptors, the custodian's reviewed descriptors "
            "list, outside SOURCE, RELEASE, and the QC pack; by default, none, "
            "so only technique descriptors made of reviewed vocabulary words "
            "are kept; python -m "
            "pymedphys._dicom.deidentify.reviewed_descriptors_command records "
            "a reviewer's decisions in it"
        ),
    )
    parser.add_argument(
        "--redaction-review",
        metavar="DIRECTORY",
        help=(
            "under Clean Pixel Data, the QC pack of an earlier run of the same "
            "files under the option, attested with redaction verdicts by python "
            "-m pymedphys._dicom.deidentify.attestation_command; each source "
            "file with an accepted or revised verdict has exactly its reviewed "
            "regions blacked out, and one with a rejected verdict is "
            "sequestered; by default, none, so every image is cleaned by the "
            "text detector and held for review"
        ),
    )
    parser.add_argument(
        "--region-rules",
        metavar="FILE",
        help=(
            "under Clean Pixel Data, the custodian's reviewed region rules, "
            "outside SOURCE, RELEASE, and the QC pack, whose regions are "
            "blacked out in every frame of a matching image beside the text "
            "detector's; by default, none"
        ),
    )
    parser.add_argument(
        "--face-review",
        metavar="DIRECTORY",
        help=(
            "under Clean Recognizable Visual Features, which needs it, the QC "
            "pack of an earlier run of the same files, attested with face "
            "verdicts by python -m "
            "pymedphys._dicom.deidentify.attestation_command; an image or RT "
            "Structure Set is released with the option only where its series "
            "was marked as showing no recognisable face and it is written as "
            "the pack showed it, and every other one is held for review"
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
    parser.add_argument(
        "--key-file",
        metavar="FILE",
        help=(
            "a project key, written by python -m "
            "pymedphys._dicom.deidentify.key_command, outside SOURCE, RELEASE, "
            "and the QC pack, so that the run's generated values agree with "
            "every other run under it; given with --profile-store, and refused "
            "until project keys are enabled; by default, a new run-scoped key"
        ),
    )
    parser.add_argument(
        "--profile-store",
        metavar="FILE",
        help=(
            "the project key's subject profiles, outside SOURCE, RELEASE, and "
            "the QC pack, created if it does not exist and saved before the "
            "release is published; given with --key-file"
        ),
    )
    return parser


class TransformNotBuilt(Exception):
    """A transform that cannot be built, with a message that quotes nothing."""


def build_transform(
    preset: str | None,
    key: DeidKey,
    *,
    options: Collection[str] | None = None,
    cleaning: DescriptorCleaning | None = None,
    finder: TextFinder | None = None,
    redaction_review: RedactionReview | None = None,
    pixel_region_rules: PixelRegionRules | None = None,
    safe_private_list: SafePrivateList = SafePrivateList.REVIEWED,
    profiles: ProfileStore | None = None,
    face_review: FaceReview | None = None,
) -> instance_transform.InstanceTransform:
    """Return the run's transform under ``preset``, or ``options``, and ``key``.

    Parameters
    ----------
    preset : str or None
        As :func:`~pymedphys._dicom.deidentify.policy.select_policy` takes it.
    key : DeidKey
        The run's key.
    options : collection of str, optional
        A custom option set in place of a preset, as
        :func:`~pymedphys._dicom.deidentify.policy.select_policy` takes it
        (D-033).
    cleaning : DescriptorCleaning, optional
        What ROI Names are cleaned with, which a policy with Clean
        Descriptors needs and no other policy takes.
    finder : TextFinder, optional
        What finds text in Pixel Data, such as the text detector, which a
        policy with Clean Pixel Data needs and no other policy takes.
    redaction_review : RedactionReview, optional
        Under Clean Pixel Data, the redaction verdicts of an attested QC
        pack, which no other policy takes.
    pixel_region_rules : PixelRegionRules, optional
        Under Clean Pixel Data, the custodian's reviewed region rules, which
        no other policy takes.
    safe_private_list : SafePrivateList, optional
        Under Retain Safe Private, the list whose rules settle private
        attributes: the reviewed rules, the default, or TCIA's Private Tag
        Dictionary, which no other policy takes.
    profiles : ProfileStore, optional
        A project key's subject profiles, from :func:`run_key`; by default,
        an ephemeral store, for a run-scoped key.
    face_review : FaceReview, optional
        The face verdicts of an earlier run's attested QC pack, which a
        policy with Clean Recognizable Visual Features needs and no other
        policy takes (D-046).

    Raises
    ------
    PolicyError
        If the preset or option set is not enabled, or ``cleaning``,
        ``finder``, ``redaction_review``, ``pixel_region_rules``, or
        ``safe_private_list`` does not fit it, with a message that quotes
        nothing but the names of presets and options. So too if
        ``face_review`` is given without Clean Recognizable Visual Features,
        or left out with it.
    """
    return instance_transform.InstanceTransform(
        policy.select_policy(preset, options=options),
        key,
        cleaning=cleaning,
        finder=finder,
        redaction_review=redaction_review,
        pixel_region_rules=pixel_region_rules,
        safe_private_list=safe_private_list,
        profiles=profiles,
        face_review=face_review,
    )


def _protected(
    source: str | os.PathLike[str],
    release: str | os.PathLike[str],
    qc_pack: str | os.PathLike[str],
) -> tuple[Path, ...]:
    """Return the directories that a custodian's file must lie outside."""
    absolute_release = Path(release).absolute()
    return (
        Path(source),
        absolute_release,
        run.staging_path(absolute_release),
        Path(qc_pack),
    )


def run_key(
    key_file: str | os.PathLike[str] | None,
    profile_store: str | os.PathLike[str] | None,
    *,
    source: str | os.PathLike[str],
    release: str | os.PathLike[str],
    qc_pack: str | os.PathLike[str],
) -> tuple[DeidKey, ProfileStore | None]:
    """Return the run's key and, for a project key, its subject profiles (D-004).

    Without ``key_file`` and ``profile_store``, the key is a new run-scoped
    one, which nothing keeps, and there is no store. A project key needs
    both, since a later run extends earlier ones consistently only with the
    key and the profiles of the subjects already exported. Each must lie
    outside ``source``, ``release`` and its staging area, and ``qc_pack``,
    and outside the PyMedPhys configuration directory; the store is created
    if it does not exist, and must belong to the key.

    Raises
    ------
    TransformNotBuilt
        If only one of ``key_file`` and ``profile_store`` is given, project
        keys are not enabled (:data:`~pymedphys._dicom.deidentify.keys.PROJECT_KEYS_ENABLED`),
        or the key file or store cannot be used, with a message that names
        neither file and quotes nothing of the key.
    """
    if key_file is None and profile_store is None:
        return DeidKey.generate(), None
    if key_file is None or profile_store is None:
        raise TransformNotBuilt(_PROJECT_KEY_HALF)
    if not keys.PROJECT_KEYS_ENABLED:
        raise TransformNotBuilt(_PROJECT_KEYS_NOT_ENABLED)
    protected = _protected(source, release, qc_pack)
    given = Path(key_file).absolute()
    places = (given.parent.resolve() / given.name, given.resolve())
    if not places[1].is_file() or any(
        custodian_location_problem(place, protected) for place in places
    ):
        raise TransformNotBuilt(_KEY_FILE_UNUSABLE)
    try:
        key = read_key_file(places[1])
    except DeidKeyError:
        raise TransformNotBuilt(_KEY_FILE_UNUSABLE) from None
    try:
        profiles = ProfileStore.open(key, profile_store, protected_dirs=protected)
    except (ProfileError, OSError):
        raise TransformNotBuilt(_PROFILES_UNUSABLE) from None
    return key, profiles


def profile_saver(profiles: ProfileStore | None) -> Callable[[], None] | None:
    """Return what saves a project key's profiles before a run publishes.

    For :func:`~pymedphys._dicom.deidentify.run.run`'s ``before_publish``,
    so that a published release always has its subjects' profiles saved
    (D-004). None for no store, or one kept for the run only.
    """
    if profiles is None or not profiles.persistent:
        return None

    def save() -> None:
        try:
            profiles.save()
        except (ProfileError, OSError):
            raise ProfileError(_PROFILES_UNSAVED) from None

    return save


def _face_review(pack: str | os.PathLike[str] | None) -> FaceReview:
    """Return the face verdicts of an attested QC pack (D-046).

    A run under Clean Recognizable Visual Features needs them, so ``pack``
    must be given.

    Raises
    ------
    TransformNotBuilt
        If ``pack`` is None, or the pack cannot be read, has not been
        attested, or its verdicts cannot be used, with
        :func:`~pymedphys._dicom.deidentify.face_review.read_face_review`'s
        message, which names no path and no value, or with none for an
        operating system's error.
    """
    if pack is None:
        raise TransformNotBuilt(_FACE_REVIEW_NEEDED)
    try:
        return read_face_review(pack)
    except QcPackError as error:
        raise TransformNotBuilt(_FACE_REVIEW_UNREAD.format(error=error)) from None
    except OSError:
        raise TransformNotBuilt(_FACE_REVIEW_UNOPENED) from None


def _descriptor_cleaning(  # pylint: disable = too-many-arguments
    *,
    source: str | os.PathLike[str],
    release: str | os.PathLike[str],
    qc_pack: str | os.PathLike[str],
    tg263_spreadsheet: str | os.PathLike[str] | None,
    reviewed_names: str | os.PathLike[str] | None,
    empty_held_roi_names: bool,
    roi_list_path: str | os.PathLike[str] | None,
    reviewed_descriptors: str | os.PathLike[str] | None,
) -> DescriptorCleaning:
    """Return what ROI Names and free-text descriptors are cleaned with (D-009).

    The pinned TG-263 edition is read from ``tg263_spreadsheet`` or else
    from PyMedPhys's cached download. The custodian's reviewed-names list is
    read from ``reviewed_names``, which must exist, since a run records no
    decision (:mod:`.reviewed_names_command` records them), and lie outside
    the source, the release and its staging area, and the QC destination;
    without it, the list is empty. Held names are emptied only with
    ``empty_held_roi_names``. An institutional list, converted from CSV, is
    read from ``roi_list_path``; it renames nothing, and is matched against
    held names for their reviewer (D-009). The custodian's reviewed
    descriptors list is read from ``reviewed_descriptors`` as the
    reviewed-names list is; without it, the list is empty, and only the
    bundled technique vocabulary keeps a descriptor value (D-036).

    Raises
    ------
    TransformNotBuilt
        If the edition or any list cannot be used.
    """
    try:
        nomenclature = (
            tg263_published.load()
            if tg263_spreadsheet is None
            else tg263_published.load(spreadsheet=Path(tg263_spreadsheet))
        )
    except (tg263.TG263Error, OSError):
        raise TransformNotBuilt(_TG263_UNLOADED) from None
    protected = _protected(source, release, qc_pack)
    if reviewed_names is None:
        reviewed = ReviewedNames.empty()
    else:
        try:
            if not Path(reviewed_names).is_file():
                raise TransformNotBuilt(_REVIEWED_MISSING)
            reviewed = ReviewedNames.open(reviewed_names, protected_dirs=protected)
        except (ReviewedNamesError, OSError):
            raise TransformNotBuilt(_REVIEWED_UNUSABLE) from None
    if reviewed_descriptors is None:
        descriptors = ReviewedDescriptors.empty()
    else:
        try:
            if not Path(reviewed_descriptors).is_file():
                raise TransformNotBuilt(_DESCRIPTORS_MISSING)
            descriptors = ReviewedDescriptors.open(
                reviewed_descriptors, protected_dirs=protected
            )
        except (ReviewedDescriptorsError, OSError):
            raise TransformNotBuilt(_DESCRIPTORS_UNUSABLE) from None
    institutional = None
    if roi_list_path is not None:
        try:
            institutional = roi_list.load_json(Path(roi_list_path))
        except (roi_list.RoiListError, OSError, UnicodeDecodeError):
            raise TransformNotBuilt(_ROI_LIST_UNUSABLE) from None
    return DescriptorCleaning(
        nomenclature,
        reviewed,
        empty_held=empty_held_roi_names,
        institutional=institutional,
        reviewed_descriptors=descriptors,
    )


def _redaction_review(pack: str | os.PathLike[str]) -> RedactionReview:
    """Return the redaction verdicts of an attested QC pack (D-048).

    Raises
    ------
    TransformNotBuilt
        If the pack cannot be read, has not been attested, or its verdicts
        cannot be used, with :func:`read_redaction_review`'s message, which
        names no path and no value, or with none for an operating system's
        error.
    """
    try:
        return read_redaction_review(pack)
    except QcPackError as error:
        raise TransformNotBuilt(_REVIEW_UNREAD.format(error=error)) from None
    except OSError:
        raise TransformNotBuilt(_REVIEW_UNOPENED) from None


def _region_rules(
    path: str | os.PathLike[str], protected: Collection[Path]
) -> PixelRegionRules:
    """Return the custodian's reviewed region rules (D-037).

    The store must exist, since a run records no rule, and lie outside the
    ``protected`` directories.

    Raises
    ------
    TransformNotBuilt
        If the store does not exist or cannot be used, with a message that
        names no path and no value.
    """
    try:
        if not Path(path).is_file():
            raise TransformNotBuilt(_RULES_MISSING)
        return PixelRegionRules.open(path, protected_dirs=protected)
    except (PixelRegionRulesError, OSError):
        raise TransformNotBuilt(_RULES_UNUSABLE) from None


def _text_detector() -> TextFinder:
    """Return the text detector, with the pinned model (D-037).

    Raises
    ------
    TransformNotBuilt
        If ONNX Runtime or the model cannot be used, with the detector's
        own message, which names no path, or with none if the model could
        not be downloaded or read.
    """
    try:
        return TextDetector()
    except TextDetectionError as error:
        raise TransformNotBuilt(_DETECTOR_UNMADE.format(error=error)) from None
    except OSError:
        raise TransformNotBuilt(_MODEL_UNREAD) from None


def transform_for(  # pylint: disable = too-many-arguments
    preset: str | None,
    key: DeidKey,
    *,
    options: Collection[str] | None = None,
    source: str | os.PathLike[str],
    release: str | os.PathLike[str],
    qc_pack: str | os.PathLike[str],
    tg263_spreadsheet: str | os.PathLike[str] | None = None,
    reviewed_names: str | os.PathLike[str] | None = None,
    empty_held_roi_names: bool = False,
    roi_list_path: str | os.PathLike[str] | None = None,
    reviewed_descriptors: str | os.PathLike[str] | None = None,
    redaction_review: str | os.PathLike[str] | None = None,
    region_rules: str | os.PathLike[str] | None = None,
    safe_private_list: SafePrivateList = SafePrivateList.REVIEWED,
    profiles: ProfileStore | None = None,
    face_review: str | os.PathLike[str] | None = None,
) -> instance_transform.InstanceTransform:
    """Return :func:`build_transform`'s transform for a run's options.

    The command line and the library build a run's transform here, so that
    both load the same things in the same order. The preset, or the custom
    option set in ``options`` (D-033), is checked before anything is loaded;
    under Clean Descriptors, ROI Names are cleaned with the pinned TG-263
    edition, from ``tg263_spreadsheet`` or PyMedPhys's cached download, and
    the custodian's ``reviewed_names`` list, which must exist and lie
    outside ``source``, ``release`` and its staging area, and ``qc_pack``,
    and, if given, the institutional list converted from CSV at
    ``roi_list_path``, which renames nothing (D-009); and free-text
    descriptors are cleaned with the custodian's ``reviewed_descriptors``
    list, which must exist and lie outside the same directories, and the
    bundled technique vocabulary (D-036). Under Clean Pixel Data, the
    redaction verdicts of the attested QC pack in ``redaction_review`` are
    read (D-048), the custodian's reviewed region rules are read from
    ``region_rules``, which must exist and lie outside the same directories
    (D-037), and the text detector is made, with the pinned model, last,
    since it can download the model. Under any other policy, these options
    are not read. Under Retain Safe Private, ``safe_private_list``
    chooses the list whose rules settle private attributes, and no other
    policy takes TCIA's, which is refused before anything is loaded. A
    project key's subject profiles, from :func:`run_key`, are given as
    ``profiles``; by default, the store is ephemeral. Under Clean
    Recognizable Visual Features, the face verdicts of the attested QC pack
    in ``face_review``, of an earlier run of the same files, are read before
    what ROI Names or descriptors are cleaned with (D-046); the run needs
    them, so without a pack, or with one that cannot be used, no transform
    is built.
    Under any other policy, ``face_review`` is not read.

    Raises
    ------
    TransformNotBuilt
        If the preset or option set is not enabled, ``safe_private_list``
        does not fit it, the policy selects Clean Recognizable Visual
        Features and ``face_review`` is not given, or what ROI Names or
        descriptors are cleaned with, the redaction review, the region
        rules, the face review, or the text detector cannot be used, with a
        message that quotes nothing but the names of presets and options,
        or a reason that names no path or value.
    """
    try:
        selected = policy.select_policy(preset, options=options)
    except policy.PolicyError as error:
        raise TransformNotBuilt(str(error)) from None
    if (
        safe_private_list is not SafePrivateList.REVIEWED
        and policy.SAFE_PRIVATE not in selected.options
    ):
        raise TransformNotBuilt(
            "a safe private list can be chosen only under the Retain Safe "
            "Private Option"
        )
    review = (
        _face_review(face_review)
        if policy.CLEAN_RECOGNIZABLE_VISUAL_FEATURES in selected.options
        else None
    )
    cleaning = (
        _descriptor_cleaning(
            source=source,
            release=release,
            qc_pack=qc_pack,
            tg263_spreadsheet=tg263_spreadsheet,
            reviewed_names=reviewed_names,
            empty_held_roi_names=empty_held_roi_names,
            roi_list_path=roi_list_path,
            reviewed_descriptors=reviewed_descriptors,
        )
        if CLEAN_DESCRIPTORS in selected.options
        else None
    )
    pixel_data = CLEAN_PIXEL_DATA in selected.options
    redaction = (
        _redaction_review(redaction_review)
        if pixel_data and redaction_review is not None
        else None
    )
    rules = (
        _region_rules(region_rules, _protected(source, release, qc_pack))
        if pixel_data and region_rules is not None
        else None
    )
    finder = _text_detector() if pixel_data else None
    try:
        return build_transform(
            preset,
            key,
            options=None if options is None else selected.options,
            cleaning=cleaning,
            finder=finder,
            redaction_review=redaction,
            pixel_region_rules=rules,
            safe_private_list=safe_private_list,
            profiles=profiles,
            face_review=review,
        )
    except policy.PolicyError as error:
        raise TransformNotBuilt(str(error)) from None


def face_review_applies(
    preset: str | None, options: Collection[str] | None = None
) -> bool:
    """Return whether the run's policy takes a face review.

    It applies under Clean Recognizable Visual Features: with a preset, or a
    custom option set in ``options``, that selects it (D-033, D-046), and the
    command line and the library refuse one given otherwise. No preset
    selects it yet. Without either, the run's preset is ``basic``.
    """
    if options is not None:
        return policy.CLEAN_RECOGNIZABLE_VISUAL_FEATURES in options
    return policy.CLEAN_RECOGNIZABLE_VISUAL_FEATURES in policy.PRESETS.get(
        policy.DEFAULT_PRESET if preset is None else preset, ()
    )


def roi_name_options_apply(
    preset: str | None, options: Collection[str] | None = None
) -> bool:
    """Return whether the run's policy takes the ROI name and descriptor options.

    They apply under Clean Descriptors: with a preset that selects it, such as
    ``basic-clean-descriptors``, or a custom option set in ``options`` that
    selects it (D-033).
    Without either, the run's preset is ``basic``.
    """
    if options is not None:
        return CLEAN_DESCRIPTORS in options
    return CLEAN_DESCRIPTORS in policy.PRESETS.get(
        policy.DEFAULT_PRESET if preset is None else preset, ()
    )


def pixel_data_options_apply(
    preset: str | None, options: Collection[str] | None = None
) -> bool:
    """Return whether the run's policy takes the redaction review and region rules.

    They apply under Clean Pixel Data: with a preset, or a custom option set
    in ``options``, that selects it (D-033). No preset selects it yet.
    Without either, the run's preset is ``basic``.
    """
    if options is not None:
        return CLEAN_PIXEL_DATA in options
    return CLEAN_PIXEL_DATA in policy.PRESETS.get(
        policy.DEFAULT_PRESET if preset is None else preset, ()
    )


def _built(
    arguments: argparse.Namespace, key: DeidKey, profiles: ProfileStore | None
) -> instance_transform.InstanceTransform:
    """Return :func:`transform_for`'s transform for the parsed options."""
    return transform_for(
        arguments.preset,
        key,
        options=arguments.options,
        source=arguments.source,
        release=arguments.release,
        qc_pack=arguments.qc_pack,
        tg263_spreadsheet=arguments.tg263,
        reviewed_names=arguments.reviewed_names,
        empty_held_roi_names=arguments.empty_held_roi_names,
        roi_list_path=arguments.roi_list,
        reviewed_descriptors=arguments.reviewed_descriptors,
        redaction_review=arguments.redaction_review,
        region_rules=arguments.region_rules,
        safe_private_list=SafePrivateList(arguments.safe_private_list),
        profiles=profiles,
        face_review=arguments.face_review,
    )


def main(
    argv: Sequence[str] | None = None,
    *,
    transform: run.Transform | None = None,
    gate: run.Gate | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Parse the command line's arguments, and de-identify as they say.

    Each run has a new key, which nothing keeps, as M6's run-scoped key
    requires, unless ``--key-file`` and ``--profile-store`` give a project
    key and its subject profiles, which :func:`run_key` refuses until
    project keys are enabled; the transform is :func:`build_transform`'s for
    the key, and the release report is that transform's. A project key's
    profiles are saved before the release is published.

    Parameters
    ----------
    argv : sequence of str, optional
        The arguments, by default ``sys.argv[1:]``.
    transform : Transform, optional
        In place of :func:`build_transform`'s, for tests; the release then
        has no report.
    gate : Gate, optional
        By default, the release gate,
        :class:`~pymedphys._dicom.deidentify.instance_transform.ReleaseGate`.
    stdout, stderr
        As for :func:`deidentify_directory`.

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
    error_stream = sys.stderr if stderr is None else stderr
    roi_name_options = (
        arguments.tg263 is not None
        or arguments.reviewed_names is not None
        or arguments.empty_held_roi_names
        or arguments.roi_list is not None
        or arguments.reviewed_descriptors is not None
    )
    if roi_name_options and not roi_name_options_apply(
        arguments.preset, arguments.options
    ):
        _print(_ROI_NAME_OPTIONS, error_stream)
        return EXIT_USAGE
    pixel_data_options = (
        arguments.redaction_review is not None or arguments.region_rules is not None
    )
    if pixel_data_options and not pixel_data_options_apply(
        arguments.preset, arguments.options
    ):
        _print(_PIXEL_DATA_OPTIONS, error_stream)
        return EXIT_USAGE
    if arguments.face_review is not None and not face_review_applies(
        arguments.preset, arguments.options
    ):
        _print(_FACE_REVIEW_OPTION, error_stream)
        return EXIT_USAGE
    reporter = written_check = before_publish = None
    if transform is None:
        try:
            with redacted_diagnostics():
                key, profiles = run_key(
                    arguments.key_file,
                    arguments.profile_store,
                    source=arguments.source,
                    release=arguments.release,
                    qc_pack=arguments.qc_pack,
                )
                built = _built(arguments, key, profiles)
        except TransformNotBuilt as error:
            _print(f"error: {error}", error_stream)
            return EXIT_NOT_RUN
        transform, reporter = built, built.reporter
        written_check = built.written_check
        before_publish = profile_saver(profiles)
    return deidentify_directory(
        arguments.source,
        arguments.release,
        transform=transform,
        gate=instance_transform.ReleaseGate() if gate is None else gate,
        qc_destination=arguments.qc_pack,
        reporter=reporter,
        written_check=written_check,
        before_publish=before_publish,
        stdout=stdout,
        stderr=stderr,
    )
