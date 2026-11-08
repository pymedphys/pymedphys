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

"""The face block and CT defacing, checked against PDDCA's optic nerves
(D-054).

The Public Domain Database for Computational Anatomy (PDDCA), version
1.4.1, holds the head and neck radiotherapy planning CTs of 48 patients of
the RTOG 0522 trial, with expert masks of the brainstem, chiasm, mandible,
optic nerves, parotids, and submandibular glands, curated for the MICCAI
2015 head and neck auto-segmentation challenge (:data:`PDDCA`). Its NRRD
files are re-hosted on Zenodo in three ZIP files (:data:`PARTS`), which
give its licence as CC BY 3.0, as first distributed. TCIA now distributes
the trial's images under controlled access, since they could be used to
reconstruct a face, so this check, like the HaN-Seg check, writes only
counts that name no case and no value, and renders nothing. Its cases are
held-out evidence: the finder's settings were not set from them and are
not to be tuned to them.

Each case is measured as
:func:`~pymedphys._dicom.deidentify.face_validation.measure_case` measures
HaN-Seg's: the finder's outcome, by the reasons that a run counts, how the
CT is stored, and, where the series is defaced, the share of each organ's
voxels written as air. PDDCA has no masks of the eyes. Each optic nerve
runs back from its globe, so the anterior tip of each nerve's mask, its
voxel farthest towards the patient's anterior, corroborates where that
side's globe lies, independently of the image, though it measures no
globe-centre error, and an incomplete or inaccurate mask moves it too:
where the series is defaced and both nerves' masks are given, the
distance from each globe found to its side's tip, how far the tip lies
behind the globe along the block's anterior, and whether the globes found
were taken for the other side's are measured and counted in fixed bins
(:func:`summarise`).
"""

from __future__ import annotations

import collections
import dataclasses
import functools
import pathlib
import re
import zipfile
from collections.abc import Mapping, Sequence
from typing import Any

from . import face_validation, nrrd
from .face_validation import (
    Bins,
    CaseMeasures,
    CaseNotMeasured,
    FaceValidationRefused,
    _NotMeasured,
)

FORMAT = "pymedphys-deid-face-validation-pddca/1"
# The optic nerves' masks, the patient's right first.
NERVES = ("OpticNerve_R", "OpticNerve_L")
HELD_OUT = (
    "Held-out evidence: the face block finder's settings were not set from "
    "these scans and are not to be tuned to them."
)
PDDCA = {
    "name": "PDDCA",
    "version": "1.4.1",
    "licence": "CC BY 3.0",
    "citation": (
        "P. F. Raudaschl, P. Zaffino, G. C. Sharp, M. F. Spadea, and others, "
        '"Evaluation of segmentation methods on head and neck CT: '
        'Auto-segmentation challenge 2015", Medical Physics, 2017, '
        "doi:10.1002/mp.12197"
    ),
}


@dataclasses.dataclass(frozen=True)
class Part:
    """One of the data set's ZIP files on Zenodo, with the size and MD5
    that its record gives and the SHA-256 of the same file, downloaded on
    1 November 2026."""

    doi: str
    file: str
    size: int
    md5: str
    sha256: str


PARTS = (
    Part(
        "10.5281/zenodo.19657912",
        "PDDCA-1.4.1_part1.zip",
        509880384,
        "141d64efeb23218cd94c3492cabdba9f",
        "5b47b94f1e6aaad0a10c694906bd40ee8bcfc701e6d3bcbe3f12005815b721ef",
    ),
    Part(
        "10.5281/zenodo.19658040",
        "PDDCA-1.4.1_part2.zip",
        592862395,
        "5ab957cb1ec66b51c1d812a3bb8a75ba",
        "a5354e5373050f958e2696088a24f25f72361844d8b0d6988c16a3c989fd5659",
    ),
    Part(
        "10.5281/zenodo.19658102",
        "PDDCA-1.4.1_part3.zip",
        522438423,
        "f4653461de6e7fa92c4a7ce02c457a8e",
        "58bc70db301d3f0fd2e856a33e7d2be929859bc5b1a37d7c83a47f2bbe6a7fb6",
    ),
)
NERVE_TIP = Bins("mm", (0.0, 5.0, 10.0, 12.5, 15.0, 17.5, 20.0, 25.0, 30.0))
NERVE_TIP_BEHIND = Bins("mm", (-5.0, 0.0, 5.0, 10.0, 15.0, 20.0, 25.0), below=True)
_CT = re.compile(r"(?:.*/)?([^/]+)/img\.nrrd")
_ORGAN = re.compile(r"(?:.*/)?([^/]+)/structures/(\w+)\.nrrd")


@dataclasses.dataclass(frozen=True, repr=False)
class _Case:
    """The members of one case, in one of the ZIP files."""

    ct: zipfile.ZipInfo | None
    organs: Mapping[str, zipfile.ZipInfo]


