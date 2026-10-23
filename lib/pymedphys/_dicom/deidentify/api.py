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

"""The library's entry point: de-identify a directory, and return what happened.

:func:`deidentify` is the library API that the design document's Scope
says the first supported release ships beside the command line. It runs a
directory exactly as :func:`~pymedphys._dicom.deidentify.command.main`
does: a new run-scoped key that nothing keeps, or a project key and its
subject profiles once project keys are enabled, the transform of its preset
or custom option set (D-033) from
:func:`~pymedphys._dicom.deidentify.command.transform_for`, the release
gate, the transform's release report, and the reference graph's second
pass under its key. Where the command prints a
summary and returns an exit status, it prints nothing and returns
:class:`Deidentified`; where the command exits because the run could not
start, it raises.

It is private until the release, which is to export it as
``pymedphys.dicom.deidentify``; nothing exports it yet. No preset or option
is enabled yet, so until one is, it raises :class:`DeidentifyError`.
"""

from __future__ import annotations

import dataclasses
import os
from collections.abc import Collection

from . import command, instance_transform, policy, run
from .diagnostics import RedactionCounts, redacted_diagnostics
from .safe_private import SafePrivateList


class DeidentifyError(Exception):
    """A run that could not start, with a message that quotes no path or value.

    Its preset or option set is not enabled, or what it cleans ROI Names
    with cannot be used. Nothing was created.
    """


@dataclasses.dataclass(frozen=True)
class Deidentified:
    """What a run of :func:`deidentify` did, without a source value or path.

    Attributes
    ----------
    result : RunResult
        The run's result, with each input's outcome by run position.
    redacted : RedactionCounts
        How many warnings and log records were redacted during the run.
    """

    result: run.RunResult
    redacted: RedactionCounts

    @property
    def exit_status(self) -> int:
        """The command line's exit status for this run.

        :data:`~pymedphys._dicom.deidentify.command.EXIT_RELEASED`,
        :data:`~pymedphys._dicom.deidentify.command.EXIT_WITHHELD`, or
        :data:`~pymedphys._dicom.deidentify.command.EXIT_STAGING_LEFT`.
        """
        return command.exit_status(self.result)

    @property
    def released(self) -> bool:
        """Whether every input was released, or is an identical copy of one that was.

        It is also false if the staging area could not be deleted.
        """
        return self.exit_status == command.EXIT_RELEASED

    def summary(self) -> list[str]:
        """Return the command line's summary of the run, line by line."""
        return command.summary_lines(self.result, self.redacted)


