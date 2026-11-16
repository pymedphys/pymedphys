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

"""The face block and CT defacing, checked and rendered on Steven
Keating's cranial CT (D-058).

In 2014 Steven Keating released a cranial CT of his own head on Zenodo
(:data:`RECORD_DOI`), as "open access (CC0) with approval from patient",
three months after an astrocytoma was removed: a hospital's CD export of
one acquisition, reconstructed as two axial series of 216 slices 1.25 mm
apart, from below the chin to the vertex, one on a 284 mm field of view and
one on a 500 mm field of view. It is a living adult's head, with globes,
lenses, orbital fat, bony orbits, a cranium with a craniotomy, and a face
in front of air, imaged by a clinical scanner, and its subject chose to
make it public, so its face can be rendered where this project's results
are public. It is held-out evidence: the finder's settings were not set
from it and are not to be tuned to it.

:func:`check_keating` refuses an archive whose size, MD5, or SHA-256
differs from those pinned (:data:`ARCHIVE_SIZE`, :data:`ARCHIVE_MD5`,
:data:`ARCHIVE_SHA256`), writes each axial series' files into a folder of
its own in a temporary directory (:func:`extract_series`), refuses a
series whose files differ from those pinned in :data:`SERIES`, and checks
each series as the Visible Human check checks a series
(:func:`~pymedphys._dicom.deidentify.face_validation_vhp.check_series`):
the finder's outcome as a run finds it, by stack, and resampled; what it
saw; how the globes that it finds compare with reference globe centres
placed by hand, independently of its output; the Hounsfield units about
each reference globe; what the CT defacer would write for each block
found and for a reference block placed from the reference globes; and
renders of the skin surface as received and as each block would deface
it, and of slices through each globe with the globes and blocks marked,
each carrying :data:`CREDIT`. Nothing here changes a setting of the finder
or the defacer.

The headers carry the identifiers of the subject, who published them; the
summary holds none of them, only geometry, counts, and measures, and the
renders show only pixels and the captions here.
"""

from __future__ import annotations

import io
import os
import pathlib
import tempfile
import zipfile
from collections.abc import Sequence
from typing import Any

from pymedphys._imports import pydicom

from .face_validation import (
    CT_IMAGE_STORAGE,
    FaceValidationRefused,
    _settings,
    _software,
    file_digest,
)
from .face_validation_vhp import (
    CORE,
    REFERENCE_RADIUS,
    REFERENCE_TOLERANCE,
    SHELL,
    Credit,
    VhpSeries,
    check_series,
    manifest_digest,
)

FORMAT = "pymedphys-deid-face-validation-keating/1"
RECORD_DOI = "10.5281/zenodo.16816"
RECORD = "https://zenodo.org/records/16816"
ARCHIVE = "CT_Scan_-_Steven_Keating_-_Nov_19_2014_MGH.zip"
# The size and MD5 that the Zenodo record gives, and the SHA-256 of the
# same file, downloaded on 1 November 2026.
ARCHIVE_SIZE = 84560647
ARCHIVE_MD5 = "30583051d773ba5f6bc182e6e183f618"
ARCHIVE_SHA256 = "b7a36cd6ad9e0160fc6cee8c88fa9c83085fdbf989e1f7a80bf311d774ad7d86"
LICENCE = "CC0 1.0"
LICENCE_URL = "https://creativecommons.org/publicdomain/zero/1.0/"
# CC0 asks for no attribution; the record is credited all the same.
ATTRIBUTION = (
    "Cranial CT of Steven Keating, released by him on Zenodo as open access "
    f"under CC0 1.0 (doi:{RECORD_DOI})."
)
NOTICE = (
    f"Steven Keating's cranial CT of 19 November 2014, Zenodo record {RECORD}, "
    f'doi:{RECORD_DOI}, released as "Open access (CC0) with approval from '
    'patient". No endorsement by him of PyMedPhys or of these results is '
    "implied."
)
HELD_OUT = (
    "Held-out evidence: the face block finder's settings were not set from "
    "this scan and are not to be tuned to it."
)
CREDIT = Credit(f"{ATTRIBUTION} {HELD_OUT}", f"{ATTRIBUTION}\n\n{NOTICE}\n")
SUBJECT = "Keating"
JSON_NAME = "face-validation-keating.json"
MARKDOWN_NAME = "face-validation-keating.md"
RENDERS = "renders"
# A ZIP file member left by the archiver of the macOS Finder, which holds
# its metadata, not the export.
_MACOS = "__MACOSX/"

# Placed on 1 November 2026, before the finder was run on the scan, from
# axial and sagittal views and from Hounsfield unit profiles along each
# axis through each globe, as the midpoint of the globe's extent along each
# axis: between the peaks of the sclera, of 50 to 75 HU, medially and
# laterally, inferiorly and superiorly, and posteriorly, and the front of
# the cornea against air. Both series image one acquisition in one patient
# coordinate system and give the same extents within 0.5 mm.
GLOBES = ((-31.0, -82.5, -33.5), (28.0, -83.0, -33.5))
# Each axial series, by its Series Number, pinned by its file count and
# manifest_digest of its files as extract_series writes them.
SERIES: tuple[VhpSeries, ...] = (
    VhpSeries(
        "series-3",
        SUBJECT,
        "axial, 1.25 mm slices, 0.55 mm pixels on a 284 mm field of view",
        216,
        "cbc88aa261621125e267c7a335c97b4c3c63d8b8cc5ee5730085a36fd88a4ec6",
        GLOBES,
        rendered=True,
        name="Keating-series-3",
    ),
    VhpSeries(
        "series-4",
        SUBJECT,
        "axial, 1.25 mm slices, 0.98 mm pixels on a 500 mm field of view",
        216,
        "b7e7c1051235ed36df4a15bf66512dc0e83d510aece556de24887335e26d7a0c",
        GLOBES,
        rendered=True,
        name="Keating-series-4",
    ),
)


