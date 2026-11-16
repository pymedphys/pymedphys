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

"""Cases of frames for the text detector's evaluation (D-056).

A case is what the split keeps together and the uncertainty clusters by: a
series of DICOM files, a volume, or a phantom's frames. Each kind of case
reads its frames when asked, in a worker process where several run, and
gives each frame (:class:`~.text_evaluation_frames.EvaluationFrame`) or
why one could not be read (:class:`Skipped`), by a code that quotes no
value.

:class:`DicomCase`
    DICOM files, each read as a run reads a source (:func:`~.source.read_source`)
    and its frames taken as a run under the Clean Pixel Data Option gives
    them to the text detector: through :func:`~.pixel_cleaning.black_out`
    itself, decoded by the pinned plugins and with overlays in unused bits
    cleared, so that the frames searched are the frames a run would search.
    :func:`dicom_folder_cases` makes them from a folder, such as a clinic's
    own RT Images on its own machine, grouped by patient, study, or series,
    with what is known of their text and any boxes that someone drew around
    it (:class:`TextAnnotations`).
:class:`NrrdCase`
    One volume of an NRRD file in a ZIP file, such as HaN-Seg's, each slice
    a frame, as the Text Detector Check gives them.
:class:`~.text_evaluation_phantoms.PhantomCase`
    Synthetic frames.

Real patients' scans are read only on CI runners, under the project's data
rules, or on the machine of someone allowed to use them; nothing here
writes, logs, or returns a value of them other than the frames, which stay
in memory. A case's name is a digest, never a path or identifier.
"""

from __future__ import annotations

import csv
import dataclasses
import hashlib
import math
import pathlib
import zipfile
from collections.abc import Collection, Iterable, Iterator, Mapping, Sequence
from typing import Protocol, runtime_checkable

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom

from . import nrrd
from .pixel_cleaning import Layout, PixelDataRefused, black_out, overlay_planes
from .pixel_text_validation import hanseg_volumes
from .source import SourceRefused, read_source
from .text_detection import TextBox
from .text_evaluation_frames import (
    KNOWN_TEXT,
    TIERS,
    BurnedText,
    EvaluationFrame,
    EvaluationRefused,
)

PRIVATE_SOP_CLASS = "private SOP class"
UNKNOWN_SOP_CLASS = "unknown SOP class"
RT_IMAGE_STORAGE = "1.2.840.10008.5.1.4.1.1.481.1"
# How a folder's files are grouped into cases, which the split keeps
# together and the bootstrap resamples: by patient, so that no patient is
# in both parts, unless asked otherwise.
GROUPINGS = ("patient", "study", "series", "file")
_CASE_SALT = "pymedphys-text-detector-evaluation-case/1"
ANNOTATION_COLUMNS = ("sop_instance_uid", "frame", "top", "left", "bottom", "right")


@dataclasses.dataclass(frozen=True)
class Skipped:
    """Frames not read, for why: a code such as ``"not-read"``."""

    reason: str


@runtime_checkable
class CaseSource(Protocol):
    """A case, which reads its frames when asked.

    A source may also give a ``subject``, a private key of the patient its
    frames are of, which the split and the bootstrap read in place of its
    case (:func:`~.text_evaluation.subject_of`), so that one patient's
    cases are kept together.
    """

    @property
    def collection(self) -> str:
        """The collection, which the summary names."""

    @property
    def case(self) -> str:
        """The case, which the summary never names."""

    def read(self) -> Iterable[EvaluationFrame | Skipped]:
        """Each frame, in order, or why frames were not read."""


class _Frames:
    """A text finder that keeps each frame that a run gives it, and finds
    nothing, so that :func:`~.pixel_cleaning.black_out` gives the frames as
    a run searches them."""

    method: Mapping[str, object] = {"frames": "kept"}

    def __init__(self) -> None:
        self.frames: list[np.ndarray] = []

    def find(self, frame: np.ndarray) -> Sequence:
        self.frames.append(np.array(frame, copy=True))
        return ()


