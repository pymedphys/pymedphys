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

"""Full results and previews of the text detector on phantoms alone (D-056).

The evaluation's summary (:mod:`.text_evaluation`) gives counts alone, since
most of its images are of real patients. Images of a phantom are not, so for
them this module also gives, for each case, a report of every frame's
regions and texts (:data:`PHANTOM_REPORT_FORMAT`) and previews: PNG crops of
each region away from text and of each injected text not fully covered, and
an overview of each frame that has either, with the boxes outlined.

Only phantoms reach it, by three gates that do not depend on a caller's flag:

type
    :func:`phantom_report` takes only a :class:`PhantomDicomCase` or a
    synthetic :class:`~.text_evaluation_phantoms.PhantomCase`, and refuses
    any other source, such as a :class:`~.text_evaluation_sources.DicomCase`
    of a patient collection;
allow-list
    a :class:`PhantomDicomCase` is only of a collection in
    :data:`PHANTOM_COLLECTIONS`, each a collection of physical phantoms, and
    reads only files that name that collection as the archive's project in
    the private block that The Cancer Imaging Archive's de-identification
    adds, and, where the entry lists them, only the Patient IDs of its
    phantoms. A file that fails is skipped by a code, never read;
tier
    each frame must be of tier T1 or T2 (:data:`PREVIEWED_TIERS`), so that
    no frame of a patient is drawn, even with synthetic text burned in.

Each entry carries the collection's citation, DOI, and licence, which every
report and the ``ATTRIBUTION.md`` that :func:`write_phantom_reports` writes
give, with the changes made to the images, as their licences ask.
"""

from __future__ import annotations

import dataclasses
import json
import pathlib
import struct
import types
import zlib
from collections.abc import Callable, Iterator, Mapping, Sequence
from typing import Any

from pymedphys._imports import numpy as np

from .source import SourceRefused, read_source
from .text_detection import TextBox
from .text_evaluation import INK_LEVEL, EvaluationSettings
from .text_evaluation_detector import MeasuredDetector
from .text_evaluation_frames import BurnedText, EvaluationFrame, EvaluationRefused
from .text_evaluation_injection import inject
from .text_evaluation_phantoms import COLLECTION as SYNTHETIC_COLLECTION
from .text_evaluation_phantoms import PhantomCase
from .text_evaluation_sources import (
    DicomCase,
    Skipped,
    SkippedFiles,
    dicom_folder_cases,
    dicom_frames,
)

PHANTOM_REPORT_FORMAT = "pymedphys-deid-text-detector-phantom-report/1"
# The tiers of the corpus whose frames may be previewed: wholly synthetic
# frames and allow-listed phantoms' frames.
PREVIEWED_TIERS = frozenset({"T1", "T2"})
# The private block that The Cancer Imaging Archive's de-identification adds,
# and its Project Name, the collection, within it.
_CTP_GROUP = 0x0013
_CTP_CREATOR = "CTP"
_CTP_PROJECT = 0x10
CHANGES = (
    "Frames were cropped, windowed, rescaled, and outlined to show the text "
    "detector's regions; where a plan was given, synthetic text was burned "
    "into copies of them."
)


@dataclasses.dataclass(frozen=True)
class PhantomCollection:
    """A collection of phantom images, and how to credit it.

    Attributes
    ----------
    name : str
        The collection's name, as its archive gives it.
    citation : str
    doi : str
    licence, licence_url : str
    project_names : tuple of str
        The Project Names that its files may carry in the archive's private
        block; a file with another, or none, is not read.
    patients : frozenset of str or None
        The Patient IDs of its phantoms, where it holds anything else, such
        as images derived from patients; None where every subject is a
        phantom.
    """

    name: str
    citation: str
    doi: str
    licence: str
    licence_url: str
    project_names: tuple[str, ...]
    patients: frozenset[str] | None = None

    def attribution(self) -> dict[str, str]:
        """How the collection is credited, as reports give it."""
        return {
            "collection": self.name,
            "citation": self.citation,
            "doi": self.doi,
            "licence": self.licence,
            "licence_url": self.licence_url,
            "changes": CHANGES,
        }


