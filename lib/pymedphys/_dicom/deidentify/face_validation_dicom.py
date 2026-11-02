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
# One module measures each kind of instance that the face block bears on,
# and documents each measure, so it is long.

"""The face block and its holds, checked on a directory of DICOM files
(D-054).

Under the Clean Recognizable Visual Features Option, a run finds the face
block of each CT series (:mod:`~pymedphys._dicom.deidentify.face_blocks`),
holds a series with a target in its block or an eye ROI away from the
globes it found, sets an RT Dose in a defaced frame to zero in the block or
holds it where that dose is too great
(:mod:`~pymedphys._dicom.deidentify.dose_defacing`), and cuts an RT
Structure Set's contours by the block
(:mod:`~pymedphys._dicom.deidentify.region_defacing`). This module runs the
same code on a directory of DICOM files, such as the CT Image series, RT
Structure Sets, RT Plans, and RT Doses that a planning system exports
(:func:`check_dicom`), and counts what a run would do and how the block
that it finds compares with the planners' own eye ROIs and targets. It
renders nothing, writes no instance, and reads each file from where it
lies.

The files below the directory are found as a run's first pass finds them
(:func:`~pymedphys._dicom.deidentify.run_discovery.discover`), each is read
into its record (:class:`~pymedphys._dicom.deidentify.references.InstanceRecord`),
and the records and the files are given to
:func:`~pymedphys._dicom.deidentify.face_blocks.find_face_blocks` and
:func:`~pymedphys._dicom.deidentify.dose_defacing.find_dose_blocks` as a run
gives them. A file that changes once read is given as one that can no
longer be read, as a run gives it. Of each series of CT Image instances
(:class:`SeriesMeasures`), it measures:

- the finder's outcome, by the reason that a run counts in its release
  report;
- how its slices are stored, their spacings, and whether at least 1% of its
  voxels are at -900 Hounsfield units or below, as a head CT's are;
- for a series with a block, whether defaced or held: each eye ROI that a
  run checks against the globes found, in the structure sets that it
  searches for the series (``_is_eye`` and ``_searched`` in
  :mod:`~pymedphys._dicom.deidentify.face_blocks`): the distance from the
  globe on the side that its name gives, or for a name that gives none from
  the nearer globe to each of its contours, to the centroid of its closed
  planar contours, weighted by their areas (:func:`centroid`); whether it is
  nearer the other side's globe; the distance from its farthest point to
  the nearer globe, which a run compares with
  :data:`~pymedphys._dicom.deidentify.face_blocks.EYE_REACH`; and the height
  of its lowest point above the block's inferior limit;
- for a series with a block, each target of those structure sets, an ROI of
  RT ROI Interpreted Type PTV, CTV, or GTV, by whether it holds the series
  and why, and for one in the series' frame that does not, its clearance
  from the block (:func:`clearance`); and
- for any other series, whether those structure sets hold an eye ROI.

Of each RT Dose and RT Structure Set that a run holds or cleans for a
defaced series' frame, it counts the outcome: an RT Dose set to zero in the
block or held, with the greatest stored value that a run would set to zero
as a fraction of the grid's greatest, which a run compares with
:data:`~pymedphys._dicom.deidentify.dose_defacing.DOSE_FRACTION`; and an RT
Structure Set cut, unchanged, or held, with the ROIs that a run would cut
by RT ROI Interpreted Type. It counts the RT Plans that name a defaced
series' frame.

These are summarised (:func:`summarise`) as counts: of files, series,
instances, and ROIs by code, and of measures in fixed bins, never a value,
a UID, a name, a path, or a date, so that the summary of a run on real
patients' files can be shared. A unit whose measuring raises anything is
counted by the exception's type and the place in the code that raised it,
never its message; library warnings and log records are redacted
(:func:`~pymedphys._dicom.deidentify.diagnostics.redacted_diagnostics`).

Nothing here renders a surface or tests whether a face can be recognised.
"""

from __future__ import annotations

import collections
import dataclasses
import hashlib
import io
import math
import os
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom

from . import face_blocks
from .defacing import FaceBlock
from .diagnostics import redacted_diagnostics
from .dose_defacing import (
    DOSE_FRACTION,
    RT_DOSE,
    DoseBlock,
    RtDoseDefacer,
    find_dose_blocks,
)
from .face_blocks import (
    CT_IMAGE,
    PET_IMAGE,
    RT_STRUCTURE_SET,
    Defaced,
    SeriesDefacing,
    _hull_reaches,
    _is_eye,
    _roi_frames,
    _searched,
    _series_outcome,
    _targets,
    _tied_frames,
    find_defaced,
    find_face_blocks,
    frames_of,
)
from .face_review import PIXEL_DATA_TAGS
from .face_validation import (
    EYE_REACH,
    EYES_ABOVE_LIMIT,
    GLOBE_ERROR,
    PIXEL_SPACING,
    SLICE_SPACING,
    Bins,
    FaceValidationRefused,
    _added,
    _AIR,
    _AIR_SHARE,
    _counted,
    _present,
    _settings,
    _software,
    crash_site,
)
from .pixel_cleaning import FrameMask, PixelDataRefused, black_out
from .reasons import VisualFeaturesReason
from .references import InstanceRecord
from .region_defacing import ContoursRefused, cut_contours
from .run_discovery import RunError, discover
from .source import NATIVE_TRANSFER_SYNTAXES, SourceRefused, read_source
from .uids import normalise_uid