def dicom_frames(
    data: bytes,
    *,
    collection: str,
    case: str,
    first: int = 0,
    known_text: str = "none",
    annotations: TextAnnotations | None = None,
    tier: str = "none",
) -> list[EvaluationFrame] | Skipped:
    """The frames of one DICOM file's top-level Pixel Data, as a run gives
    them to the text detector, numbered from ``first``, or why there are
    none.

    Each frame's text is ``known_text``, unless ``annotations`` holds the
    instance, whose frames then hold the boxes drawn on them, and are
    ``"annotated"``. Each frame is of the corpus's ``tier``."""
    if known_text not in KNOWN_TEXT:
        raise EvaluationRefused("What is known of a frame's text must be known.")
    decoded = decoded_frames(data)
    if isinstance(decoded, Skipped):
        return decoded
    dataset, layout, stored_frames = decoded
    if layout.signed:
        stored_range = (
            -(1 << (layout.bits_stored - 1)),
            (1 << (layout.bits_stored - 1)) - 1,
        )
    else:
        stored_range = (0, (1 << layout.bits_stored) - 1)
    iod = _sop_class_name(dataset)
    modality = _text(dataset, "Modality") or "unknown"
    instance = _text(dataset, "SOPInstanceUID")
    annotated = (
        annotations
        if annotations is not None and instance in annotations.instances
        else None
    )
    frames = []
    for index, frame in enumerate(stored_frames):
        slope, intercept = _rescale(dataset, index)
        texts: tuple[BurnedText, ...] = ()
        if annotated is not None and instance is not None:
            try:
                texts = annotated.texts(instance, index, frame.shape[:2])
            except EvaluationRefused:
                return Skipped("annotation-outside-frame")
        frames.append(
            EvaluationFrame(
                stored=frame,
                collection=collection,
                case=case,
                iod=iod,
                modality=modality,
                pixel_spacing=_spacing(dataset, index),
                slope=slope,
                intercept=intercept,
                stored_range=stored_range,
                photometric=layout.photometric,
                number=first + index,
                texts=texts,
                known_text="annotated" if annotated is not None else known_text,
                tier=tier,
            )
        )
    return frames


def decoded_frames(
    data: bytes,
) -> tuple[pydicom.Dataset, Layout, list[np.ndarray]] | Skipped:
    """A DICOM file's data set, the layout of its top-level Pixel Data, and
    its frames of stored values, as a run gives them to the text detector:
    decoded by the pinned plugins, with overlays in unused bits cleared; or
    why there are none."""
    try:
        source = read_source(data)
        dataset = source.dataset()
    except SourceRefused:
        return Skipped("not-read")
    planes = overlay_planes(source, dataset)
    if planes is None:
        return Skipped("overlay-not-cleared")
    finder = _Frames()
    try:
        redaction = black_out(source, dataset, finder, overlays=planes)
    except PixelDataRefused as refused:
        return Skipped(f"pixel-data-refused/{refused.reason.value}")
    if redaction is None:
        return Skipped("no-pixel-data")
    # The evaluation reads frames of integer stored values, whose range Bits
    # Stored bounds; floating-point pixel data are not evaluated.
    if redaction.layout.floating:
        return Skipped("float-pixel-data")
    return dataset, redaction.layout, finder.frames


def _sop_class_name(dataset: pydicom.Dataset) -> str:
    """The name of the instance's SOP Class from pydicom's dictionary, as
    such names are not patient data, or a code for a private or unknown
    one."""
    value = _text(dataset, "SOPClassUID")
    if not value:
        return UNKNOWN_SOP_CLASS
    uid = pydicom.uid.UID(value)
    if uid.is_private:
        return PRIVATE_SOP_CLASS
    name = uid.name
    return name if name and name != str(uid) else UNKNOWN_SOP_CLASS


def _text(dataset: pydicom.Dataset, keyword: str) -> str | None:
    try:
        value = dataset.get(keyword)
    # pydicom converts a value when it is first read and raises many types
    # for one it cannot; such a value is treated as absent.
    except Exception:  # pylint: disable = broad-exception-caught
        return None
    return str(value).strip() if value not in (None, "") else None


def _numbers(item: pydicom.Dataset, keyword: str) -> list[float] | None:
    try:
        value = item.get(keyword)
        if value is None or value == "":
            return None
        many = isinstance(value, (list, tuple, pydicom.multival.MultiValue))
        numbers = [float(each) for each in (value if many else [value])]
    except Exception:  # pylint: disable = broad-exception-caught
        return None
    return numbers if numbers and all(np.isfinite(numbers)) else None