_CC_BY_3 = "https://creativecommons.org/licenses/by/3.0/"
_CC_BY_4 = "https://creativecommons.org/licenses/by/4.0/"

# Collections of phantoms whose images may be previewed. Only a collection
# whose every subject reaching it is a phantom belongs here: MRI-DIR also
# holds synthetic images derived from patients' scans, so it admits only
# the Patient IDs of its porcine phantom, which are listed once verified;
# until then it admits none.
PHANTOM_COLLECTIONS: Mapping[str, PhantomCollection] = types.MappingProxyType(
    {
        each.name: each
        for each in (
            PhantomCollection(
                name="CC-Radiomics-Phantom-3",
                citation=(
                    "Ger R, Zhou S, Chi P-C, Lee H, Layman R, Jones K, Goff DL, "
                    "Fuller CD, Howell RM, Heng L, Stafford RJ, Court LE, Mackin D. "
                    "(2019). Data from CT Phantom Scans for Head, Chest, and "
                    "Controlled Protocols on 100 Scanners (CC-Radiomics-Phantom-3) "
                    "(Version 1). The Cancer Imaging Archive."
                ),
                doi="10.7937/tcia.2019.j71i4fah",
                licence="CC BY 3.0",
                licence_url=_CC_BY_3,
                project_names=("CC-Radiomics-Phantom-3",),
            ),
            PhantomCollection(
                name="RIDER PHANTOM PET-CT",
                citation=(
                    "Muzi P, Wanner M, Kinahan P. (2015). Data From RIDER PHANTOM "
                    "PET-CT (Version 2). The Cancer Imaging Archive."
                ),
                doi="10.7937/K9/TCIA.2015.8WG2KN4W",
                licence="CC BY 3.0",
                licence_url=_CC_BY_3,
                project_names=("RIDER PHANTOM PET-CT",),
            ),
            PhantomCollection(
                name="MRI-DIR",
                citation=(
                    "Ger RB, Yang J, Ding Y, Jacobsen MC, Cardenas CE, Fuller CD, "
                    "Howell RM, Li H, Stafford RJ, Zhou S, Court L. (2018). Data "
                    "from Synthetic and Phantom MR Images for Determining "
                    "Deformable Image Registration Accuracy (MRI-DIR) (Version 1). "
                    "The Cancer Imaging Archive."
                ),
                doi="10.7937/K9/TCIA.2018.3f08iejt",
                licence="CC BY 4.0",
                licence_url=_CC_BY_4,
                project_names=("MRI-DIR",),
                patients=frozenset(),
            ),
        )
    }
)
SYNTHETIC = PhantomCollection(
    name=SYNTHETIC_COLLECTION,
    citation="PyMedPhys's synthetic phantoms, drawn by the evaluation itself.",
    doi="none",
    licence="Apache-2.0",
    licence_url="https://www.apache.org/licenses/LICENSE-2.0",
    project_names=(),
)


def phantom_collection(name: str) -> PhantomCollection:
    """The allow-listed collection of this name.

    Raises
    ------
    EvaluationRefused
        If no collection of phantoms has the name.
    """
    found = PHANTOM_COLLECTIONS.get(name)
    if found is None:
        raise EvaluationRefused("Only an allow-listed phantom collection is previewed.")
    return found


def _not_phantom(data: bytes, phantom: PhantomCollection) -> str | None:
    """Why a file is not of the collection's phantoms, or None if it is."""
    try:
        dataset = read_source(data).dataset()
    except SourceRefused:
        return "not-read"
    try:
        block = dataset.private_block(_CTP_GROUP, _CTP_CREATOR)
        project = str(block[_CTP_PROJECT].value).strip()
    # pydicom raises KeyError where the block or element is absent, and
    # others for a value it cannot read; each means the project is unknown.
    except Exception:  # pylint: disable = broad-exception-caught
        return "not-phantom/no-project"
    if project not in phantom.project_names:
        return "not-phantom/other-project"
    if phantom.patients is not None:
        patient = dataset.get("PatientID")
        if patient is None or str(patient).strip() not in phantom.patients:
            return "not-phantom/patient-not-listed"
    return None


