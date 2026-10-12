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
:func:`main` parses the source and release directories, the QC
destination, the preset, and, under Clean Descriptors, what ROI Names are
cleaned with from the command line's arguments, builds the preset's
transform for a new run-scoped key with :func:`build_transform`, and runs
it with the release gate, the transform's release report, and the
reference graph's second pass under its key, for the
``pymedphys`` command to call once the engine is public; nothing registers
it yet. No preset is enabled yet, so until one is, the command refuses to
run.

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
  they give ROI name options without Clean Descriptors;
- :data:`EXIT_NOT_RUN`, 3: the run could not start, because its preset is
  not enabled, or what it cleans ROI Names with cannot be used, among other
  reasons, the first pass stopped it, or its QC pack could not be written,
  and nothing was published;
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
from collections.abc import Sequence
from pathlib import Path
from typing import NoReturn, TextIO

from pymedphys._nomenclature import roi_list, tg263, tg263_published

from . import instance_transform, policy, run, run_report
from .descriptor_cleaning import CLEAN_DESCRIPTORS, DescriptorCleaning
from .diagnostics import RedactionCounts, redacted_diagnostics
from .keys import DeidKey
from .qc_pack import QcPackError
from .reviewed_roi_names import ReviewedNames, ReviewedNamesError

EXIT_RELEASED = 0
EXIT_WITHHELD = 1
EXIT_USAGE = 2
EXIT_NOT_RUN = 3
EXIT_STAGING_LEFT = 4
EXIT_INTERNAL_ERROR = 70

_RELEASED = (run.Status.RELEASED, run.Status.DUPLICATE)
# The first supported release's presets (design document, Scope).
_PRESETS = ("basic", "basic-clean-descriptors")
_ROI_NAME_OPTIONS = (
    "error: --tg263, --reviewed-names, --empty-held-roi-names, and --roi-list "
    "apply only with --preset basic-clean-descriptors"
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


def deidentify_directory(
    source: str | os.PathLike[str],
    release: str | os.PathLike[str],
    *,
    transform: run.Transform,
    gate: run.Gate,
    qc_destination: str | os.PathLike[str],
    reporter: run_report.Reporter | None = None,
    written_check: run.WrittenCheck | None = None,
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
            )
        except (run.RunError, run.RunStopped, QcPackError) as error:
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
    parser.add_argument(
        "--preset",
        choices=_PRESETS,
        default=policy.DEFAULT_PRESET,
        help=(
            "the de-identification policy: the Basic Profile alone (basic, "
            "the default) or with Clean Descriptors (basic-clean-descriptors)"
        ),
    )
    parser.add_argument(
        "--tg263",
        metavar="SPREADSHEET",
        help=(
            "with basic-clean-descriptors, a copy of the pinned TG-263 "
            "spreadsheet to read; by default, PyMedPhys's cached download"
        ),
    )
    parser.add_argument(
        "--reviewed-names",
        metavar="FILE",
        help=(
            "with basic-clean-descriptors, the custodian's reviewed-names "
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
            "with basic-clean-descriptors, empty each ROI Name that would be "
            "held for review, so that its instance can be released"
        ),
    )
    parser.add_argument(
        "--roi-list",
        metavar="FILE",
        help=(
            "with basic-clean-descriptors, an institutional list of ROI names "
            "converted by python -m pymedphys._nomenclature roi-list; it "
            "renames nothing, and the QC pack shows the reviewer of a held "
            "ROI Name the list's names it matches"
        ),
    )
    return parser


class TransformNotBuilt(Exception):
    """A transform that cannot be built, with a message that quotes nothing."""


def build_transform(
    preset: str, key: DeidKey, *, cleaning: DescriptorCleaning | None = None
) -> instance_transform.InstanceTransform:
    """Return the run's transform under ``preset`` and ``key``.

    Parameters
    ----------
    preset : str
        As :func:`~pymedphys._dicom.deidentify.policy.select_policy` takes it.
    key : DeidKey
        The run's key.
    cleaning : DescriptorCleaning, optional
        What ROI Names are cleaned with, which a preset with Clean
        Descriptors needs and no other preset takes.

    Raises
    ------
    PolicyError
        If the preset is not enabled, or ``cleaning`` does not fit it, with a
        message that quotes nothing but the preset's name.
    """
    return instance_transform.InstanceTransform(
        policy.select_policy(preset), key, cleaning=cleaning
    )


def _descriptor_cleaning(  # pylint: disable = too-many-arguments
    *,
    source: str | os.PathLike[str],
    release: str | os.PathLike[str],
    qc_pack: str | os.PathLike[str],
    tg263_spreadsheet: str | os.PathLike[str] | None,
    reviewed_names: str | os.PathLike[str] | None,
    empty_held_roi_names: bool,
    roi_list_path: str | os.PathLike[str] | None,
) -> DescriptorCleaning:
    """Return what ROI Names are cleaned with (D-009).

    The pinned TG-263 edition is read from ``tg263_spreadsheet`` or else
    from PyMedPhys's cached download. The custodian's reviewed-names list is
    read from ``reviewed_names``, which must exist, since a run records no
    decision (:mod:`.reviewed_names_command` records them), and lie outside
    the source, the release and its staging area, and the QC destination;
    without it, the list is empty. Held names are emptied only with
    ``empty_held_roi_names``. An institutional list, converted from CSV, is
    read from ``roi_list_path``; it renames nothing, and is matched against
    held names for their reviewer (D-009).

    Raises
    ------
    TransformNotBuilt
        If the edition or either list cannot be used.
    """
    try:
        nomenclature = (
            tg263_published.load()
            if tg263_spreadsheet is None
            else tg263_published.load(spreadsheet=Path(tg263_spreadsheet))
        )
    except (tg263.TG263Error, OSError):
        raise TransformNotBuilt(_TG263_UNLOADED) from None
    if reviewed_names is None:
        reviewed = ReviewedNames.empty()
    else:
        absolute_release = Path(release).absolute()
        protected = (
            Path(source),
            absolute_release,
            run.staging_path(absolute_release),
            Path(qc_pack),
        )
        try:
            if not Path(reviewed_names).is_file():
                raise TransformNotBuilt(_REVIEWED_MISSING)
            reviewed = ReviewedNames.open(reviewed_names, protected_dirs=protected)
        except (ReviewedNamesError, OSError):
            raise TransformNotBuilt(_REVIEWED_UNUSABLE) from None
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
    )