def _items(dataset: pydicom.Dataset, keyword: str) -> list[pydicom.Dataset]:
    try:
        value = dataset.get(keyword)
    except Exception:  # pylint: disable = broad-exception-caught
        return []
    return list(value) if isinstance(value, pydicom.Sequence) else []


def _functional_group(
    dataset: pydicom.Dataset, index: int, macro: str
) -> pydicom.Dataset | None:
    """The item of a functional group macro for one frame: per frame, else
    shared."""
    per_frame = _items(dataset, "PerFrameFunctionalGroupsSequence")
    groups = [per_frame[index]] if index < len(per_frame) else []
    groups += _items(dataset, "SharedFunctionalGroupsSequence")[:1]
    for group in groups:
        items = _items(group, macro)
        if items:
            return items[0]
    return None


def _spacing(dataset: pydicom.Dataset, index: int) -> float | None:
    """The larger spacing between a frame's pixels in millimetres: Pixel
    Spacing, from the Pixel Measures functional group for an enhanced
    image, else Image Plane Pixel Spacing for an RT Image, else Imager Pixel
    Spacing for a projection, or None."""
    measures = _functional_group(dataset, index, "PixelMeasuresSequence")
    for item, keyword in (
        (measures, "PixelSpacing"),
        (dataset, "PixelSpacing"),
        (dataset, "ImagePlanePixelSpacing"),
        (dataset, "ImagerPixelSpacing"),
    ):
        if item is None:
            continue
        numbers = _numbers(item, keyword)
        if numbers and len(numbers) == 2 and min(numbers) > 0:
            return max(numbers)
    return None


def _rescale(dataset: pydicom.Dataset, index: int) -> tuple[float, float]:
    """A frame's Rescale Slope and Intercept, from the Pixel Value
    Transformation functional group for an enhanced image, else the top
    level, else 1 and 0."""
    transformation = _functional_group(
        dataset, index, "PixelValueTransformationSequence"
    )
    for item in (transformation, dataset):
        if item is None:
            continue
        slope = _numbers(item, "RescaleSlope")
        intercept = _numbers(item, "RescaleIntercept")
        if slope and intercept and slope[0] != 0:
            return slope[0], intercept[0]
    return 1.0, 0.0


@dataclasses.dataclass(frozen=True)
class DicomCase:
    """A case of DICOM files, read in the order given, their frames
    numbered in turn.

    Attributes
    ----------
    collection : str
    case : str
        The series or patient, never published.
    paths : tuple of str
    known_text : str
        What is known of the text of its frames as read, one of
        :data:`~.text_evaluation_frames.KNOWN_TEXT`, except for annotated
        instances.
    annotations : TextAnnotations or None
        Boxes drawn around the text of some of its instances.
    tier : str
        The tier of the corpus, one of
        :data:`~.text_evaluation_frames.TIERS`.
    subject : str or None
        Its patient, by a salted SHA-256 (:func:`case_name`), where its
        files are grouped more finely than by patient and all name one;
        None where its case is its subject.
    """

    collection: str
    case: str
    paths: tuple[str, ...]
    known_text: str = "none"
    annotations: TextAnnotations | None = None
    tier: str = "none"
    subject: str | None = dataclasses.field(default=None, repr=False)

    def read(self) -> Iterator[EvaluationFrame | Skipped]:
        number = 0
        for path in self.paths:
            try:
                data = pathlib.Path(path).read_bytes()
            except OSError:
                yield Skipped("not-opened")
                continue
            found = dicom_frames(
                data,
                collection=self.collection,
                case=self.case,
                first=number,
                known_text=self.known_text,
                annotations=self.annotations,
                tier=self.tier,
            )
            if isinstance(found, Skipped):
                yield found
                continue
            number += len(found)
            yield from found