def deidentify(  # pylint: disable = too-many-arguments
    source: str | os.PathLike[str],
    release: str | os.PathLike[str],
    *,
    qc_pack: str | os.PathLike[str],
    preset: str | None = None,
    options: Collection[str] | None = None,
    tg263_spreadsheet: str | os.PathLike[str] | None = None,
    reviewed_names: str | os.PathLike[str] | None = None,
    empty_held_roi_names: bool = False,
    roi_list: str | os.PathLike[str] | None = None,
    reviewed_descriptors: str | os.PathLike[str] | None = None,
    safe_private_list: str = "reviewed",
    key_file: str | os.PathLike[str] | None = None,
    profile_store: str | os.PathLike[str] | None = None,
) -> Deidentified:
    """De-identify the DICOM files below a source directory into a new release.

    The release directory is published whole once every file has been
    checked, or not at all, as :func:`~pymedphys._dicom.deidentify.run.run`
    publishes it.

    Parameters
    ----------
    source : str or os.PathLike
        The directory of source files.
    release : str or os.PathLike
        The release directory to create, which must not exist. Its parent
        must.
    qc_pack : str or os.PathLike
        The confidential directory for the run's QC pack, outside
        ``source`` and ``release``, which must not exist or must be empty.
    preset : str, optional
        The de-identification policy: ``"basic"``, the Basic Profile alone
        (the default, unless ``options`` is given), or
        ``"basic-clean-descriptors"``, with Clean Descriptors.
    options : collection of str, optional
        A custom option set in place of a preset (D-033): the names of
        options of PS3.15 Table E.1-1, such as ``"clean_descriptors"``, or
        of the Clean Pixel Data and Clean Recognizable Visual Features
        Options, to apply with the Basic Profile. The run is refused unless
        each is enabled.
    tg263_spreadsheet : str or os.PathLike, optional
        Under Clean Descriptors, a copy of the pinned TG-263 spreadsheet to
        read; by default, PyMedPhys's cached download.
    reviewed_names : str or os.PathLike, optional
        Under Clean Descriptors, the custodian's reviewed-names list, which
        must exist, outside ``source``, ``release``, and ``qc_pack``. By
        default, none, so every ROI Name that cleaning does not rename is
        held for review.
    empty_held_roi_names : bool, optional
        Under Clean Descriptors, empty each ROI Name that would be held for
        review, so that its instance can be released.
    roi_list : str or os.PathLike, optional
        Under Clean Descriptors, an institutional list of ROI names,
        converted from CSV by ``python -m pymedphys._nomenclature
        roi-list``. It renames nothing: the QC pack shows the reviewer of a
        held ROI Name the list's names that it matches (D-009).
    reviewed_descriptors : str or os.PathLike, optional
        Under Clean Descriptors, the custodian's reviewed descriptors list,
        which must exist, outside ``source``, ``release``, and ``qc_pack``,
        recorded by ``python -m
        pymedphys._dicom.deidentify.reviewed_descriptors_command``. By
        default, none, so only technique descriptors made of reviewed
        vocabulary words are kept (D-036).
    safe_private_list : str, optional
        Under Retain Safe Private, the list whose rules settle private
        attributes: ``"reviewed"``, the default, for the reviewed rules of
        Table E.3.10-1 and their additions, or ``"tcia"`` for the Private
        Tag Dictionary of The Cancer Imaging Archive. The method digest,
        the release report, and the conformance statement record which.
    key_file : str or os.PathLike, optional
        A project key, written by ``python -m
        pymedphys._dicom.deidentify.key_command``, outside ``source``,
        ``release``, and ``qc_pack``, so that the run's replacement UIDs,
        pseudonyms, and date offsets agree with every other run under it
        (D-004). It is given with ``profile_store``, and refused until
        project keys are enabled. By default, a new run-scoped key, which
        nothing keeps.
    profile_store : str or os.PathLike, optional
        The project key's subject profiles, outside the same directories,
        created if it does not exist, and saved before the release is
        published, so that each subject keeps the date offset of its first
        export. It is given with ``key_file``.

    Returns
    -------
    Deidentified
        What the run did. Each input that was not released has its reasons
        in its outcome; :attr:`Deidentified.released` says whether there
        are any, and whether the staging area was deleted.

    Raises
    ------
    TypeError
        If ``options`` is a single string rather than a collection of
        names. Nothing is read or created.
    ValueError
        If both ``preset`` and ``options`` are given, or if
        ``tg263_spreadsheet``, ``reviewed_names``, ``empty_held_roi_names``,
        ``roi_list``, or ``reviewed_descriptors`` is given with a policy
        without Clean Descriptors, or if ``safe_private_list`` is not
        ``"reviewed"`` or ``"tcia"``, or is ``"tcia"`` with a policy without
        Retain Safe Private. Nothing is read or created.
    DeidentifyError
        If the preset or an option is unknown or not enabled, the options
        cannot be composed, or the TG-263 edition, the reviewed-names list,
        the institutional list, or the reviewed descriptors list cannot be
        used; or if only one of ``key_file`` and ``profile_store`` is given,
        project keys are not enabled, or either cannot be used. Nothing is
        created.
    ~pymedphys._dicom.deidentify.profiles.ProfileError
        If the profile store could not be saved. Nothing is published.
    ~pymedphys._dicom.deidentify.run.RunError
    ~pymedphys._dicom.deidentify.run.RunStopped
    ~pymedphys._dicom.deidentify.qc_pack.QcPackError
        As :func:`~pymedphys._dicom.deidentify.run.run` raises them; their
        messages name only the caller's directories, counts, or the check of
        the QC destination that failed. Nothing is published.

    Any other error that stops the run passes through unchanged, and its
    message can quote a path or a DICOM value. Nothing is published, but a
    run that fails can leave its staging area,
    :func:`~pymedphys._dicom.deidentify.run.staging_path` of ``release``,
    which may hold output that still identifies people.
    """
    if preset is not None and options is not None:
        raise ValueError("give a preset or options, not both")
    if isinstance(options, str):
        raise TypeError(
            "options must be a collection of option names, not a single string"
        )
    # Read once, so that the check below and the run see the same options.
    chosen = None if options is None else tuple(options)
    roi_name_options = (
        tg263_spreadsheet is not None
        or reviewed_names is not None
        or empty_held_roi_names
        or roi_list is not None
        or reviewed_descriptors is not None
    )
    if roi_name_options and not command.roi_name_options_apply(preset, chosen):
        raise ValueError(
            "tg263_spreadsheet, reviewed_names, empty_held_roi_names, roi_list, "
            "and reviewed_descriptors apply only under Clean Descriptors: with the "
            "basic-clean-descriptors preset, or options that include "
            "clean_descriptors"
        )
    try:
        chosen_list = SafePrivateList(safe_private_list)
    except ValueError:
        raise ValueError('safe_private_list must be "reviewed" or "tcia"') from None
    if chosen_list is not SafePrivateList.REVIEWED and not _safe_private_applies(
        preset, chosen
    ):
        raise ValueError(
            'safe_private_list "tcia" applies only under Retain Safe Private: '
            "with a preset or options that include retain_safe_private"
        )
    with redacted_diagnostics() as counts:
        try:
            key, profiles = command.run_key(
                key_file,
                profile_store,
                source=source,
                release=release,
                qc_pack=qc_pack,
            )
            transform = command.transform_for(
                preset,
                key,
                options=chosen,
                source=source,
                release=release,
                qc_pack=qc_pack,
                tg263_spreadsheet=tg263_spreadsheet,
                reviewed_names=reviewed_names,
                empty_held_roi_names=empty_held_roi_names,
                roi_list_path=roi_list,
                reviewed_descriptors=reviewed_descriptors,
                safe_private_list=chosen_list,
                profiles=profiles,
            )
        except command.TransformNotBuilt as error:
            raise DeidentifyError(str(error)) from None
        result = run.run(
            run.discover(source),
            release,
            transform,
            instance_transform.ReleaseGate(),
            qc_destination=qc_pack,
            reporter=transform.reporter,
            written_check=transform.written_check,
            before_publish=command.profile_saver(profiles),
        )
    return Deidentified(result, counts)


def _safe_private_applies(preset: str | None, options: tuple[str, ...] | None) -> bool:
    """Return whether the run's policy selects Retain Safe Private."""
    if options is not None:
        return policy.SAFE_PRIVATE in options
    return policy.SAFE_PRIVATE in policy.PRESETS.get(
        policy.DEFAULT_PRESET if preset is None else preset, ()
    )