def transform_for(  # pylint: disable = too-many-arguments
    preset: str,
    key: DeidKey,
    *,
    source: str | os.PathLike[str],
    release: str | os.PathLike[str],
    qc_pack: str | os.PathLike[str],
    tg263_spreadsheet: str | os.PathLike[str] | None = None,
    reviewed_names: str | os.PathLike[str] | None = None,
    empty_held_roi_names: bool = False,
    roi_list_path: str | os.PathLike[str] | None = None,
) -> instance_transform.InstanceTransform:
    """Return :func:`build_transform`'s transform for a run's options.

    The command line and the library build a run's transform here, so that
    both load the same things in the same order. The preset is checked
    before anything is loaded; under Clean Descriptors, ROI Names are
    cleaned with the pinned TG-263 edition, from ``tg263_spreadsheet`` or
    PyMedPhys's cached download, and the custodian's ``reviewed_names``
    list, which must exist and lie outside ``source``, ``release`` and its
    staging area, and ``qc_pack``, and, if given, the institutional list
    converted from CSV at ``roi_list_path``, which renames nothing (D-009).
    Under any other preset, the ROI name
    options are not read.

    Raises
    ------
    TransformNotBuilt
        If the preset is not enabled, or what ROI Names are cleaned with
        cannot be used, with a message that quotes nothing but the preset's
        name.
    """
    try:
        selected = policy.select_policy(preset)
    except policy.PolicyError as error:
        raise TransformNotBuilt(str(error)) from None
    cleaning = (
        _descriptor_cleaning(
            source=source,
            release=release,
            qc_pack=qc_pack,
            tg263_spreadsheet=tg263_spreadsheet,
            reviewed_names=reviewed_names,
            empty_held_roi_names=empty_held_roi_names,
            roi_list_path=roi_list_path,
        )
        if CLEAN_DESCRIPTORS in selected.options
        else None
    )
    try:
        return build_transform(preset, key, cleaning=cleaning)
    except policy.PolicyError as error:
        raise TransformNotBuilt(str(error)) from None


def roi_name_options_apply(preset: str) -> bool:
    """Return whether ``preset`` takes the ROI name options, as Clean Descriptors does."""
    return CLEAN_DESCRIPTORS in policy.PRESETS.get(preset, ())


def _built(
    arguments: argparse.Namespace, key: DeidKey
) -> instance_transform.InstanceTransform:
    """Return :func:`transform_for`'s transform for the parsed options."""
    return transform_for(
        arguments.preset,
        key,
        source=arguments.source,
        release=arguments.release,
        qc_pack=arguments.qc_pack,
        tg263_spreadsheet=arguments.tg263,
        reviewed_names=arguments.reviewed_names,
        empty_held_roi_names=arguments.empty_held_roi_names,
        roi_list_path=arguments.roi_list,
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
    requires; the transform is :func:`build_transform`'s for it, and the
    release report is that transform's.

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
    )
    if roi_name_options and not roi_name_options_apply(arguments.preset):
        _print(_ROI_NAME_OPTIONS, error_stream)
        return EXIT_USAGE
    reporter = written_check = None
    if transform is None:
        try:
            with redacted_diagnostics():
                built = _built(arguments, DeidKey.generate())
        except TransformNotBuilt as error:
            _print(f"error: {error}", error_stream)
            return EXIT_NOT_RUN
        transform, reporter = built, built.reporter
        written_check = built.written_check
    return deidentify_directory(
        arguments.source,
        arguments.release,
        transform=transform,
        gate=instance_transform.ReleaseGate() if gate is None else gate,
        qc_destination=arguments.qc_pack,
        reporter=reporter,
        written_check=written_check,
        stdout=stdout,
        stderr=stderr,
    )