FORMAT = "pymedphys-deid-face-validation-dicom/1"
RT_PLAN = "RT Plan"
CLOSED = frozenset({"CLOSED_PLANAR", "CLOSEDPLANAR_XOR"})
# The defined terms of RT ROI Interpreted Type (PS3.3 C.8.8.8): any other
# value is counted as "other", and an empty one as "none", so that no text
# that a planner typed is written.
INTERPRETED_TYPES = frozenset(
    {
        "EXTERNAL",
        "PTV",
        "CTV",
        "GTV",
        "TREATED_VOLUME",
        "IRRAD_VOLUME",
        "OAR",
        "BOLUS",
        "AVOIDANCE",
        "ORGAN",
        "MARKER",
        "REGISTRATION",
        "ISOCENTER",
        "CONTRAST_AGENT",
        "CAVITY",
        "BRACHY_CHANNEL",
        "BRACHY_ACCESSORY",
        "BRACHY_SRC_APP",
        "BRACHY_CHNL_SHLD",
        "SUPPORT",
        "FIXATION",
        "DOSE_REGION",
        "CONTROL",
        "DOSE_MEASUREMENT",
        "DEVICE",
    }
)
TARGET_CLEARANCE = Bins("mm", (0.0, 2.0, 5.0, 10.0, 20.0, 30.0, 50.0, 100.0))
DOSE_SHARE = Bins("fraction", (0.0, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5))
# The sides that an eye ROI's name may give, the patient's right first, as
# a block's globes are.
SIDES = ("right", "left")
_SIDE_WORDS = {
    "r": 0,
    "rt": 0,
    "right": 0,
    "l": 1,
    "lt": 1,
    "left": 1,
}
_SIDED_EYE = r"(l|r|lt|rt|left|right)?(?:eye|eyeball|globe)s?(l|r|lt|rt|left|right)?"


@dataclasses.dataclass(frozen=True, repr=False)
class EyeMeasures:
    """What one eye ROI shows against the block's globes, for
    :func:`summarise` alone. Its ``repr`` shows nothing of it.

    Attributes
    ----------
    side : str
        ``"right"`` or ``"left"``, the side that the ROI's name gives, or
        ``"not-named"``.
    globe_errors : tuple of float
        For a named side, the distance from that side's globe to the ROI's
        centroid; otherwise, for each globe nearer the centroid of any of
        its contours than the other, the distance from that globe to the
        centroid of those contours; in millimetres. Empty where its points
        cannot be placed.
    swapped : bool or None
        For a named side, whether the centroid is nearer the other side's
        globe; otherwise None.
    reach : float or None
        The distance from its point farthest from the nearer globe to that
        globe, in millimetres; None where a point cannot be placed.
    above_limit : float or None
        The height of its lowest point above the block's inferior limit, in
        millimetres.
    """

    side: str
    globe_errors: tuple[float, ...] = ()
    swapped: bool | None = None
    reach: float | None = None
    above_limit: float | None = None

    def __repr__(self) -> str:
        return "EyeMeasures()"


@dataclasses.dataclass(frozen=True, repr=False)
class SeriesMeasures:
    """What one CT series shows, for :func:`summarise` alone. Its ``repr``
    shows nothing of it.

    Attributes
    ----------
    outcome : str
        ``"defaced"``, or the reason that a run counts for a series that it
        does not deface, such as ``"no-eyes"`` or ``"target-in-block"``.
    storage : str
        How its first slice is stored, such as ``"native 16/12 signed"``,
        or ``"unreadable"``.
    pixel_spacing, slice_spacing : float or None
        The larger spacing within its first slice, and the median distance
        between its slices along their normal, in millimetres; None where
        not measured.
    air : bool or None
        Whether at least 1% of its voxels are at -900 Hounsfield units or
        below; None where its pixel data is compressed or cannot be read.
    eye_rois : int
        How many eye ROIs, by ``_is_eye``, in its frame or naming none, the
        structure sets searched for it hold.
    eyes : tuple of EyeMeasures
        For a series with a block, each of those eye ROIs.
    targets : mapping of str to int
        For a series with a block, the targets of those structure sets by
        where they lie (:func:`_target_codes`).
    clearances : tuple of float
        For a series with a block, the clearance from it of each target in
        its frame, or naming none, that does not reach it, in millimetres.
    """

    outcome: str
    storage: str
    pixel_spacing: float | None = None
    slice_spacing: float | None = None
    air: bool | None = None
    eye_rois: int = 0
    eyes: tuple[EyeMeasures, ...] = ()
    targets: Mapping[str, int] = dataclasses.field(default_factory=dict)
    clearances: tuple[float, ...] = ()

    def __repr__(self) -> str:
        return "SeriesMeasures()"


