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
does: a new run-scoped key that nothing keeps, the preset's transform from
:func:`~pymedphys._dicom.deidentify.command.transform_for`, the release
gate, the transform's release report, and the reference graph's second
pass under its key. Where the command prints a
summary and returns an exit status, it prints nothing and returns
:class:`Deidentified`; where the command exits because the run could not
start, it raises.

It is private until the release, which is to export it as
``pymedphys.dicom.deidentify``; nothing exports it yet. No preset is
enabled yet, so until one is, it raises :class:`DeidentifyError`.
"""

from __future__ import annotations

import dataclasses
import os

from . import command, instance_transform, policy, run
from .diagnostics import RedactionCounts, redacted_diagnostics
from .keys import DeidKey


class DeidentifyError(Exception):
    """A run that could not start, with a message that quotes no path or value.

    Its preset is not enabled, or what it cleans ROI Names with cannot be
    used. Nothing was created.
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
    preset: str = policy.DEFAULT_PRESET,
    tg263_spreadsheet: str | os.PathLike[str] | None = None,
    reviewed_names: str | os.PathLike[str] | None = None,
    empty_held_roi_names: bool = False,
    roi_list: str | os.PathLike[str] | None = None,
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
        (the default), or ``"basic-clean-descriptors"``, with Clean
        Descriptors.
    tg263_spreadsheet : str or os.PathLike, optional
        With ``basic-clean-descriptors``, a copy of the pinned TG-263
        spreadsheet to read; by default, PyMedPhys's cached download.
    reviewed_names : str or os.PathLike, optional
        With ``basic-clean-descriptors``, the custodian's reviewed-names
        list, which must exist, outside ``source``, ``release``, and
        ``qc_pack``. By default, none, so every ROI Name that cleaning does
        not rename is held for review.
    empty_held_roi_names : bool, optional
        With ``basic-clean-descriptors``, empty each ROI Name that would be
        held for review, so that its instance can be released.
    roi_list : str or os.PathLike, optional
        With ``basic-clean-descriptors``, an institutional list of ROI
        names, converted from CSV by ``python -m pymedphys._nomenclature
        roi-list``. It renames nothing: the QC pack shows the reviewer of a
        held ROI Name the list's names that it matches (D-009).

    Returns
    -------
    Deidentified
        What the run did. Each input that was not released has its reasons
        in its outcome; :attr:`Deidentified.released` says whether there
        are any, and whether the staging area was deleted.

    Raises
    ------
    ValueError
        If ``tg263_spreadsheet``, ``reviewed_names``,
        ``empty_held_roi_names``, or ``roi_list`` is given with a preset
        without Clean Descriptors. Nothing is read or created.
    DeidentifyError
        If the preset is not enabled, or the TG-263 edition, the
        reviewed-names list, or the institutional list cannot be used.
        Nothing is created.
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
    roi_name_options = (
        tg263_spreadsheet is not None
        or reviewed_names is not None
        or empty_held_roi_names
        or roi_list is not None
    )
    if roi_name_options and not command.roi_name_options_apply(preset):
        raise ValueError(
            "tg263_spreadsheet, reviewed_names, empty_held_roi_names, and "
            "roi_list apply only with the basic-clean-descriptors preset"
        )
    with redacted_diagnostics() as counts:
        try:
            transform = command.transform_for(
                preset,
                DeidKey.generate(),
                source=source,
                release=release,
                qc_pack=qc_pack,
                tg263_spreadsheet=tg263_spreadsheet,
                reviewed_names=reviewed_names,
                empty_held_roi_names=empty_held_roi_names,
                roi_list_path=roi_list,
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
        )
    return Deidentified(result, counts)