@dataclasses.dataclass(frozen=True)
class PhantomDicomCase:
    """DICOM files of an allow-listed phantom collection, read as a
    :class:`~.text_evaluation_sources.DicomCase` reads them, except that a
    file not of the collection's phantoms is skipped unread, by a code.

    Attributes
    ----------
    phantom : PhantomCollection
        An entry of :data:`PHANTOM_COLLECTIONS`, and no other.
    case : str
    paths : tuple of str
    """

    phantom: PhantomCollection
    case: str
    paths: tuple[str, ...]

    def __post_init__(self):
        if PHANTOM_COLLECTIONS.get(self.phantom.name) != self.phantom:
            raise EvaluationRefused(
                "Only an allow-listed phantom collection is previewed."
            )

    @property
    def collection(self) -> str:
        return self.phantom.name

    def read(self) -> Iterator[EvaluationFrame | Skipped]:
        number = 0
        for path in self.paths:
            try:
                data = pathlib.Path(path).read_bytes()
            except OSError:
                yield Skipped("not-opened")
                continue
            reason = _not_phantom(data, self.phantom)
            if reason is not None:
                yield Skipped(reason)
                continue
            found = dicom_frames(
                data,
                collection=self.collection,
                case=self.case,
                first=number,
                tier="T2",
            )
            if isinstance(found, Skipped):
                yield found
                continue
            number += len(found)
            yield from found


def phantom_dicom_cases(
    root: pathlib.Path | str,
    name: str,
    *,
    group_by: str = "series",
    sop_classes: Sequence[str] | None = None,
) -> tuple[PhantomDicomCase | SkippedFiles, ...]:
    """The DICOM files under a folder as cases of an allow-listed phantom
    collection, grouped and named as
    :func:`~.text_evaluation_sources.dicom_folder_cases` groups them; they
    serve both the counts of :func:`~.text_evaluation.evaluate` and the
    reports here."""
    phantom = phantom_collection(name)
    cases: list[PhantomDicomCase | SkippedFiles] = []
    for each in dicom_folder_cases(
        root,
        collection=phantom.name,
        group_by=group_by,
        sop_classes=sop_classes,
        known_text="none",
    ):
        if isinstance(each, DicomCase):
            cases.append(PhantomDicomCase(phantom, each.case, each.paths))
        else:
            cases.append(each)
    return tuple(cases)


PhantomSource = PhantomDicomCase | PhantomCase


def _admitted(case: object) -> PhantomCollection:
    """The collection of a phantom source; any other source is refused."""
    if isinstance(case, PhantomDicomCase):
        return phantom_collection(case.phantom.name)
    if isinstance(case, PhantomCase):
        return SYNTHETIC
    raise EvaluationRefused("Only a phantom source is reported in full.")


@dataclasses.dataclass(frozen=True)
class PreviewSettings:
    """How previews are drawn.

    Attributes
    ----------
    point : int
        The grid point whose boxes the previews show.
    margin : int
        Frame pixels around a crop's box.
    min_side : int
        The least shorter side of a crop, in PNG pixels, reached by an
        integer enlargement of at most 8.
    overview_side : int
        The greatest side of an overview, in PNG pixels, reached by taking
        every nth pixel.
    max_previews : int
        The most crops for one case; the rest are counted, not drawn.
    """

    point: int = 0
    margin: int = 16
    min_side: int = 96
    overview_side: int = 512
    max_previews: int = 200