@dataclasses.dataclass(frozen=True, repr=False)
class DoseMeasures:
    """What a run does with one RT Dose in a defaced frame. Its ``repr``
    shows nothing of it.

    Attributes
    ----------
    outcome : str
        ``"set-to-zero"``, ``"not-measured/compressed"``, the reason that it
        is held, such as ``"dose-in-face-block"``, or, for a file that a run
        sequesters, ``"sequestered/"`` and the
        :class:`~.source.SourceReason`'s value.
    share : float or None
        The greatest stored value that a run would set to zero as a
        fraction of the grid's greatest, 0 for a grid of none above zero;
        None where the grid is not placed in the block, or a run's cleaner
        refuses its Pixel Data, as it refuses a field of more bytes than its
        frames and one byte of padding.
    """

    outcome: str
    share: float | None = None

    def __repr__(self) -> str:
        return "DoseMeasures()"


@dataclasses.dataclass(frozen=True, repr=False)
class StructureSetMeasures:
    """What a run does with one RT Structure Set in a defaced frame. Its
    ``repr`` shows nothing of it.

    Attributes
    ----------
    outcome : str
        ``"cut"``, ``"unchanged"``, or the reason that it is held, such as
        ``"undefaced-in-defaced-frame"``.
    cut : mapping of str to int
        The ROIs that a run would cut, by RT ROI Interpreted Type.
    """

    outcome: str
    cut: Mapping[str, int] = dataclasses.field(default_factory=dict)

    def __repr__(self) -> str:
        return "StructureSetMeasures()"


@dataclasses.dataclass(frozen=True, repr=False)
class DicomMeasures:
    """What a directory of DICOM files shows, for :func:`summarise` alone.
    Its ``repr`` shows nothing of it.

    Attributes
    ----------
    files : mapping of str to int
        Counts of the entries found: ``total``, ``read``, and ``not-read``.
    refused : mapping of str to int
        The entries that discovery refused, by why, such as ``"dicomdir"``.
    iods : mapping of str to int
        The files read, by IOD, ``"unknown"`` for one of no supported IOD.
    ct_without_series : int
        CT Image instances without a Series Instance UID, which a run does
        not deface.
    series : tuple of SeriesMeasures
    doses, structure_sets : tuple
        Each RT Dose with pixel data, and each RT Structure Set, that a run
        holds or cleans for a defaced series' frame.
    plans, plans_in_defaced_frames : int
        The RT Plans, and those that name a defaced series' frame.
    crashed : mapping of str to int
        The units whose measuring raised, by what and where
        (:func:`~.face_validation.crash_site`), each prefixed by the kind of
        unit, such as ``"series: "``.
    """

    files: Mapping[str, int]
    refused: Mapping[str, int]
    iods: Mapping[str, int]
    ct_without_series: int
    series: tuple[SeriesMeasures, ...]
    doses: tuple[DoseMeasures, ...]
    structure_sets: tuple[StructureSetMeasures, ...]
    plans: int
    plans_in_defaced_frames: int
    crashed: Mapping[str, int]

    def __repr__(self) -> str:
        return "DicomMeasures()"


class _Files:
    """The regular files found, read by run position, each given as None
    once it can no longer be read or has changed since it was first read."""

    def __init__(self, paths: Mapping[int, os.PathLike[str] | str]) -> None:
        self._paths = paths
        self._digests: dict[int, bytes] = {}

    def first(self, position: int) -> bytes | None:
        """A file's bytes, read for the first time, or None."""
        data = self._bytes(position)
        if data is not None:
            self._digests[position] = hashlib.sha256(data).digest()
        return data

    def __call__(self, position: int) -> bytes | None:
        data = self._bytes(position)
        if data is None or self._digests.get(position) != (
            hashlib.sha256(data).digest()
        ):
            return None
        return data

    def _bytes(self, position: int) -> bytes | None:
        try:
            with open(self._paths[position], "rb") as file:
                return file.read()
        except (OSError, KeyError):
            return None


def check_dicom(directory: os.PathLike[str] | str) -> dict[str, Any]:
    """Check the face block and its holds on a directory of DICOM files.

    Returns
    -------
    dict
        :func:`summarise`'s counts of :func:`measure_dicom`'s measures.

    Raises
    ------
    FaceValidationRefused
        As :func:`measure_dicom` does.
    """
    return summarise(measure_dicom(directory))