def verify_archive(path: os.PathLike[str] | str) -> dict[str, Any]:
    """The archive's size, MD5, and SHA-256, if they are those pinned.

    Raises
    ------
    FaceValidationRefused
        If the file cannot be read, or any of the three differs.
    """
    try:
        digest = file_digest(pathlib.Path(path))
    except OSError:
        raise FaceValidationRefused("The archive cannot be read.") from None
    pinned = {"size": ARCHIVE_SIZE, "md5": ARCHIVE_MD5, "sha256": ARCHIVE_SHA256}
    if digest != pinned:
        raise FaceValidationRefused(
            f"The archive is not the one pinned: {digest['size']} bytes, "
            f"MD5 {digest['md5']}, SHA-256 {digest['sha256']}."
        )
    return digest


def extract_series(
    archive: zipfile.ZipFile,
    directory: os.PathLike[str] | str,
    series: Sequence[VhpSeries] | None = None,
) -> dict[str, int]:
    """Write the files of each axial CT series of ``series``, :data:`SERIES`
    where None, from the archive into ``<directory>/<folder>/``, and return
    how many each has.

    A member is a series' file where it is a DICOM file of the CT Image
    Storage SOP Class whose Series Number is the one that the series'
    folder, ``series-<number>``, names, and whose Image Type's third value
    is ``AXIAL``, which leaves out the localisers, a screen capture, and a
    structured report. It is written as ``<its folder's name>-<its name>``,
    since the export gives files of the same name in different folders.
    Members of ``__MACOSX/``, and members that are not DICOM files, such as
    the CD's viewer, are not read further.
    """
    root = pathlib.Path(directory)
    series = SERIES if series is None else series
    numbers = {each.uuid.removeprefix("series-"): each.uuid for each in series}
    counts = dict.fromkeys(numbers.values(), 0)
    for info in archive.infolist():
        if info.is_dir() or info.filename.startswith(_MACOS):
            continue
        data = archive.read(info)
        try:
            dataset = pydicom.dcmread(io.BytesIO(data), stop_before_pixels=True)
        except (pydicom.errors.InvalidDicomError, EOFError, ValueError):
            continue
        folder = numbers.get(str(dataset.get("SeriesNumber", "")))
        image_type = list(dataset.get("ImageType", []))
        if (
            folder is None
            or dataset.get("SOPClassUID") != CT_IMAGE_STORAGE
            or len(image_type) < 3
            or image_type[2] != "AXIAL"
        ):
            continue
        parts = info.filename.split("/")
        name = f"{parts[-2] if len(parts) > 1 else ''}-{parts[-1]}"
        (root / folder).mkdir(parents=True, exist_ok=True)
        (root / folder / name).write_bytes(data)
        counts[folder] += 1
    return counts


def check_keating(
    archive: os.PathLike[str] | str,
    renders: os.PathLike[str] | str | None = None,
    series: Sequence[VhpSeries] | None = None,
) -> dict[str, Any]:
    """Check each series, as the module describes.

    Parameters
    ----------
    archive
        The record's ZIP file, unchanged.
    renders
        A directory for the renders, or None for none.
    series
        The series to check; :data:`SERIES` where None.

    Raises
    ------
    FaceValidationRefused
        If the archive, or a series' files, are not those pinned.
    """
    series = SERIES if series is None else tuple(series)
    digest = verify_archive(archive)
    with tempfile.TemporaryDirectory() as scratch:
        root = pathlib.Path(scratch)
        try:
            with zipfile.ZipFile(archive) as opened:
                extract_series(opened, root, series)
        except (OSError, zipfile.BadZipFile):
            raise FaceValidationRefused(
                "The archive is not a readable ZIP file."
            ) from None
        # Every series is verified before any is checked, so that nothing
        # is rendered from a set that is refused.
        for each in series:
            folder = root / each.uuid
            count, files = manifest_digest(folder) if folder.is_dir() else (0, "none")
            if (count, files) != (each.files, each.sha256):
                raise FaceValidationRefused(
                    f"Series {each.uuid} is not the one pinned: {count} files, "
                    f"digest {files}."
                )
        checked = [
            check_series(each, root / each.uuid, renders, CREDIT) for each in series
        ]
    return {
        "format": FORMAT,
        "source": {
            "record": RECORD,
            "record_doi": RECORD_DOI,
            "file": ARCHIVE,
            "size": digest["size"],
            "md5": digest["md5"],
            "sha256": digest["sha256"],
            "licence": LICENCE,
            "licence_url": LICENCE_URL,
            "attribution": ATTRIBUTION,
            "notice": NOTICE,
        },
        "held_out": HELD_OUT,
        "reference": {
            "radius_mm": REFERENCE_RADIUS,
            "tolerance_mm": REFERENCE_TOLERANCE,
            "core_mm": CORE,
            "shell_mm": list(SHELL),
        },
        "software": _software(),
        "settings": _settings(),
        "series": checked,
    }