def phantom_report(
    case: PhantomSource,
    detector: MeasuredDetector,
    settings: EvaluationSettings,
    out: pathlib.Path | str,
    previews: PreviewSettings = PreviewSettings(),
) -> dict[str, Any]:
    """Report one phantom case in full, and write its previews.

    Writes ``report.json`` and ``previews/*.png`` under ``out``, and
    returns the report: for each frame as read and, where the settings give
    a plan, with its text burned in, the boxes of every grid point, the
    regions away from text, and each text's extent, strata, and whether
    each point covers it fully.

    Raises
    ------
    EvaluationRefused
        For a source that is not a phantom's, or a point not in the grid.
    """
    phantom = _admitted(case)
    if not 0 <= previews.point < len(settings.points):
        raise EvaluationRefused("The previewed point must be a point of the grid.")
    out = pathlib.Path(out)
    (out / "previews").mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "format": PHANTOM_REPORT_FORMAT,
        "attribution": phantom.attribution(),
        "case": case.case,
        "detector": dict(detector.method),
        "points": [point.described() for point in settings.points],
        "previewed_point": previews.point,
        "frames": [],
        "skipped": {},
        "previews_not_drawn": 0,
    }
    drawn = 0
    for item in case.read():
        if isinstance(item, Skipped):
            report["skipped"][item.reason] = report["skipped"].get(item.reason, 0) + 1
            continue
        if item.collection != phantom.name:
            raise EvaluationRefused("A frame is not of the case's collection.")
        # A third gate, on each frame: only a wholly synthetic frame, T1, or
        # an allow-listed phantom's, T2, is drawn; never a patient's, even
        # with synthetic text burned into it.
        if item.tier not in PREVIEWED_TIERS:
            raise EvaluationRefused("Only a phantom's frame is previewed.")
        passes = [("as read", item)]
        if settings.plan is not None and not item.rgb:
            injected = inject(item, settings.plan).frame
            if len(injected.texts) > len(item.texts):
                passes.append(("with injected text", injected))
        for name, frame in passes:
            entry, crops = _frame_entry(frame, name, detector, settings, previews)
            for label, image in crops:
                if drawn >= previews.max_previews:
                    report["previews_not_drawn"] += 1
                    continue
                kind = "read" if name == "as read" else "injected"
                file = f"frame-{frame.number:05d}-{kind}-{label}.png"
                (out / "previews" / file).write_bytes(png(image))
                entry["previews"].append(f"previews/{file}")
                drawn += 1
            report["frames"].append(entry)
    (out / "report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    return report


def _frame_entry(
    frame: EvaluationFrame,
    name: str,
    detector: MeasuredDetector,
    settings: EvaluationSettings,
    previews: PreviewSettings,
) -> tuple[dict[str, Any], list[tuple[str, np.ndarray]]]:
    shape = frame.shape
    boxes_of_points = detector.boxes_of_points(frame, settings.points)
    zones = [text.zone(shape) for text in frame.texts]
    inks = [text.ink(shape, INK_LEVEL) for text in frame.texts]
    entry: dict[str, Any] = {
        "number": frame.number,
        "pass": name,
        "iod": frame.iod,
        "modality": frame.modality,
        "shape": list(shape),
        "pixel_spacing": frame.pixel_spacing,
        "boxes": [[_box(box) for box in boxes] for boxes in boxes_of_points],
        "away_from_text": [
            [_box(box) for box in boxes if not _meets_any(box, zones)]
            for boxes in boxes_of_points
        ],
        "texts": [],
        "previews": [],
    }
    for text, ink in zip(frame.texts, inks):
        entry["texts"].append(
            {
                "extent": _box(text.extent),
                "strata": dict(text.strata),
                "fully_covered": [
                    _fully_covered(boxes, ink, shape) for boxes in boxes_of_points
                ],
            }
        )
    shown = boxes_of_points[previews.point]
    away = [box for box in shown if not _meets_any(box, zones)]
    missed = [
        text
        for text, ink in zip(frame.texts, inks)
        if not _fully_covered(shown, ink, shape)
    ]
    crops: list[tuple[str, np.ndarray]] = []
    if not (away or missed):
        return entry, crops
    values = frame.luminance()
    crops.append(("overview", _overview(values, shown, frame.texts, previews)))
    for index, box in enumerate(away):
        crops.append(
            (f"region-{index:03d}", _crop(values, box, shown, frame.texts, previews))
        )
    for index, text in enumerate(missed):
        crops.append(
            (
                f"missed-{index:03d}",
                _crop(values, text.extent, shown, frame.texts, previews),
            )
        )
    return entry, crops


def _box(box: TextBox) -> list[int]:
    return [box.top, box.left, box.bottom, box.right]


def _meets_any(box: TextBox, zones: Sequence[TextBox]) -> bool:
    return any(
        box.top < zone.bottom
        and zone.top < box.bottom
        and box.left < zone.right
        and zone.left < box.right
        for zone in zones
    )


def _fully_covered(
    boxes: Sequence[TextBox], ink: np.ndarray, shape: tuple[int, int]
) -> bool:
    covered = np.zeros(shape, bool)
    for box in boxes:
        covered[box.top : box.bottom, box.left : box.right] = True
    return bool(covered[ink].all())


# Outline colours: a region of the detector, and a text's extent.
_REGION = (255, 64, 64)
_TEXT = (255, 220, 0)


def _windowed(values: np.ndarray) -> np.ndarray:
    """Grey levels from 0 to 255 between the values' 0.5th and 99.5th
    percentiles."""
    low, high = np.percentile(values, (0.5, 99.5))
    if high <= low:
        high = low + 1
    grey = np.clip((values - low) / (high - low), 0, 1) * 255
    return np.repeat(np.rint(grey).astype(np.uint8)[..., None], 3, axis=2)


def _outline(
    image: np.ndarray, box: TextBox, offset: tuple[int, int], scale: int, colour
) -> None:
    """Draw a box's edge, in frame pixels shifted by ``offset``, on an image
    enlarged ``scale`` times, clipped to it."""
    rows, columns = image.shape[:2]
    top = (box.top - offset[0]) * scale
    left = (box.left - offset[1]) * scale
    bottom = (box.bottom - offset[0]) * scale - 1
    right = (box.right - offset[1]) * scale - 1
    if bottom < 0 or right < 0 or top >= rows or left >= columns:
        return
    clipped_top, clipped_left = max(top, 0), max(left, 0)
    clipped_bottom, clipped_right = min(bottom, rows - 1), min(right, columns - 1)
    for row in (top, bottom):
        if 0 <= row < rows:
            image[row, clipped_left : clipped_right + 1] = colour
    for column in (left, right):
        if 0 <= column < columns:
            image[clipped_top : clipped_bottom + 1, column] = colour


def _crop(
    values: np.ndarray,
    box: TextBox,
    boxes: Sequence[TextBox],
    texts: Sequence[BurnedText],
    previews: PreviewSettings,
) -> np.ndarray:
    top = max(0, box.top - previews.margin)
    left = max(0, box.left - previews.margin)
    bottom = min(values.shape[0], box.bottom + previews.margin)
    right = min(values.shape[1], box.right + previews.margin)
    window = values[top:bottom, left:right]
    scale = int(min(8, max(1, -(-previews.min_side // min(window.shape)))))
    image = _windowed(window)
    image = np.repeat(np.repeat(image, scale, axis=0), scale, axis=1)
    for text in texts:
        _outline(image, text.extent, (top, left), scale, _TEXT)
    for each in boxes:
        _outline(image, each, (top, left), scale, _REGION)
    return image


def _overview(
    values: np.ndarray,
    boxes: Sequence[TextBox],
    texts: Sequence[BurnedText],
    previews: PreviewSettings,
) -> np.ndarray:
    step = max(1, -(-max(values.shape) // previews.overview_side))
    image = _windowed(values)[::step, ::step].copy()
    for text in texts:
        _outline(image, _shrunk(text.extent, step), (0, 0), 1, _TEXT)
    for each in boxes:
        _outline(image, _shrunk(each, step), (0, 0), 1, _REGION)
    return image


def _shrunk(box: TextBox, step: int) -> TextBox:
    return TextBox(
        box.top // step,
        box.left // step,
        max(box.top // step + 1, -(-box.bottom // step)),
        max(box.left // step + 1, -(-box.right // step)),
    )


def png(image: np.ndarray) -> bytes:
    """An 8-bit RGB image, rows by columns by 3, as a PNG file."""
    image = np.ascontiguousarray(image, dtype=np.uint8)
    if image.ndim != 3 or image.shape[2] != 3 or not image.size:
        raise EvaluationRefused("A preview must be rows by columns by 3.")
    rows, columns = image.shape[:2]
    raw = b"".join(b"\x00" + image[row].tobytes() for row in range(rows))

    def chunk(kind: bytes, body: bytes) -> bytes:
        return (
            struct.pack(">I", len(body))
            + kind
            + body
            + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", columns, rows, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def attribution_markdown(collections: Sequence[PhantomCollection]) -> str:
    """``ATTRIBUTION.md``: the citation, DOI, licence, and changes of each
    collection whose images the previews show."""
    lines = [
        "# Attribution",
        "",
        "The previews show images from these collections, changed as each entry says.",
        "",
    ]
    for each in sorted(set(collections), key=lambda entry: entry.name):
        lines += [
            f"## {each.name}",
            "",
            f"- Citation: {each.citation}",
            f"- DOI: {each.doi if each.doi == 'none' else 'https://doi.org/' + each.doi}",
            f"- Licence: [{each.licence}]({each.licence_url})",
            f"- Changes: {CHANGES}",
            "",
        ]
    return "\n".join(lines).rstrip("\n") + "\n"


def write_phantom_reports(
    cases: Sequence[PhantomSource | SkippedFiles],
    detector: Callable[[], MeasuredDetector],
    settings: EvaluationSettings,
    out: pathlib.Path | str,
    previews: PreviewSettings = PreviewSettings(),
) -> dict[str, Any]:
    """Report each phantom case under ``out``, one folder each, and write
    ``ATTRIBUTION.md`` and ``index.json``, which lists the cases and counts
    the files skipped.

    Raises
    ------
    EvaluationRefused
        If any case is not a phantom's, before anything is written.
    """
    sources: list[tuple[PhantomSource, PhantomCollection]] = []
    skipped: list[SkippedFiles] = []
    for each in cases:
        if isinstance(each, SkippedFiles):
            phantom_collection(each.collection)
            skipped.append(each)
        else:
            sources.append((each, _admitted(each)))
    out = pathlib.Path(out)
    out.mkdir(parents=True, exist_ok=True)
    made = detector()
    index: dict[str, Any] = {
        "format": PHANTOM_REPORT_FORMAT,
        "cases": [],
        "skipped": {},
    }
    for each in skipped:
        index["skipped"][each.reason] = (
            index["skipped"].get(each.reason, 0) + each.count
        )
    used: list[PhantomCollection] = []
    for each, phantom in sources:
        used.append(phantom)
        folder = pathlib.Path(_folder(phantom.name)) / _folder(each.case)
        report = phantom_report(each, made, settings, out / folder, previews)
        for reason, count in report["skipped"].items():
            index["skipped"][reason] = index["skipped"].get(reason, 0) + count
        index["cases"].append(
            {
                "collection": phantom.name,
                "case": each.case,
                "report": f"{folder.as_posix()}/report.json",
                "frames": len(report["frames"]),
                "previews": sum(len(frame["previews"]) for frame in report["frames"]),
            }
        )
    (out / "ATTRIBUTION.md").write_text(attribution_markdown(used), encoding="utf-8")
    (out / "index.json").write_text(json.dumps(index, indent=1), encoding="utf-8")
    return index


def _folder(name: str) -> str:
    """A name made safe as one folder's name."""
    return "".join(each if each.isalnum() or each in "-_." else "-" for each in name)