def measure_dicom(directory: os.PathLike[str] | str) -> DicomMeasures:
    """Measure a directory of DICOM files, as the module describes.

    Raises
    ------
    FaceValidationRefused
        Where the directory cannot be listed, or holds no CT Image series.
        The message names no path.
    """
    try:
        found = discover(directory)
    except RunError:
        raise FaceValidationRefused(
            "The input is not a directory whose files can be listed."
        ) from None
    regular = {
        position: path
        for position, (path, refusal) in enumerate(
            zip(found.paths, found.refusals, strict=True)
        )
        if refusal is None
    }
    read = _Files(regular)
    crashed: collections.Counter[str] = collections.Counter()
    with redacted_diagnostics():
        records: dict[int, InstanceRecord] = {}
        not_read = 0
        for position in regular:
            data = read.first(position)
            try:
                if data is None:
                    raise OSError
                records[position] = InstanceRecord.from_file(data)
            # A file that is not DICOM, or that pydicom cannot read, raises
            # many types, and a message can quote a value.
            except Exception:  # pylint: disable = broad-exception-caught
                not_read += 1
        series = _series_positions(records)
        if not series:
            raise FaceValidationRefused("The directory holds no CT Image series.")
        outcomes = find_face_blocks(records, read)
        defaced = find_defaced(records, outcomes)
        dose_blocks = find_dose_blocks(
            records, read, outcomes, (RT_DOSE, RT_STRUCTURE_SET, PET_IMAGE)
        )
        measured = []
        for uid, positions in series.items():
            try:
                measured.append(
                    _measure_series(records, read, positions, outcomes[uid])
                )
            # Anything else that a series raises is counted, by where; its
            # message, which could quote a value, is dropped.
            except Exception as error:  # pylint: disable = broad-exception-caught
                crashed[f"series: {crash_site(error)}"] += 1
        doses, structure_sets = [], []
        for position, record in records.items():
            if record.iod not in (RT_DOSE, RT_STRUCTURE_SET):
                continue
            try:
                if record.iod == RT_DOSE:
                    dose = _measure_dose(record, read(position), defaced, dose_blocks)
                    if dose is not None:
                        doses.append(dose)
                else:
                    cut = _measure_structure_set(
                        record, read(position), defaced, dose_blocks
                    )
                    if cut is not None:
                        structure_sets.append(cut)
            except Exception as error:  # pylint: disable = broad-exception-caught
                crashed[f"{record.iod}: {crash_site(error)}"] += 1
    plans = [record for record in records.values() if record.iod == RT_PLAN]
    return DicomMeasures(
        files={
            "total": len(found.paths),
            "read": len(records),
            "not-read": not_read,
        },
        refused=_counted(
            refusal.value for refusal in found.refusals if refusal is not None
        ),
        iods=_counted(record.iod or "unknown" for record in records.values()),
        ct_without_series=sum(
            record.iod == CT_IMAGE and record.series is None
            for record in records.values()
        ),
        series=tuple(measured),
        doses=tuple(doses),
        structure_sets=tuple(structure_sets),
        plans=len(plans),
        plans_in_defaced_frames=sum(
            not frames_of(record).isdisjoint(defaced.frames) for record in plans
        ),
        crashed=dict(sorted(crashed.items())),
    )


def _series_positions(records: Mapping[int, InstanceRecord]) -> dict[str, list[int]]:
    """The run positions of each series of CT Image instances, by its Series
    Instance UID, as :func:`~.face_blocks.find_face_blocks` groups them."""
    series: dict[str, list[int]] = collections.defaultdict(list)
    for position, record in sorted(records.items()):
        if record.iod == CT_IMAGE and record.series is not None:
            series[record.series].append(position)
    return dict(series)


def _measure_series(
    records: Mapping[int, InstanceRecord],
    read: Callable[[int], bytes | None],
    positions: list[int],
    outcome: SeriesDefacing,
) -> SeriesMeasures:
    """Measure one CT series, given its outcome in a run."""
    block, frame = outcome.block, outcome.frame
    if outcome.held:
        # A held series' block is dropped from its outcome, so it is found
        # again, as the run found it, for the holds to be measured against.
        found, frame = _series_outcome(positions, read)
        block = found.block
    if frame is None:
        frame = normalise_uid(str(records[positions[0]].frame_of_reference or ""))
    storage = _stored(positions, read)
    slices = {
        each for position in positions if (each := records[position].sop_instance)
    }
    searched = (
        [
            position
            for position, record in sorted(records.items())
            if record.iod == RT_STRUCTURE_SET
            and _searched(record, frame, slices, positions, records)
        ]
        if frame
        else []
    )
    structure_sets = [_dataset(read(position)) for position in searched]
    eyes = [
        points
        for dataset in structure_sets
        if dataset is not None
        for points in _eye_rois(dataset, frame)
    ]
    measures: dict[str, Any] = {
        "outcome": "defaced" if outcome.problem is None else _code(outcome.problem),
        **storage,
        "eye_rois": len(eyes),
    }
    if block is not None:
        targets: collections.Counter[str] = collections.Counter()
        clearances: list[float] = []
        for dataset in structure_sets:
            if dataset is None:
                targets["structure-set-not-read"] += 1
                continue
            for code, distance in _target_codes(dataset, frame, slices, block):
                targets[code] += 1
                if distance is not None:
                    clearances.append(distance)
        measures["eyes"] = tuple(_eye_measures(block, *each) for each in eyes)
        measures["targets"] = dict(sorted(targets.items()))
        measures["clearances"] = tuple(clearances)
    return SeriesMeasures(**measures)


def _code(problem: object) -> str:
    """The reason code of a series' problem."""
    value = getattr(problem, "value", None)
    return value if isinstance(value, str) else "unknown"


def _dataset(data: bytes | None) -> pydicom.Dataset | None:
    """A file's data set, or None where it cannot be read."""
    try:
        return pydicom.dcmread(io.BytesIO(data or b""))
    # pydicom raises many types for a file it cannot read, and a message can
    # quote a value.
    except Exception:  # pylint: disable = broad-exception-caught
        return None