@dataclasses.dataclass(frozen=True)
class NrrdCase:
    """One volume of an NRRD file in a ZIP file, each slice along its third
    axis a frame, as the Text Detector Check gives them.

    Attributes
    ----------
    collection : str
    archive : str
        The ZIP file's path.
    member : str
        The volume's name in it, never published.
    modality : str
        ``"CT"`` for a CT in Hounsfield units, otherwise another modality.
    """

    collection: str
    archive: str
    member: str
    modality: str

    @property
    def case(self) -> str:
        return self.member

    def read(self) -> Iterator[EvaluationFrame | Skipped]:
        try:
            with (
                zipfile.ZipFile(self.archive) as archive,
                archive.open(self.member) as stream,
            ):
                volume = nrrd.read_nrrd(stream)
        except nrrd.NrrdRefused as refused:
            yield Skipped(f"not-read/{refused.problem.value}")
            return
        except (OSError, KeyError, zipfile.BadZipFile):
            yield Skipped("not-opened")
            return
        values = volume.values
        if values.ndim != 3 or values.dtype.kind not in "iuf":
            yield Skipped("not-a-volume")
            return
        if values.dtype.kind == "f":
            if not np.isfinite(values).all():
                yield Skipped("values-not-finite")
                return
            values = np.rint(values).astype(np.int64)
        # A run would store the volume's values in at most 32 bits.
        info = np.iinfo(values.dtype if values.dtype.itemsize < 8 else np.int32)
        stored_range = (int(info.min), int(info.max))
        spacing = float(
            max(np.linalg.norm(volume.axes[0]), np.linalg.norm(volume.axes[1]))
        )
        for number, frame in enumerate(values):
            yield EvaluationFrame(
                stored=frame,
                collection=self.collection,
                case=self.case,
                iod="NRRD volume",
                modality=self.modality,
                pixel_spacing=spacing if spacing > 0 else None,
                stored_range=stored_range,
                number=number,
                tier="T3",
            )


def hanseg_cases(path: pathlib.Path | str, image: str) -> tuple[NrrdCase, ...]:
    """HaN-Seg's volumes of one image (``"CT"`` or ``"MR_T1"``) as cases,
    in the order of their cases' directories."""
    with zipfile.ZipFile(path) as archive:
        members = [info.filename for info in hanseg_volumes(archive, image)]
    modality = "CT" if image == "CT" else "MR"
    return tuple(NrrdCase("HaN-Seg", str(path), member, modality) for member in members)


@dataclasses.dataclass(frozen=True)
class SkippedFiles:
    """Files of a folder that are not read, counted as one case's skips:
    those of a SOP Class not asked for, or annotated instances not found."""

    collection: str
    case: str
    reason: str
    count: int

    def read(self) -> Iterator[Skipped]:
        for _ in range(self.count):
            yield Skipped(self.reason)


