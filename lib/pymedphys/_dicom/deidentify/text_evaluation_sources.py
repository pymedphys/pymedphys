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
:class:`NrrdCase`
    One volume of an NRRD file in a ZIP file, such as HaN-Seg's, each slice
    a frame, as the Text Detector Check gives them.
:class:`~.text_evaluation_phantoms.PhantomCase`
    Synthetic frames.

Real patients' scans are read only on CI runners, under the project's data
rules; nothing here writes, logs, or returns a value of them other than
the frames, which stay in memory.
"""

from __future__ import annotations

import dataclasses
import pathlib
import zipfile
from collections.abc import Iterable, Iterator, Mapping, Sequence
from typing import Protocol, runtime_checkable

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom

from . import nrrd
from .pixel_cleaning import PixelDataRefused, black_out, overlay_planes
from .pixel_text_validation import hanseg_volumes
from .source import SourceRefused, read_source
from .text_evaluation_frames import EvaluationFrame

PRIVATE_SOP_CLASS = "private SOP class"
UNKNOWN_SOP_CLASS = "unknown SOP class"


@dataclasses.dataclass(frozen=True)
class Skipped:
    """Frames not read, for why: a code such as ``"not-read"``."""

    reason: str


@runtime_checkable
class CaseSource(Protocol):
    """A case, which reads its frames when asked."""

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
    data: bytes, *, collection: str, case: str, first: int = 0
) -> list[EvaluationFrame] | Skipped:
    """The frames of one DICOM file's top-level Pixel Data, as a run gives
    them to the text detector, numbered from ``first``, or why there are
    none."""
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
    layout = redaction.layout
    if layout.signed:
        stored_range = (
            -(1 << (layout.bits_stored - 1)),
            (1 << (layout.bits_stored - 1)) - 1,
        )
    else:
        stored_range = (0, (1 << layout.bits_stored) - 1)
    iod = _sop_class_name(dataset)
    modality = _text(dataset, "Modality") or "unknown"
    frames = []
    for index, frame in enumerate(finder.frames):
        slope, intercept = _rescale(dataset, index)
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
            )
        )
    return frames


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
    """

    collection: str
    case: str
    paths: tuple[str, ...]

    def read(self) -> Iterator[EvaluationFrame | Skipped]:
        number = 0
        for path in self.paths:
            try:
                data = pathlib.Path(path).read_bytes()
            except OSError:
                yield Skipped("not-opened")
                continue
            found = dicom_frames(
                data, collection=self.collection, case=self.case, first=number
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
            )


def hanseg_cases(path: pathlib.Path | str, image: str) -> tuple[NrrdCase, ...]:
    """HaN-Seg's volumes of one image (``"CT"`` or ``"MR_T1"``) as cases,
    in the order of their cases' directories."""
    with zipfile.ZipFile(path) as archive:
        members = [info.filename for info in hanseg_volumes(archive, image)]
    modality = "CT" if image == "CT" else "MR"
    return tuple(NrrdCase("HaN-Seg", str(path), member, modality) for member in members)