def _stored(
    positions: list[int], read: Callable[[int], bytes | None]
) -> dict[str, Any]:
    """How a series' slices are stored, their spacings, and whether air is
    stored, as :class:`SeriesMeasures` describes them."""
    heights = []
    air = total = 0
    storage = pixel_spacing = normal = None
    compressed = False
    try:
        for position in positions:
            dataset = pydicom.dcmread(io.BytesIO(read(position) or b""))
            native = str(dataset.file_meta.TransferSyntaxUID) in (
                NATIVE_TRANSFER_SYNTAXES
            )
            if storage is None:
                storage = _storage(dataset, native)
                pixel_spacing = max(float(each) for each in dataset.PixelSpacing)
                cosines = [float(each) for each in dataset.ImageOrientationPatient]
                normal = np.cross(cosines[:3], cosines[3:])
            assert normal is not None
            heights.append(
                float(
                    np.dot(
                        [float(each) for each in dataset.ImagePositionPatient], normal
                    )
                )
            )
            compressed |= not native
            if not compressed:
                values = dataset.pixel_array.astype(np.float64) * float(
                    dataset.get("RescaleSlope", 1)
                ) + float(dataset.get("RescaleIntercept", 0))
                air += int(np.count_nonzero(values <= _AIR))
                total += values.size
    # A slice that cannot be read, or whose attributes cannot be read as
    # numbers, raises many types, and a message can quote a value.
    except Exception:  # pylint: disable = broad-exception-caught
        return {"storage": storage or "unreadable"}
    steps = np.diff(np.sort(heights))
    steps = steps[steps > 0]
    return {
        "storage": storage,
        "pixel_spacing": _spacing(pixel_spacing),
        "slice_spacing": _spacing(float(np.median(steps)) if len(steps) else None),
        "air": None if compressed or not total else air >= _AIR_SHARE * total,
    }


def _spacing(value: float | None) -> float | None:
    """A spacing that is a finite number above zero, which a bin can hold,
    or None."""
    return value if value is not None and 0 < value < math.inf else None


def _storage(dataset: pydicom.Dataset, native: bool) -> str:
    """How a slice is stored, as a code of its transfer syntax's kind, its
    bits allocated and stored, and its pixel representation."""
    allocated, stored = int(dataset.BitsAllocated), int(dataset.BitsStored)
    if allocated not in (8, 16, 32) or not 1 <= stored <= allocated:
        return "other"
    signed = "signed" if int(dataset.PixelRepresentation) else "unsigned"
    return f"{'native' if native else 'compressed'} {allocated}/{stored} {signed}"


def _eye_rois(
    dataset: pydicom.Dataset, frame: str
) -> list[tuple[int | None, list[tuple[str, np.ndarray]]]]:
    """Each eye ROI that a run checks against the globes, as
    ``_eyes_far`` in :mod:`~.face_blocks` selects them: the side that its
    name gives, as an index into a block's globes, or None, and each of its
    contours' geometric type and points."""
    frames_of_roi = _roi_frames(dataset)
    names = {
        int(item.ROINumber): str(item.get("ROIName") or "")
        for item in dataset.get("StructureSetROISequence") or []
    }
    eyes = {
        number: name
        for number, name in names.items()
        if frames_of_roi(number) & {"", frame} and _is_eye(name)
    }
    found = []
    for item in dataset.get("ROIContourSequence") or []:
        number = int(item.ReferencedROINumber)
        if number not in eyes:
            continue
        contours = [
            (
                str(contour.get("ContourGeometricType") or "").strip().upper(),
                np.asarray([float(v) for v in contour.ContourData]).reshape(-1, 3),
            )
            for contour in item.get("ContourSequence") or []
        ]
        if contours:
            found.append((side_of(eyes[number]), contours))
    return found


def side_of(name: str) -> int | None:
    """The side that an eye ROI's name gives, 0 for the patient's right and
    1 for their left, as a block's globes are ordered, or None where it
    gives neither or both.

    Its words are parted as ``_is_eye`` parts them; a side is a word of its
    own, such as ``"L"`` in ``"Eye_L"`` or ``"EyeL"``, or joined to the
    word for the eye, as in ``"lefteye"``.

    >>> [side_of(name) for name in ("Eye_R", "LEye", "Globe_Lt", "Eyes")]
    [0, 1, 1, None]
    """
    sides = set()
    for word in re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|[0-9]+", name):
        word = word.lower()
        if word in _SIDE_WORDS:
            sides.add(_SIDE_WORDS[word])
        elif (match := re.fullmatch(_SIDED_EYE, word)) is not None:
            sides.update(_SIDE_WORDS[each] for each in match.groups() if each)
    return next(iter(sides)) if len(sides) == 1 else None