@dataclasses.dataclass(frozen=True, repr=False)
class TextAnnotations:
    """Boxes that someone drew around the text of DICOM instances, as the
    ground truth of that text.

    An instance that the annotations hold is **annotated**: the text of
    each of its frames is the boxes drawn on that frame, and a frame with
    none holds no text. Each box is taken as text whose ink fills it, so a
    text is fully covered only where the detector's boxes cover the whole
    box: draw boxes tight to the text.

    Attributes
    ----------
    boxes : mapping of str to tuple
        For each SOP Instance UID, its boxes, each a frame index from 0 and
        a :class:`~.text_detection.TextBox` of rows and columns from 0, its
        bottom and right excluded.
    """

    boxes: Mapping[str, tuple[tuple[int, TextBox], ...]]

    def __repr__(self) -> str:
        return "TextAnnotations()"

    @property
    def instances(self) -> frozenset[str]:
        """The instances annotated."""
        return frozenset(self.boxes)

    def subset(self, instances: Iterable[str]) -> TextAnnotations:
        """The annotations of the given instances alone."""
        return TextAnnotations(
            {each: self.boxes[each] for each in instances if each in self.boxes}
        )

    def texts(
        self, instance: str, index: int, shape: tuple[int, int]
    ) -> tuple[BurnedText, ...]:
        """The text of one frame of an annotated instance.

        Raises
        ------
        EvaluationRefused
            If a box lies outside the frame.
        """
        texts = []
        for frame, box in self.boxes.get(instance, ()):
            if frame != index:
                continue
            if box.bottom > shape[0] or box.right > shape[1]:
                raise EvaluationRefused("An annotated box lies outside its frame.")
            rows, columns = box.bottom - box.top, box.right - box.left
            texts.append(
                BurnedText(
                    box.top,
                    box.left,
                    np.ones((rows, columns)),
                    float(min(rows, columns)),
                    {"truth": "annotated"},
                )
            )
        return tuple(texts)

    @classmethod
    def from_csv(cls, path: pathlib.Path | str) -> TextAnnotations:
        """Read annotations from a CSV file with the header row
        :data:`ANNOTATION_COLUMNS`: an instance's SOP Instance UID; its
        frame number, from 1, as DICOM numbers frames, or empty for 1; and
        a box's top row, left column, bottom row, and right column, in
        pixels from 0, the bottom and right excluded. A row whose box is
        empty marks an instance annotated as holding no text.

        Raises
        ------
        EvaluationRefused
            For a file not of this form, by its line, never quoting a value.
        """
        boxes: dict[str, list[tuple[int, TextBox]]] = {}
        with open(path, newline="", encoding="utf-8") as stream:
            reader = csv.reader(stream)
            header = next(reader, None)
            if (
                header is None
                or tuple(each.strip() for each in header) != ANNOTATION_COLUMNS
            ):
                raise EvaluationRefused(
                    "The annotations' first row must name the columns "
                    + ", ".join(ANNOTATION_COLUMNS)
                    + "."
                )
            for line, row in enumerate(reader, start=2):
                if not any(each.strip() for each in row):
                    continue
                instance, box = _annotation(row, line)
                listed = boxes.setdefault(instance, [])
                if box is not None:
                    listed.append(box)
        return cls({key: tuple(value) for key, value in boxes.items()})


def _annotation(
    row: Sequence[str], line: int
) -> tuple[str, tuple[int, TextBox] | None]:
    """One row of an annotations file."""
    if len(row) != len(ANNOTATION_COLUMNS):
        raise EvaluationRefused(
            f"Line {line} of the annotations has too few or many cells."
        )
    cells = [each.strip() for each in row]
    instance, frame, *edges = cells
    if not instance:
        raise EvaluationRefused(f"Line {line} of the annotations names no instance.")
    if not any(edges):
        return instance, None
    try:
        number = int(frame) if frame else 1
        top, left, bottom, right = (int(each) for each in edges)
    except ValueError as error:
        raise EvaluationRefused(
            f"Line {line} of the annotations has a cell that is not a whole number."
        ) from error
    if number < 1 or top < 0 or left < 0 or bottom <= top or right <= left:
        raise EvaluationRefused(
            f"Line {line} of the annotations has a frame below 1 or an empty box."
        )
    return instance, (number - 1, TextBox(top, left, bottom, right))


@dataclasses.dataclass(frozen=True)
class _Header:
    path: pathlib.Path
    sop_class: str | None
    instance: str | None
    keys: Mapping[str, str | None]
    order: tuple


def _header(path: pathlib.Path) -> _Header | None:
    """What grouping needs of one file, or None for a file that a run would
    not read."""
    try:
        dataset = read_source(path.read_bytes()).dataset()
    except (SourceRefused, OSError):
        return None
    patient = _text(dataset, "PatientID")
    issuer = _text(dataset, "IssuerOfPatientID") or ""
    series = _text(dataset, "SeriesInstanceUID")
    number = _numbers(dataset, "InstanceNumber")
    return _Header(
        path=path,
        sop_class=_text(dataset, "SOPClassUID"),
        instance=_text(dataset, "SOPInstanceUID"),
        keys={
            "patient": None if patient is None else f"{patient}\0{issuer}",
            "study": _text(dataset, "StudyInstanceUID"),
            "series": series,
        },
        order=(series or "", number[0] if number else math.inf),
    )


def case_name(level: str, key: str) -> str:
    """The name of a case of files grouped at ``level`` by ``key``: a salted
    SHA-256, so that no identifier is held as its name."""
    digest = hashlib.sha256("\0".join((_CASE_SALT, level, key)).encode()).hexdigest()
    return f"{level}/{digest}"


