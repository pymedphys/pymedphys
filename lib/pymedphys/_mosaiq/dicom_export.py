# Copyright (C) 2026 Derek Lane

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Export the DICOM instances stored in Mosaiq to a directory of files.

Mosaiq keeps a DICOM instance's metadata in ``DCMStudy``, ``DCMSeries`` and
``DCMInstance``, and its bytes in the Binary Data Store, outside the
database. ``vw_LegacyDCMInstance.Rawdata`` reads those bytes on the caller's
behalf, so the export reads them from there, one instance per query, to keep
at most one instance in memory.

The directory this writes is a valid source for
:func:`pymedphys._dicom.deidentify.api.deidentify`.
"""

from __future__ import annotations

import dataclasses
import os
import re
import shutil
import tempfile
from collections.abc import Collection
from pathlib import Path

from pymedphys._dicom.deidentify.api import Deidentified, deidentify

from . import api
from .connect import Connection

# The only value seen in practice: the bytes come back as the DICOM file.
UNCOMPRESSED = 0

# A UID is digits and dots, which keeps it a single safe path component.
_UID = re.compile(r"[0-9]+(\.[0-9]+)*")


class ExportError(Exception):
    """An instance that cannot be exported as stored."""


@dataclasses.dataclass(frozen=True)
class Instance:
    """One row of ``DCMInstance`` with the UIDs that locate it."""

    instance_id: int
    study_uid: str
    series_uid: str
    sop_instance_uid: str
    compression_scheme: int
    n_bytes: int


@dataclasses.dataclass(frozen=True)
class Exported:
    """What an export wrote, and what Mosaiq could not supply.

    Attributes
    ----------
    written : tuple of pathlib.Path
        The files written, below the export directory.
    missing : tuple of Instance
        The instances for which ``Rawdata`` was NULL, which the view returns
        when it cannot find the instance's file in the Binary Data Store.
    """

    written: tuple[Path, ...]
    missing: tuple[Instance, ...]


def find_instances(
    connection: Connection,
    *,
    study_instance_uids: Collection[str] | None = None,
    patient_ids: Collection[str] | None = None,
) -> list[Instance]:
    """List the instances of the selected studies, in a stable order.

    Parameters
    ----------
    connection : pymedphys.mosaiq.Connection
        A Mosaiq connection.
    study_instance_uids : collection of str, optional
        Select the studies with these Study Instance UIDs.
    patient_ids : collection of str, optional
        Select the studies of the patients with these Mosaiq IDs
        (``Ident.IDA``).

    Raises
    ------
    ValueError
        If neither selector is given, since exporting every study in
        Mosaiq is never the intent.
    """
    clauses = []
    parameters: dict[str, tuple[str, ...]] = {}

    if study_instance_uids:
        clauses.append("DCMStudy.StudyInstanceUID IN %(study_uids)s")
        parameters["study_uids"] = tuple(study_instance_uids)
    if patient_ids:
        clauses.append("Ident.IDA IN %(patient_ids)s")
        parameters["patient_ids"] = tuple(patient_ids)
    if not clauses:
        raise ValueError("Select by study_instance_uids or patient_ids.")

    rows = api.execute(
        connection,
        f"""
        SELECT
            DCMInstance.DCMInstance_ID,
            DCMStudy.StudyInstanceUID,
            DCMSeries.SeriesInstanceUID,
            DCMInstance.SOPInstanceUID,
            DCMInstance.InternalCompressionScheme,
            DCMInstance.NBytesDecompressed
        FROM DCMInstance
        INNER JOIN DCMSeries ON DCMSeries.DCMSeries_ID = DCMInstance.DCMSeries_ID
        INNER JOIN DCMStudy ON DCMStudy.DCMStudy_ID = DCMSeries.DCMStudy_ID
        INNER JOIN Ident ON Ident.Pat_ID1 = DCMStudy.Pat_ID1
        WHERE {" AND ".join(clauses)}
        ORDER BY
            DCMStudy.StudyInstanceUID,
            DCMSeries.SeriesInstanceUID,
            DCMInstance.SOPInstanceUID
        """,  # nosec B608 - clauses are fixed strings, values are parameters
        parameters,
    )

    return [Instance(*row) for row in rows]


def export_instances(
    connection: Connection,
    directory: str | os.PathLike[str],
    *,
    study_instance_uids: Collection[str] | None = None,
    patient_ids: Collection[str] | None = None,
) -> Exported:
    """Write the selected instances to ``directory`` as DICOM files.

    The files are written to ``<study uid>/<series uid>/<sop uid>.dcm``, so
    the names carry only DICOM UIDs.

    Parameters
    ----------
    connection : pymedphys.mosaiq.Connection
        A Mosaiq connection.
    directory : str or os.PathLike
        The directory to export into. It is created if absent and must not
        already hold any of the files this would write.
    study_instance_uids, patient_ids
        As :func:`find_instances`.

    Raises
    ------
    ExportError
        If an instance is compressed in Mosaiq, if its bytes are not the
        size Mosaiq recorded, or if its file already exists.
    """
    root = Path(directory)
    instances = find_instances(
        connection,
        study_instance_uids=study_instance_uids,
        patient_ids=patient_ids,
    )

    # Check every instance before writing any, so a refusal leaves no
    # partial export behind.
    for instance in instances:
        for uid in (
            instance.study_uid,
            instance.series_uid,
            instance.sop_instance_uid,
        ):
            if not _UID.fullmatch(uid):
                raise ExportError(
                    f"Instance {instance.instance_id} has a UID that is not a DICOM UID."
                )
        if instance.compression_scheme != UNCOMPRESSED:
            raise ExportError(
                f"Instance {instance.instance_id} is stored with compression "
                f"scheme {instance.compression_scheme}, which is not supported."
            )
        if _path(root, instance).exists():
            raise ExportError(f"{_path(root, instance)} already exists.")

    written = []
    missing = []
    for instance in instances:
        data = _rawdata(connection, instance)
        if data is None:
            missing.append(instance)
            continue
        if len(data) != instance.n_bytes:
            raise ExportError(
                f"Instance {instance.instance_id} has {len(data)} bytes, "
                f"but Mosaiq recorded {instance.n_bytes}."
            )

        path = _path(root, instance)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        written.append(path)

    return Exported(written=tuple(written), missing=tuple(missing))


def export_deidentified(  # pylint: disable = too-many-arguments
    connection: Connection,
    release: str | os.PathLike[str],
    *,
    qc_pack: str | os.PathLike[str],
    study_instance_uids: Collection[str] | None = None,
    patient_ids: Collection[str] | None = None,
    staging: str | os.PathLike[str] | None = None,
    allow_missing: bool = False,
    **deidentify_options,
) -> tuple[Exported, Deidentified]:
    """Export the selected instances and de-identify them into a release.

    The instances are exported to a staging directory, de-identified in a
    single run so that UIDs and dates stay consistent across everything
    selected, and the staging directory is then deleted, since it holds
    identifiable data. It is deleted if the run fails too.

    Parameters
    ----------
    connection : pymedphys.mosaiq.Connection
        A Mosaiq connection.
    release : str or os.PathLike
        The release directory to create, as
        :func:`~pymedphys._dicom.deidentify.api.deidentify` takes it.
    qc_pack : str or os.PathLike
        The confidential QC pack directory, as ``deidentify`` takes it.
    study_instance_uids, patient_ids
        As :func:`find_instances`. Everything selected is de-identified in one
        run, so select a patient's studies together to keep their references
        to one another intact.
    staging : str or os.PathLike, optional
        The staging directory, which must not exist, and which is deleted
        afterwards. By default, a new temporary directory.
    allow_missing : bool, optional
        Release even though Mosaiq could not supply some instances, which
        are then only listed in the returned :class:`Exported`. By default
        that is refused, since the release would otherwise look complete.
    **deidentify_options
        Passed unchanged to
        :func:`~pymedphys._dicom.deidentify.api.deidentify`, such as
        ``preset``, ``options`` and ``reviewed_names``.

    Returns
    -------
    exported : Exported
        What was exported from Mosaiq.
    deidentified : pymedphys._dicom.deidentify.api.Deidentified
        What the de-identification did.

    Raises
    ------
    ExportError
        As :func:`export_instances` raises it; or if instances are missing
        and ``allow_missing`` is false, if ``staging`` exists, or if the
        staging directory could not be deleted. Nothing is released in the
        first three cases.
    """
    if staging is None:
        root = Path(tempfile.mkdtemp(prefix="pymedphys-mosaiq-export-"))
    else:
        root = Path(staging)
        if root.exists():
            raise ExportError(f"{root} already exists.")

    try:
        exported = export_instances(
            connection,
            root,
            study_instance_uids=study_instance_uids,
            patient_ids=patient_ids,
        )
        if exported.missing and not allow_missing:
            raise ExportError(
                f"Mosaiq could not supply {len(exported.missing)} of the "
                f"{len(exported.missing) + len(exported.written)} selected "
                "instances. Nothing was de-identified."
            )

        deidentified = deidentify(root, release, qc_pack=qc_pack, **deidentify_options)
    finally:
        _delete(root)

    return exported, deidentified


def _delete(root: Path) -> None:
    try:
        shutil.rmtree(root)
    except FileNotFoundError:
        pass
    except OSError as error:
        raise ExportError(
            f"Could not delete {root}, which holds identifiable data."
        ) from error


def _path(root: Path, instance: Instance) -> Path:
    return (
        root
        / instance.study_uid
        / instance.series_uid
        / f"{instance.sop_instance_uid}.dcm"
    )


def _rawdata(connection: Connection, instance: Instance) -> bytes | None:
    rows = api.execute(
        connection,
        """
        SELECT Rawdata
        FROM vw_LegacyDCMInstance
        WHERE DCMInstance_ID = %(instance_id)s
        """,
        {"instance_id": instance.instance_id},
    )
    if not rows or rows[0][0] is None:
        return None

    return bytes(rows[0][0])