def centroid(contours: Sequence[tuple[str, np.ndarray]]) -> np.ndarray:
    """The centroid of an ROI's closed contours, each polygon's centroid
    weighted by its area, or, where none bounds an area, the mean of all
    its points.

    Each closed contour's area counts as positive, so a hole's contour adds
    to the region rather than taking from it; an eye's contours have none.
    """
    areas, centres = [], []
    for kind, points in contours:
        if kind in CLOSED and len(points) >= 3:
            area, centre = _polygon(points)
            if area > 0:
                areas.append(area)
                centres.append(centre)
    if areas:
        return np.average(np.asarray(centres), axis=0, weights=areas)
    return np.mean(np.concatenate([points for _, points in contours]), axis=0)


def _polygon(points: np.ndarray) -> tuple[float, np.ndarray]:
    """A planar polygon's area and centroid, from the triangles that join
    its first point to each edge, signed by the polygon's own normal, so
    that a polygon that is not convex is measured too."""
    first = points[0]
    crosses = np.cross(points[1:-1] - first, points[2:] - first)
    vector = crosses.sum(axis=0) / 2
    size = float(np.linalg.norm(vector))
    if not size:
        return 0.0, first
    areas = crosses @ (vector / size) / 2
    centres = (first + points[1:-1] + points[2:]) / 3
    return size, (areas @ centres) / areas.sum()


def _eye_measures(
    block: FaceBlock, side: int | None, contours: list[tuple[str, np.ndarray]]
) -> EyeMeasures:
    """One eye ROI against the block's globes."""
    points = np.concatenate([each for _, each in contours])
    name = "not-named" if side is None else SIDES[side]
    if not np.isfinite(points).all():
        return EyeMeasures(name)
    globes = np.asarray(block.globes, dtype=float)
    nearest = np.min(np.linalg.norm(points[:, np.newaxis, :] - globes, axis=2), axis=1)
    measures: dict[str, Any] = {
        "side": name,
        "reach": float(np.max(nearest)),
        "above_limit": float(np.min(points[:, 2]) - block.inferior_limit),
    }
    if side is not None:
        centre = centroid(contours)
        distances = np.linalg.norm(globes - centre, axis=1)
        measures["globe_errors"] = (float(distances[side]),)
        measures["swapped"] = bool(distances[1 - side] < distances[side])
    else:
        groups: dict[int, list[tuple[str, np.ndarray]]] = collections.defaultdict(list)
        for kind, each in contours:
            middle = np.mean(each, axis=0)
            groups[int(np.argmin(np.linalg.norm(globes - middle, axis=1)))].append(
                (kind, each)
            )
        measures["globe_errors"] = tuple(
            float(np.linalg.norm(globes[globe] - centroid(group)))
            for globe, group in sorted(groups.items())
        )
    return EyeMeasures(**measures)


def _target_codes(
    dataset: pydicom.Dataset, frame: str, slices: set[str], block: FaceBlock
) -> Iterable[tuple[str, float | None]]:
    """Where each target of a structure set lies, as ``_targets_reach`` in
    :mod:`~.face_blocks` judges it, with the clearance of each that does not
    reach the block: ``"tied-to-another-frame"`` for one in another frame
    that the set ties to the series' slices, which holds the series;
    ``"reaches-block"``, which holds it too; ``"clear"``; ``"no-contours"``;
    and ``"in-another-frame"`` for one in a frame that the set does not tie
    to the series' slices."""
    frames_of_roi = _roi_frames(dataset)
    targets = _targets(dataset)
    tied = _tied_frames(dataset, frames_of_roi, slices)
    for item in dataset.get("ROIContourSequence") or []:
        number = int(item.ReferencedROINumber)
        if number not in targets:
            continue
        frames = frames_of_roi(number)
        if (frames - {"", frame}) & tied:
            yield "tied-to-another-frame", None
        elif frames & {"", frame}:
            contours = [
                np.asarray([float(v) for v in contour.ContourData]).reshape(-1, 3)
                for contour in item.get("ContourSequence") or []
            ]
            if not contours:
                yield "no-contours", None
                continue
            points = np.concatenate(contours)
            if _hull_reaches(block, points):
                yield "reaches-block", None
            else:
                yield "clear", clearance(block, points)
        else:
            yield "in-another-frame", None


def clearance(block: FaceBlock, points: np.ndarray) -> float:
    """The distance between the convex hull of a target's points and the
    block, in millimetres, for points whose hull does not reach it.

    The block holds the points ahead of its vertical plane and above its
    inferior limit, whatever their place along the plane's horizontal
    direction, so the distance is that, in the plane of each point's
    distance ahead of the vertical plane and height above the limit, from
    the hull of the points to the quadrant where both are not negative.
    The distance from a point to that quadrant is a convex function, so
    on the hull, which lies wholly outside the quadrant, it is least on an
    edge: at a vertex, or, where an edge passes behind and below the
    quadrant's corner, at the edge's nearest point to the corner, which a
    minimum over vertices alone would overstate.
    """
    anterior, origin = np.array(block.anterior), np.array(block.origin)
    plane = np.column_stack(
        [(points - origin) @ anterior, points[:, 2] - block.inferior_limit]
    )
    plane = np.unique(plane, axis=0)
    vertices = plane[_hull(plane)]
    distance = float(np.min(np.linalg.norm(np.minimum(vertices, 0), axis=1)))
    starts, ends = vertices, np.roll(vertices, -1, axis=0)
    edges = ends - starts
    lengths = np.einsum("ij,ij->i", edges, edges)
    moving = lengths > 0
    along = np.clip(
        -np.einsum("ij,ij->i", starts[moving], edges[moving]) / lengths[moving], 0, 1
    )
    nearest = starts[moving] + along[:, np.newaxis] * edges[moving]
    behind_and_below = (nearest < 0).all(axis=1)
    if behind_and_below.any():
        distance = min(
            distance,
            float(np.min(np.linalg.norm(nearest[behind_and_below], axis=1))),
        )
    return distance