def dicom_folder_cases(
    root: pathlib.Path | str,
    *,
    collection: str,
    group_by: str = "patient",
    sop_classes: Collection[str] | None = None,
    known_text: str = "unknown",
    annotations: TextAnnotations | None = None,
    tier: str = "T6",
) -> tuple[DicomCase | SkippedFiles, ...]:
    """The DICOM files under a folder, as cases.

    Each file is read once here, as a run reads a source, for what groups
    it, and again when its case is read. Files are grouped by ``group_by``,
    one of :data:`GROUPINGS`; a file without the attribute that groups it
    falls to the next finer grouping, down to the file alone. Each case is
    named by a salted SHA-256 of what groups it, so that the split is
    fixed and no identifier or path is held as its name, and its files are
    read in order of series and Instance Number. A case grouped more finely
    than by patient, whose files all name one patient, gives that patient
    as its subject, by the same digest, so that the split and the bootstrap
    keep the patient's cases together.

    Parameters
    ----------
    root : path
        The folder, searched to any depth.
    collection : str
        The name the summary gives these files, such as ``"clinic RT
        Images"``.
    group_by : str
    sop_classes : collection of str, optional
        The SOP Class UIDs to read, such as ``(RT_IMAGE_STORAGE,)``; files
        of others are counted as skipped (``sop-class-not-selected``). All
        are read where not given.
    known_text : str
        What is known of the text of frames that no annotation covers;
        ``"unknown"``, where they may hold text, unless the folder is known
        to hold none.
    annotations : TextAnnotations, optional
        Boxes around the text of some instances; annotated instances not
        found are counted as skipped (``annotation-not-found``).
    tier : str
        The tier of the corpus, one of
        :data:`~.text_evaluation_frames.TIERS`: by default ``"T6"``, images
        read only on a person's own machine.

    Returns
    -------
    tuple of DicomCase and SkippedFiles
        In order of their names. Files that a run would not read form one
        case, whose reading counts each as skipped.
    """
    if group_by not in GROUPINGS:
        raise EvaluationRefused("A folder's files must be grouped by a known way.")
    if known_text not in KNOWN_TEXT:
        raise EvaluationRefused("What is known of a frame's text must be known.")
    if tier not in TIERS:
        raise EvaluationRefused("A frame's tier must be a known one.")
    selected = None if sop_classes is None else frozenset(sop_classes)
    root = pathlib.Path(root)
    groups: dict[str, list[_Header]] = {}
    unread: list[str] = []
    excluded = 0
    for path in sorted(each for each in root.rglob("*") if each.is_file()):
        header = _header(path)
        if header is None:
            unread.append(str(path))
            continue
        if selected is not None and header.sop_class not in selected:
            excluded += 1
            continue
        levels = GROUPINGS[GROUPINGS.index(group_by) :]
        level, key = next(
            ((each, header.keys[each]) for each in levels[:-1] if header.keys[each]),
            ("file", str(path.relative_to(root))),
        )
        groups.setdefault(case_name(level, key), []).append(header)
    found = {header.instance for members in groups.values() for header in members} - {
        None
    }
    cases: list[DicomCase | SkippedFiles] = []
    for name in sorted(groups):
        members = sorted(groups[name], key=lambda each: (each.order, str(each.path)))
        patients = {each.keys["patient"] for each in members}
        (patient,) = patients if len(patients) == 1 else (None,)
        cases.append(
            DicomCase(
                collection,
                name,
                tuple(str(each.path) for each in members),
                known_text=known_text,
                annotations=(
                    None
                    if annotations is None
                    else annotations.subset(
                        each.instance for each in members if each.instance
                    )
                ),
                tier=tier,
                subject=(
                    None
                    if patient is None or name.startswith("patient/")
                    else case_name("patient", patient)
                ),
            )
        )
    if unread:
        cases.append(
            DicomCase(collection, "not-read", tuple(unread), known_text, tier=tier)
        )
    if excluded:
        cases.append(
            SkippedFiles(collection, "excluded", "sop-class-not-selected", excluded)
        )
    if annotations is not None:
        missing = len(annotations.instances - found)
        if missing:
            cases.append(
                SkippedFiles(collection, "annotated", "annotation-not-found", missing)
            )
    return tuple(cases)