def pddca_cases(archive: zipfile.ZipFile) -> list[_Case]:
    """The cases of one of the ZIP files, by directory: each case's CT, and
    its organs' masks by name, as ``<case>/img.nrrd`` and
    ``<case>/structures/<name>.nrrd`` name them. Its landmarks are not
    read."""
    cts: dict[str, zipfile.ZipInfo] = {}
    organs: dict[str, dict[str, zipfile.ZipInfo]] = collections.defaultdict(dict)
    for info in archive.infolist():
        if (match := _CT.fullmatch(info.filename)) is not None:
            cts[info.filename.rpartition("/")[0]] = info
        elif (match := _ORGAN.fullmatch(info.filename)) is not None:
            directory = info.filename.rpartition("/")[0].rpartition("/")[0]
            organs[directory][match[2]] = info
    return [
        _Case(cts.get(directory), dict(sorted(organs[directory].items())))
        for directory in sorted({*cts, *organs})
    ]


def check_pddca(
    paths: Sequence[pathlib.Path], parts: Sequence[Part] = PARTS
) -> dict[str, Any]:
    """Check the face block and CT defacing against PDDCA's masks.

    Parameters
    ----------
    paths : sequence of pathlib.Path
        The data set's ZIP files, in the order of ``parts``.
    parts : sequence of Part
        What each file must be; :data:`PARTS` where not given.

    Returns
    -------
    dict
        :func:`summarise`'s counts of the cases of every file.

    Raises
    ------
    FaceValidationRefused
        Where the files are not as many as the parts, a file's size, MD5,
        or SHA-256 differs from its part's, a file is not a ZIP file, or
        the files hold no case.
    """
    if len(paths) != len(parts):
        raise FaceValidationRefused(f"The check takes {len(parts)} ZIP files.")
    files = []
    for path, part in zip(paths, parts):
        try:
            digest = face_validation.file_digest(path)
        except OSError:
            raise FaceValidationRefused(f"{part.file} cannot be read.") from None
        if digest != {"size": part.size, "md5": part.md5, "sha256": part.sha256}:
            raise FaceValidationRefused(
                f"The file given as {part.file} is not the one pinned: "
                f"{digest['size']} bytes, MD5 {digest['md5']}, SHA-256 "
                f"{digest['sha256']}."
            )
        files.append({"doi": part.doi, "file": part.file, **digest})
    cases: list[CaseMeasures | CaseNotMeasured] = []
    for path in paths:
        cases += measure_pddca(path)
    if not cases:
        raise FaceValidationRefused("The ZIP files hold no PDDCA case.")
    return summarise(cases, {**PDDCA, "files": files})


def measure_pddca(path: pathlib.Path) -> list[CaseMeasures | CaseNotMeasured]:
    """Measure each case of one of the ZIP files, in the order of their
    directories, reading each member without extracting it.

    Raises
    ------
    FaceValidationRefused
        Where the file is not a ZIP file.
    """
    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile):
        raise FaceValidationRefused("A file is not a readable ZIP file.") from None
    with archive:
        return [_measured(archive, case) for case in pddca_cases(archive)]


def _measured(archive: zipfile.ZipFile, case: _Case) -> CaseMeasures | CaseNotMeasured:
    """One case's measures, or why it has none."""
    if case.ct is None:
        return CaseNotMeasured("ct-missing")
    try:
        try:
            ct = _read(archive, case.ct)
        except nrrd.NrrdRefused as refused:
            return CaseNotMeasured(f"ct-not-read/{refused.problem.value}")
        organs = {
            name: functools.partial(_read, archive, info)
            for name, info in case.organs.items()
        }
        return face_validation.measure_case(ct, organs, eyes=None, nerves=NERVES)
    except _NotMeasured as unusable:
        return CaseNotMeasured(unusable.reason)
    # Anything else that a case raises is counted, by where, rather than
    # stopping the check; its message, which could quote a value, is
    # dropped.
    except Exception as error:  # pylint: disable = broad-exception-caught
        return CaseNotMeasured("crashed", face_validation.crash_site(error))


def _read(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> nrrd.Volume:
    with archive.open(info) as stream:
        return nrrd.read_nrrd(stream)


def summarise(
    cases: Sequence[CaseMeasures | CaseNotMeasured], data: Mapping[str, Any]
) -> dict[str, Any]:
    """Return the cases' counts for JSON: those of
    :func:`~pymedphys._dicom.deidentify.face_validation.summarise`, labelled
    :data:`FORMAT`, with the counts of the globes found against the optic
    nerves' anterior tips.

    Parameters
    ----------
    cases : sequence of CaseMeasures or CaseNotMeasured
    data : mapping
        What names the data set and its files: its name, version, licence,
        and citation, and each file's DOI, name, size, MD5, and SHA-256.
    """
    summary = face_validation.summarise(cases, data)
    defaced = [
        case
        for case in cases
        if isinstance(case, CaseMeasures) and case.outcome == "defaced"
    ]
    against = [case for case in defaced if case.nerve_tips]
    return {
        **summary,
        "format": FORMAT,
        "held_out": HELD_OUT,
        "optic_nerves_of_defaced_series": {
            "series": len(against),
            "without_both_nerves": len(defaced) - len(against),
            "sides_swapped": sum(bool(case.nerve_sides_swapped) for case in against),
            "globe_to_nerve_tip": NERVE_TIP.counts(
                distance for case in against for distance in case.nerve_tips
            ),
            "nerve_tip_behind_globe": NERVE_TIP_BEHIND.counts(
                behind for case in against for behind in case.nerve_tips_behind
            ),
        },
    }