def _hull(plane: np.ndarray) -> np.ndarray:
    """The indices of the vertices of the convex hull of distinct points in
    a plane, in order around it, by Andrew's monotone chain; for points on
    one line, its two ends."""
    order = [int(each) for each in np.lexsort((plane[:, 1], plane[:, 0]))]
    if len(order) <= 2:
        return np.array(order)

    def chain(indices: list[int]) -> list[int]:
        found: list[int] = []
        for index in indices:
            while (
                len(found) >= 2
                and _turn(plane[found[-2]], plane[found[-1]], plane[index]) <= 0
            ):
                found.pop()
            found.append(index)
        return found

    lower, upper = chain(order), chain(order[::-1])
    return np.array(lower[:-1] + upper[:-1])


def _turn(first: np.ndarray, second: np.ndarray, third: np.ndarray) -> float:
    """Twice the signed area of a triangle in a plane: positive where its
    points run anticlockwise."""
    return float(
        (second[0] - first[0]) * (third[1] - first[1])
        - (second[1] - first[1]) * (third[0] - first[0])
    )


def _measure_dose(
    record: InstanceRecord,
    data: bytes | None,
    defaced: Defaced,
    dose_blocks: Mapping[str, DoseBlock],
) -> DoseMeasures | None:
    """What a run does with an RT Dose, as ``_dose_block``, ``_cleaned``,
    and ``_frame_hold`` of the instance transform decide it, or None for
    one that it neither holds nor cleans for a defaced frame, such as one
    without pixel data, which holds only dose-volume histograms."""
    dataset = pydicom.dcmread(io.BytesIO(data or b""))
    if not any(tag in dataset for tag in PIXEL_DATA_TAGS):
        return None
    frames = frames_of(record)
    dose = dose_blocks.get(next(iter(frames))) if len(frames) == 1 else None
    undefaced = VisualFeaturesReason.UNDEFACED_IN_DEFACED_FRAME.value
    if dose is None:
        return DoseMeasures(undefaced) if defaced.holds(RT_DOSE, record) else None
    if str(dataset.file_meta.TransferSyntaxUID) not in NATIVE_TRANSFER_SYNTAXES:
        # A run decodes it in a process of its own; this check decodes no
        # compressed Pixel Data.
        return DoseMeasures("not-measured/compressed")
    try:
        source = read_source(data or b"")
    except SourceRefused as refused:
        return DoseMeasures(f"sequestered/{refused.reason.value}")
    try:
        defacer = RtDoseDefacer(dose, source.dataset())
        recorder = _Recorder(defacer)
        # The run's own cleaner, which admits only the Pixel Data that a
        # run cleans, gives each frame to the defacer.
        black_out(source, source.dataset(), None, recorder)
    except PixelDataRefused:
        return DoseMeasures(undefaced)
    held = defacer.held
    if held is not None:
        outcome = held.value
    else:
        outcome = undefaced if dose.holds(defaced, record) else "set-to-zero"
    return DoseMeasures(outcome, recorder.share)


class _Recorder:
    """Gives a defacer's masks, as :func:`~.pixel_cleaning.black_out` asks
    for them, and records the greatest stored value of the frames given and
    of the voxels that their masks set to zero."""

    def __init__(self, defacer: RtDoseDefacer) -> None:
        self._defacer = defacer
        self._greatest = 0
        self._zeroed = 0

    def mask(self, frame: int, stored: np.ndarray) -> FrameMask | None:
        stored = np.asarray(stored)
        if stored.size:
            self._greatest = max(self._greatest, int(stored.max()))
        mask = self._defacer.mask(frame, stored)
        if mask is not None:
            self._zeroed = max(self._zeroed, int(stored[np.asarray(mask.mask)].max()))
        return mask

    @property
    def share(self) -> float:
        """The greatest stored value set to zero as a fraction of the
        greatest given, or 0 for frames of none above 0."""
        return self._zeroed / self._greatest if self._greatest > 0 else 0.0


def _measure_structure_set(
    record: InstanceRecord,
    data: bytes | None,
    defaced: Defaced,
    dose_blocks: Mapping[str, DoseBlock],
) -> StructureSetMeasures | None:
    """What a run does with an RT Structure Set, as ``_region`` and
    ``_frame_hold`` of the instance transform decide it, or None for one
    that it neither holds nor cleans for a defaced frame."""
    frames = frames_of(record)
    region = dose_blocks.get(next(iter(frames))) if len(frames) == 1 else None
    undefaced = VisualFeaturesReason.UNDEFACED_IN_DEFACED_FRAME.value
    if region is None:
        if defaced.holds(RT_STRUCTURE_SET, record):
            return StructureSetMeasures(undefaced)
        return None
    dataset = pydicom.dcmread(io.BytesIO(data or b""))
    try:
        cut = cut_contours(region, dataset, next(iter(frames)))
    except ContoursRefused:
        return StructureSetMeasures(undefaced)
    kinds = _interpreted_types(dataset)
    items = list(dataset.get("ROIContourSequence") or [])
    by_type = _counted(
        kinds.get(int(items[index].ReferencedROINumber), "none") for index in cut
    )
    if region.holds(defaced, record):
        return StructureSetMeasures(undefaced, by_type)
    return StructureSetMeasures("cut" if cut else "unchanged", by_type)


def _interpreted_types(dataset: pydicom.Dataset) -> dict[int, str]:
    """Each ROI's RT ROI Interpreted Type, by its ROI Number, as one of
    :data:`INTERPRETED_TYPES`, ``"none"``, or ``"other"``."""
    kinds = {}
    for item in dataset.get("RTROIObservationsSequence") or []:
        kind = str(item.get("RTROIInterpretedType") or "").strip().upper()
        kinds[int(item.ReferencedROINumber)] = (
            kind if kind in INTERPRETED_TYPES else "other" if kind else "none"
        )
    return kinds


def summarise(measures: DicomMeasures) -> dict[str, Any]:
    """Return the measures' counts, as the module describes, for JSON."""
    series = measures.series
    blocks = [each for each in series if _has_block(each)]
    eyes = [eye for each in blocks for eye in each.eyes]
    placed = [eye for eye in eyes if eye.reach is not None]
    return {
        "format": FORMAT,
        "data": {
            "source": "DICOM files, read where they lie",
        },
        "software": _software(),
        "settings": {**_settings(), "dose_fraction": DOSE_FRACTION},
        "files": {
            **measures.files,
            "refused": dict(measures.refused),
            "iods": dict(measures.iods),
        },
        "crashed": dict(measures.crashed),
        "ct": {
            "series": len(series),
            "instances_without_series": measures.ct_without_series,
            "storage": _counted(each.storage for each in series),
            "air_in_hounsfield_units": {
                "yes": sum(each.air is True for each in series),
                "no": sum(each.air is False for each in series),
                "not-measured": sum(each.air is None for each in series),
            },
            "pixel_spacing": PIXEL_SPACING.counts(
                _present(each.pixel_spacing for each in series)
            ),
            "slice_spacing": SLICE_SPACING.counts(
                _present(each.slice_spacing for each in series)
            ),
        },
        "series": {
            "defaced": sum(each.outcome == "defaced" for each in series),
            "not_defaced": _counted(
                each.outcome for each in series if each.outcome != "defaced"
            ),
            "with_eye_rois": _counted(each.outcome for each in series if each.eye_rois),
        },
        "eye_rois": {
            "series_with_a_block": len(blocks),
            "by_series": _counted(_eyes_code(each) for each in blocks),
            "sides": _counted(eye.side for eye in eyes),
            "not_placed": len(eyes) - len(placed),
            "sides_swapped": sum(bool(eye.swapped) for eye in placed),
            "globe_centre_error": GLOBE_ERROR.counts(
                error for eye in placed for error in eye.globe_errors
            ),
            "eye_reach": EYE_REACH.counts(_present(eye.reach for eye in placed)),
            "eyes_above_inferior_limit": EYES_ABOVE_LIMIT.counts(
                _present(eye.above_limit for eye in placed)
            ),
        },
        "targets": {
            "by_where": _added(each.targets for each in blocks),
            "clearance": TARGET_CLEARANCE.counts(
                distance for each in blocks for distance in each.clearances
            ),
        },
        "rt_doses": {
            "outcomes": _counted(each.outcome for each in measures.doses),
            "share_set_to_zero": DOSE_SHARE.counts(
                _present(each.share for each in measures.doses)
            ),
        },
        "rt_structure_sets": {
            "outcomes": _counted(each.outcome for each in measures.structure_sets),
            "rois_cut": _added(each.cut for each in measures.structure_sets),
        },
        "rt_plans": {
            "total": measures.plans,
            "in_defaced_frames": measures.plans_in_defaced_frames,
        },
    }


def _has_block(series: SeriesMeasures) -> bool:
    """Whether a series had a block found, whether defaced or held."""
    return series.outcome in (
        "defaced",
        face_blocks.SeriesProblem.TARGET_IN_BLOCK.value,
        face_blocks.SeriesProblem.EYES_DISAGREE.value,
    )


def _eyes_code(series: SeriesMeasures) -> str:
    """How a series' eye ROIs compare with its globes, as a run judges
    them: ``"agree"``, ``"eyes-disagree-with-rois"``, or ``"no-eye-rois"``."""
    if not series.eyes:
        return "no-eye-rois"
    if all(
        eye.reach is not None and eye.reach <= face_blocks.EYE_REACH
        for eye in series.eyes
    ):
        return "agree"
    return face_blocks.SeriesProblem.EYES_DISAGREE.value
