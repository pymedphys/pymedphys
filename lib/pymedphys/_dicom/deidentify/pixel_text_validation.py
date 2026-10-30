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

"""The text detector's regions on HaN-Seg's CT and MR volumes (D-037).

Under the Clean Pixel Data Option, a run gives each frame of the
top-level Pixel Data, as stored values, to the text detector
(:class:`~pymedphys._dicom.deidentify.text_detection.TextDetector`, made
with the pinned model and its default parameters), blacks out every region
that it finds, and holds the instance for review. This module gives the
same detector the slices of the HaN-Seg data set's CT and T1-weighted MR
volumes, read from its ZIP file as the face block check reads them (D-054),
and counts the slices and regions that it finds.

Each volume (:class:`~pymedphys._dicom.deidentify.nrrd.Volume`) is given
to the detector as a run gives it a series of its slices: one frame for
each slice along the volume's third axis, rows by columns, its values,
rounded where they are not integers, as stored values. The detector's
renderings depend on the stored values only through their minimum, their
maximum, and differences between them, so a CT stored in Hounsfield units,
as HaN-Seg's are, gives the regions that the same CT stored with a rescale
intercept would. Each region is clipped to its slice, as a run clips it.
Of each volume (:class:`VolumeMeasures`), it measures how it was stored,
the plane of its slices, their size and spacing, how many regions each
slice gives, and of each region its area as a share of the slice, its
shorter side, its longer side over its shorter, and, for a CT, the share
of its pixels above -900 Hounsfield units, where it would black out more
than air. Where the finder also gives what each of its renderings found
(:class:`ScoringFinder`), as the text detector does, it measures each
region's score margin, the highest mean probability that a rendering gave
its box less the detector's box threshold, and which renderings gave it.
A region's score margin is how far the box threshold can rise before the
region is lost, since a box is kept while any rendering gives it.

The volumes' measures are summarised (:func:`summarise`) as counts, of
volumes by outcome, format, and plane, and of measures in fixed bins, also
by the larger side of a slice and by the larger spacing within one, never
a value or a case's name, so that the summary can be published from a run
on real patients' scans. A volume that cannot be read is counted by why,
and one whose measuring raises anything else by the exception's type and
the place in the code that raised it, never its message.

Inference, not measured here: HaN-Seg's volumes hold no burned-in text, so
each region is one that a run would black out in error, over anatomy unless
the region is all air, and that a reviewer would have to clear.

Detection takes seconds a slice on one thread, so :func:`measure_hanseg`
can measure the volumes in worker processes, each with its own detector of
one thread, which find the same regions as one process does.
"""

from __future__ import annotations

import concurrent.futures
import dataclasses
import importlib.metadata
import math
import multiprocessing
import pathlib
import platform
import re
import zipfile
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any, Protocol, cast, runtime_checkable

from pymedphys._imports import numpy as np

from . import nrrd
from .face_validation import (
    HANSEG,
    PIXEL_SPACING,
    SHARE,
    Bins,
    crash_site,
    file_digest,
)
from .pixel_cleaning import TextFinder, finder_description
from .text_detection import RENDERINGS, Detection, DetectionParameters, TextBox

FORMAT = "pymedphys-deid-pixel-text-validation/2"
# HaN-Seg's images, by the name after ``IMG_`` in their files' names.
IMAGES = ("CT", "MR_T1")
_HANSEG_IMAGE = re.compile(r"(?:.*/)?(case_[0-9]+)/\1_IMG_(CT|MR_T1)\.nrrd")
# Hounsfield units at or below which a CT's pixel counts as air, as in the
# face block check.
_AIR = -900
# The most that a slice's normal may turn from an axis of the patient for
# its plane to be named by that axis.
_PLANE_TOLERANCE_DEGREES = 10.0
_PLANES = ("sagittal", "coronal", "axial")

REGIONS_PER_SLICE = Bins("regions", (0, 1, 2, 3, 4, 5, 10, 20))
REGIONS_PER_VOLUME = Bins("regions", (0, 1, 2, 5, 10, 20, 50, 100, 200, 500, 1000))
REGION_AREA = Bins(
    "share of the slice", (0.0, 0.0005, 0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1)
)
REGION_SHORTER_SIDE = Bins("pixels", (0, 8, 12, 16, 24, 32, 48, 64, 96))
REGION_ELONGATION = Bins("ratio", (1.0, 1.5, 2.0, 3.0, 5.0, 10.0))
SLICE_SIDE = Bins("pixels", (0, 256, 384, 512, 640, 768, 1024))
SCORE_MARGIN = Bins(
    "mean probability above the box threshold",
    (0.0, 0.025, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45),
)


class PixelTextValidationRefused(Exception):
    """The data set cannot be checked; the message quotes no value."""


@runtime_checkable
class ScoringFinder(Protocol):
    """A finder that also gives what each of its renderings found, as
    :class:`~.text_detection.TextDetector` does, so that each region's
    score margin can be measured."""

    @property
    def parameters(self) -> DetectionParameters:
        """The settings of detection, whose box threshold each region's
        mean probability reaches."""

    def find(self, frame: np.ndarray) -> Sequence[TextBox]:
        """As :meth:`~.text_detection.TextDetector.find` does."""

    def detections(self, frame: np.ndarray) -> Sequence[Detection]:
        """As :meth:`~.text_detection.TextDetector.detections` does."""


@dataclasses.dataclass(frozen=True, repr=False)
class VolumeMeasures:
    """What one volume shows, for :func:`summarise` alone.

    Its ``repr`` shows nothing of it, and nothing of it but the counts that
    :func:`summarise` makes is to be written, printed, or logged.

    Attributes
    ----------
    format : str
        How the volume was stored (:class:`~.nrrd.NrrdFormat`).
    plane : str
        ``"axial"``, ``"coronal"``, or ``"sagittal"``, where the normal to
        its slices is within 10 degrees of the patient's superior,
        posterior, or left axis, or else ``"oblique"``.
    slice_side : int
        The larger of a slice's rows and columns.
    pixel_spacing : float
        The larger spacing within a slice, in millimetres.
    regions : tuple of int
        How many regions each slice gives, in order.
    areas : tuple of float
        Each region's area as a share of its slice's.
    shorter_sides : tuple of int
        Each region's shorter side, in pixels.
    elongations : tuple of float
        Each region's longer side over its shorter.
    not_air : tuple of float or None
        For a CT, the share of each region's pixels above -900 Hounsfield
        units; otherwise None.
    score_margins : tuple of float or None
        For a :class:`ScoringFinder`, each region's highest mean
        probability less the box threshold; otherwise None.
    renderings : tuple of str or None
        For a :class:`ScoringFinder`, the renderings that gave each region,
        in the order of :data:`~.text_detection.RENDERINGS`, joined by
        ``+``; otherwise None.
    """

    format: str
    plane: str
    slice_side: int
    pixel_spacing: float
    regions: tuple[int, ...]
    areas: tuple[float, ...] = ()
    shorter_sides: tuple[int, ...] = ()
    elongations: tuple[float, ...] = ()
    not_air: tuple[float, ...] | None = None
    score_margins: tuple[float, ...] | None = None
    renderings: tuple[str, ...] | None = None

    def __repr__(self) -> str:
        return "VolumeMeasures()"


@dataclasses.dataclass(frozen=True)
class VolumeNotMeasured:
    """A volume that was not measured, for why.

    Attributes
    ----------
    reason : str
        A code, such as ``"not-read"`` and an :class:`~.nrrd.NrrdProblem`'s
        value, such as ``"not-read/data-length"``, or ``"crashed"``.
    where : str or None
        For ``"crashed"``, the exception's type and the place in the code
        that raised it.
    """

    reason: str
    where: str | None = None


class _NotMeasured(Exception):
    """A volume that cannot be measured, for :attr:`reason`."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def measure_volume(volume: nrrd.Volume, finder: TextFinder, ct: bool) -> VolumeMeasures:
    """Give each slice of a volume to the finder, as a run gives it the
    frames of a series of those slices, and measure the regions found.

    Parameters
    ----------
    volume : nrrd.Volume
    finder : TextFinder
        As a run under the Clean Pixel Data Option is given. A
        :class:`ScoringFinder` is asked for its detections instead of its
        boxes, which give the same regions, each once.
    ct : bool
        Whether the volume is a CT in Hounsfield units, whose regions'
        shares of pixels above air are measured.

    Raises
    ------
    _NotMeasured
        For a volume of layers, or of values that are not finite numbers.
    """
    stored = _stored(volume.values)
    rows, columns = stored.shape[1:]
    along_row, down_column = volume.axes[0], volume.axes[1]
    scoring = isinstance(finder, ScoringFinder)
    regions: list[int] = []
    areas: list[float] = []
    shorter: list[int] = []
    elongations: list[float] = []
    not_air: list[float] = []
    margins: list[float] = []
    renderings: list[str] = []
    for frame in stored:
        if scoring:
            found = _scored(cast(ScoringFinder, finder), frame)
        else:
            found = [(box, math.nan, "") for box in finder.find(frame)]
        boxes = []
        for box, margin, rendering in found:
            clipped = _clipped(box, rows, columns)
            if clipped is not None:
                boxes.append(clipped)
                margins.append(margin)
                renderings.append(rendering)
        regions.append(len(boxes))
        for box in boxes:
            height, width = box.bottom - box.top, box.right - box.left
            areas.append(height * width / (rows * columns))
            shorter.append(min(height, width))
            elongations.append(max(height, width) / min(height, width))
            if ct:
                inside = frame[box.top : box.bottom, box.left : box.right]
                not_air.append(float(np.mean(inside > _AIR)))
    return VolumeMeasures(
        format=str(volume.format),
        plane=_plane(volume.axes),
        slice_side=int(max(rows, columns)),
        pixel_spacing=float(
            max(np.linalg.norm(along_row), np.linalg.norm(down_column))
        ),
        regions=tuple(regions),
        areas=tuple(areas),
        shorter_sides=tuple(shorter),
        elongations=tuple(elongations),
        not_air=tuple(not_air) if ct else None,
        score_margins=tuple(margins) if scoring else None,
        renderings=tuple(renderings) if scoring else None,
    )


def _stored(values: np.ndarray) -> np.ndarray:
    """A volume's values as stored values: integers, those not integers
    rounded, by slice, row, and column."""
    if values.ndim != 3:
        raise _NotMeasured("not-three-dimensional")
    if values.dtype.kind == "f":
        if not np.isfinite(values).all():
            raise _NotMeasured("values-not-finite")
        return np.rint(values)
    if values.dtype.kind not in "iu":
        raise _NotMeasured("values-not-numbers")
    return values


def _scored(
    finder: ScoringFinder, frame: np.ndarray
) -> list[tuple[TextBox, float, str]]:
    """Each box that the finder's renderings give, once, sorted, as
    :meth:`~.text_detection.TextDetector.find` gives them, with its score
    margin and the renderings that gave it.

    Raises
    ------
    TypeError
        If a detection is not a :class:`~.text_detection.Detection`.
    ValueError
        If a detection's rendering is not one of
        :data:`~.text_detection.RENDERINGS`; the message quotes no value.
    """
    highest: dict[TextBox, float] = {}
    gave: dict[TextBox, set[str]] = {}
    for each in finder.detections(frame):
        if not isinstance(each, Detection):
            raise TypeError("a scoring finder must give Detection objects")
        if each.rendering not in RENDERINGS:
            raise ValueError("A detection's rendering is not a known one.")
        box = each.box
        highest[box] = max(highest.get(box, -math.inf), each.mean_probability)
        gave.setdefault(box, set()).add(each.rendering)
    threshold = finder.parameters.box_threshold
    return [
        (
            box,
            highest[box] - threshold,
            "+".join(name for name in RENDERINGS if name in gave[box]),
        )
        for box in sorted(highest)
    ]


def _clipped(box: TextBox, rows: int, columns: int) -> TextBox | None:
    """The finder's box clipped to the slice, as a run clips it, or None
    where the slice does not hold it.

    Raises
    ------
    TypeError
        If the box is not a :class:`~.text_detection.TextBox`.
    """
    if not isinstance(box, TextBox):
        raise TypeError("a text finder must give TextBox objects")
    bottom, right = min(box.bottom, rows), min(box.right, columns)
    if box.top < bottom and box.left < right:
        return TextBox(box.top, box.left, bottom, right)
    return None


def _plane(axes: np.ndarray) -> str:
    """The plane of a volume's slices, by the axis of the patient nearest
    their normal."""
    normal = np.cross(axes[0], axes[1])
    normal = np.abs(normal / np.linalg.norm(normal))
    nearest = int(np.argmax(normal))
    if normal[nearest] < math.cos(math.radians(_PLANE_TOLERANCE_DEGREES)):
        return "oblique"
    return _PLANES[nearest]


def summarise(
    image: str,
    volumes: Sequence[VolumeMeasures | VolumeNotMeasured],
    data: Mapping[str, Any],
    detector: Mapping[str, Any],
) -> dict[str, Any]:
    """Return the volumes' counts, as the module describes, for JSON.

    Parameters
    ----------
    image : str
        One of :data:`IMAGES`.
    volumes : sequence of VolumeMeasures or VolumeNotMeasured
    data : mapping
        What names the data set and its file: its name, version, DOI,
        licence, and citation, and its file's size, MD5, and SHA-256.
    detector : mapping
        What decides the regions, as
        :func:`~.pixel_cleaning.finder_description` gives it for the method
        digest of a run, in JSON's types.
    """
    measured = [each for each in volumes if isinstance(each, VolumeMeasures)]
    not_measured = [each for each in volumes if isinstance(each, VolumeNotMeasured)]
    slices = [count for each in measured for count in each.regions]
    shares = [
        sum(count > 0 for count in each.regions) / len(each.regions)
        for each in measured
        if each.regions
    ]
    not_air = [
        share for each in measured if each.not_air is not None for share in each.not_air
    ]
    scored = bool(measured) and all(each.score_margins is not None for each in measured)
    return {
        "format": FORMAT,
        "image": image,
        "data": dict(data),
        "software": _software(),
        "detector": dict(detector),
        "volumes": {
            "total": len(volumes),
            "measured": len(measured),
            "not_measured": _counted(each.reason for each in not_measured),
            "crashed": _counted(each.where for each in not_measured if each.where),
            "formats": _counted(each.format for each in measured),
            "planes": _counted(each.plane for each in measured),
            "slice_side": SLICE_SIDE.counts(each.slice_side for each in measured),
            "pixel_spacing": PIXEL_SPACING.counts(
                each.pixel_spacing for each in measured
            ),
        },
        "slices": {
            "searched": len(slices),
            "with_a_region": sum(count > 0 for count in slices),
            "regions": REGIONS_PER_SLICE.counts(slices),
        },
        "volumes_by_regions": {
            "with_a_region": sum(any(each.regions) for each in measured),
            "regions": REGIONS_PER_VOLUME.counts(
                sum(each.regions) for each in measured
            ),
            "share_of_slices_with_a_region": SHARE.counts(shares),
        },
        "regions": {
            "total": sum(slices),
            "area": REGION_AREA.counts(
                area for each in measured for area in each.areas
            ),
            "shorter_side": REGION_SHORTER_SIDE.counts(
                side for each in measured for side in each.shorter_sides
            ),
            "elongation": REGION_ELONGATION.counts(
                ratio for each in measured for ratio in each.elongations
            ),
            "share_not_air": SHARE.counts(not_air) if image == "CT" else None,
            **_scores(measured, scored),
        },
        "by_slice_side": _grouped(
            SLICE_SIDE, measured, [each.slice_side for each in measured], scored
        ),
        "by_pixel_spacing": _grouped(
            PIXEL_SPACING, measured, [each.pixel_spacing for each in measured], scored
        ),
    }


def _scores(measured: Sequence[VolumeMeasures], scored: bool) -> dict[str, Any]:
    """The volumes' regions by score margin and by the renderings that gave
    them, or None for each where the finder gives no scores."""
    if not scored:
        return {"score_margin": None, "renderings": None}
    return {
        "score_margin": SCORE_MARGIN.counts(
            margin for each in measured for margin in each.score_margins or ()
        ),
        "renderings": _counted(
            code for each in measured for code in each.renderings or ()
        ),
    }


def _grouped(
    bins: Bins,
    measured: Sequence[VolumeMeasures],
    values: Sequence[float],
    scored: bool,
) -> dict[str, Any]:
    """The volumes, their slices, and their regions, counted in each of
    the bins that hold the volumes' values, with the regions by score
    margin and by the renderings that gave them."""
    groups: list[list[VolumeMeasures]] = [[] for _ in bins.counts(())["bins"]]
    for each, value in zip(measured, values, strict=True):
        groups[bins.index(value)].append(each)
    return {
        "unit": bins.unit,
        "bins": [
            {
                "from": edges["from"],
                "to": edges["to"],
                "volumes": len(group),
                "slices_searched": sum(len(each.regions) for each in group),
                "slices_with_a_region": sum(
                    count > 0 for each in group for count in each.regions
                ),
                "regions": sum(sum(each.regions) for each in group),
                **_scores(group, scored),
            }
            for edges, group in zip(bins.counts(())["bins"], groups, strict=True)
        ],
    }


def _counted(codes: Iterable[str]) -> dict[str, int]:
    """How many of each code, in the codes' order."""
    counts: dict[str, int] = {}
    for code in codes:
        counts[code] = counts.get(code, 0) + 1
    return dict(sorted(counts.items()))


def _software() -> dict[str, str]:
    """The versions of Python and of the packages that the counts depend
    on."""
    versions = {"python": platform.python_version()}
    for package in ("pymedphys", "numpy", "scipy", "onnxruntime"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = "unknown"
    return versions


def described(finder: TextFinder) -> dict[str, Any]:
    """What decides a finder's regions, as the method digest of a run
    takes it (:func:`~.pixel_cleaning.finder_description`), in JSON's
    types: mappings as objects, and sequences and sets as lists, a set's
    members sorted."""
    return cast(dict[str, Any], _plain(finder_description(finder)))


def _plain(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _plain(each) for key, each in value.items()}
    if isinstance(value, (set, frozenset)):
        return sorted(_plain(each) for each in value)  # type: ignore[type-var]
    if isinstance(value, (list, tuple)):
        return [_plain(each) for each in value]
    return value


def hanseg_volumes(archive: zipfile.ZipFile, image: str) -> list[zipfile.ZipInfo]:
    """The volumes of one image in HaN-Seg's ZIP file, one for each case
    that has it, in the order of the cases' directories, as
    ``case_NN/case_NN_IMG_<image>.nrrd`` names them."""
    found = {}
    for info in archive.infolist():
        match = _HANSEG_IMAGE.fullmatch(info.filename)
        if match is not None and match[2] == image:
            found[info.filename.rpartition("/")[0]] = info
    return [found[directory] for directory in sorted(found)]


def check_hanseg(
    path: pathlib.Path,
    image: str,
    *,
    finder: Callable[[], TextFinder],
    workers: int = 1,
) -> dict[str, Any]:
    """Count the finder's regions on one image of HaN-Seg's cases.

    Parameters
    ----------
    path : pathlib.Path
        HaN-Seg's ZIP file, ``HaN-Seg.zip``, from its Zenodo record.
    image : str
        One of :data:`IMAGES`.
    finder : callable
        Makes the finder, as a run under the option makes it: for the
        text detector, :class:`~.text_detection.TextDetector` with no
        arguments. Where ``workers`` is more than one, it is called once in
        each worker, so must be picklable, as a class or a module's
        function is.
    workers : int
        How many processes measure the volumes; one measures them in this
        process.

    Returns
    -------
    dict
        :func:`summarise`'s counts of :func:`measure_hanseg`'s volumes.

    Raises
    ------
    PixelTextValidationRefused
        As :func:`measure_hanseg` does.
    """
    made = finder()
    volumes = measure_hanseg(path, image, finder=finder, workers=workers, made=made)
    return summarise(
        image, volumes, {**HANSEG, "file": file_digest(path)}, described(made)
    )


def measure_hanseg(
    path: pathlib.Path,
    image: str,
    *,
    finder: Callable[[], TextFinder],
    workers: int = 1,
    made: TextFinder | None = None,
) -> list[VolumeMeasures | VolumeNotMeasured]:
    """Measure each volume of one image of HaN-Seg's ZIP file, in the order
    of their cases' directories, reading each from the ZIP file without
    extracting it.

    Parameters
    ----------
    path, image, finder, workers
        As :func:`check_hanseg` takes them.
    made : TextFinder, optional
        A finder already made, used where ``workers`` is one.

    Raises
    ------
    PixelTextValidationRefused
        Where the image is not one of :data:`IMAGES`, ``workers`` is less
        than one, or the file is not a ZIP file or holds no volume of the
        image.
    """
    if image not in IMAGES:
        raise PixelTextValidationRefused(
            f"The image must be one of {', '.join(IMAGES)}."
        )
    if workers < 1:
        raise PixelTextValidationRefused("There must be at least one worker.")
    try:
        with zipfile.ZipFile(path) as archive:
            names = [info.filename for info in hanseg_volumes(archive, image)]
    except (OSError, zipfile.BadZipFile):
        raise PixelTextValidationRefused(
            "The data set is not a readable ZIP file."
        ) from None
    if not names:
        raise PixelTextValidationRefused(
            f"The ZIP file holds no HaN-Seg {image} volume."
        )
    ct = image == "CT"
    if workers == 1:
        one = finder() if made is None else made
        with zipfile.ZipFile(path) as archive:
            return [_measured(archive, name, one, ct) for name in names]
    # Each worker is a new interpreter, so that each imports ONNX Runtime
    # itself, as the detector requires, and makes its own detector.
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=workers,
        mp_context=multiprocessing.get_context("spawn"),
        initializer=_start_worker,
        initargs=(finder,),
    ) as pool:
        return list(
            pool.map(
                _measured_in_worker, [str(path)] * len(names), names, [ct] * len(names)
            )
        )


# The finder of a worker process, which _start_worker makes.
_WORKER: dict[str, TextFinder] = {}


def _start_worker(finder: Callable[[], TextFinder]) -> None:
    _WORKER["finder"] = finder()


def _measured_in_worker(
    path: str, name: str, ct: bool
) -> VolumeMeasures | VolumeNotMeasured:
    with zipfile.ZipFile(path) as archive:
        return _measured(archive, name, _WORKER["finder"], ct)


def _measured(
    archive: zipfile.ZipFile, name: str, finder: TextFinder, ct: bool
) -> VolumeMeasures | VolumeNotMeasured:
    """One volume's measures, or why it has none."""
    try:
        try:
            with archive.open(name) as stream:
                volume = nrrd.read_nrrd(stream)
        except nrrd.NrrdRefused as refused:
            return VolumeNotMeasured(f"not-read/{refused.problem.value}")
        return measure_volume(volume, finder, ct)
    except _NotMeasured as unusable:
        return VolumeNotMeasured(unusable.reason)
    # Anything else that a volume raises is counted, by where, rather than
    # stopping the check; its message, which could quote a value, is
    # dropped.
    except Exception as error:  # pylint: disable = broad-exception-caught
        return VolumeNotMeasured("crashed", crash_site(error))


def markdown(summary: Mapping[str, Any]) -> str:
    """Render :func:`summarise`'s counts, and nothing else, as a CommonMark
    page, so that the page shows no more than the JSON does."""
    data = summary["data"]
    volumes = summary["volumes"]
    slices = summary["slices"]
    by_volume = summary["volumes_by_regions"]
    regions = summary["regions"]
    detector = summary["detector"]
    method = detector["method"]
    lines = [
        f"# Text detector check on {data['name']} {summary['image']}",
        "",
        f"Each {summary['image']} volume's slices, given to the text finder "
        "as a de-identification run under the Clean Pixel Data Option gives "
        "it the frames of a series, and the regions that it finds counted. "
        "The data set holds no burned-in text, so each region is one that a "
        "run would black out in error and a reviewer would have to clear. "
        "Only counts are shown: no value, image, or case of the data set.",
        "",
        "| About | |",
        "| --- | --- |",
        f"| Data set | {data['name']} {data['version']}, "
        f"doi:{data['doi']}, {data['licence']} |",
        f"| File | {data['file']['size']} bytes, MD5 `{data['file']['md5']}`, "
        f"SHA-256 `{data['file']['sha256']}` |",
        "| Software | "
        + ", ".join(
            f"{name} {version}" for name, version in summary["software"].items()
        )
        + " |",
        f"| Finder | `{detector['finder']}` |",
        *(
            [f"| Model SHA-256 | `{method['model_sha256']}` |"]
            if "model_sha256" in method
            else []
        ),
        "",
        f"The data set: {data['citation']}.",
        "",
        "## Volumes",
        "",
        "| Volumes | Count |",
        "| --- | ---: |",
        f"| In the data set | {volumes['total']} |",
        f"| Measured | {volumes['measured']} |",
        *(
            f"| Not measured: `{reason}` | {count} |"
            for reason, count in volumes["not_measured"].items()
        ),
        *(
            f"| Crashed: `{site}` | {count} |"
            for site, count in volumes["crashed"].items()
        ),
        "",
        *_codes("Format", volumes["formats"], "Volumes"),
        *_codes("Plane of the slices", volumes["planes"], "Volumes"),
        *_bins("Larger side of a slice", volumes["slice_side"], "Volumes"),
        *_bins("Larger spacing within a slice", volumes["pixel_spacing"], "Volumes"),
        "## Slices",
        "",
        f"Slices searched: {slices['searched']}. Slices with a region: "
        f"{slices['with_a_region']}. Regions: {regions['total']}.",
        "",
        *_bins("Regions in a slice", slices["regions"], "Slices"),
        "## Volumes by their regions",
        "",
        f"Volumes with a region: {by_volume['with_a_region']}.",
        "",
        *_bins("Regions in a volume", by_volume["regions"], "Volumes"),
        *_bins(
            "Share of a volume's slices with a region",
            by_volume["share_of_slices_with_a_region"],
            "Volumes",
        ),
        "## Regions",
        "",
        *_bins("Area", regions["area"], "Regions"),
        *_bins("Shorter side", regions["shorter_side"], "Regions"),
        *_bins("Longer side over shorter", regions["elongation"], "Regions"),
    ]
    if regions["share_not_air"] is not None:
        lines += _bins(
            "Share of the region's pixels above -900 HU",
            regions["share_not_air"],
            "Regions",
        )
    if regions["score_margin"] is not None:
        lines += [
            *_bins("Score margin", regions["score_margin"], "Regions"),
            *_codes(
                "Renderings that gave the region", regions["renderings"], "Regions"
            ),
        ]
    lines += [
        *_grouped_tables("larger side of a slice", summary["by_slice_side"]),
        *_grouped_tables("larger spacing within a slice", summary["by_pixel_spacing"]),
    ]
    return "\n".join(lines).rstrip("\n") + "\n"


def _grouped_tables(title: str, grouped: Mapping[str, Any]) -> list[str]:
    """The tables of :func:`_grouped`'s counts: the volumes, slices, and
    regions in each bin, then, for the bins that hold a volume, the regions
    by score margin and by the renderings that gave them."""
    unit = grouped["unit"]
    lines = [
        f"## By the {title}",
        "",
        f"| {title.capitalize()} ({unit}) | Volumes | Slices searched "
        "| Slices with a region | Regions |",
        "| --- | ---: | ---: | ---: | ---: |",
        *(
            f"| {_range(each)} | {each['volumes']} | {each['slices_searched']} "
            f"| {each['slices_with_a_region']} | {each['regions']} |"
            for each in grouped["bins"]
        ),
        "",
    ]
    held = [each for each in grouped["bins"] if each["volumes"]]
    if not held or held[0]["score_margin"] is None:
        return lines
    header = " | ".join(f"{_range(each)} {unit}" for each in held)
    alignment = " | ".join("---:" for _ in held)
    margins = held[0]["score_margin"]
    lines += [
        f"Regions by score margin ({margins['unit']}) and {title}:",
        "",
        f"| Score margin | {header} |",
        f"| --- | {alignment} |",
        *(
            f"| {_range(margin)} | "
            + " | ".join(
                str(each["score_margin"]["bins"][row]["count"]) for each in held
            )
            + " |"
            for row, margin in enumerate(margins["bins"])
        ),
        "",
    ]
    codes = sorted({code for each in held for code in each["renderings"]})
    if not codes:
        return lines + [f"Regions by renderings and {title}: none.", ""]
    return lines + [
        f"Regions by the renderings that gave them and {title}:",
        "",
        f"| Renderings | {header} |",
        f"| --- | {alignment} |",
        *(
            f"| `{code}` | "
            + " | ".join(str(each["renderings"].get(code, 0)) for each in held)
            + " |"
            for code in codes
        ),
        "",
    ]


def _codes(title: str, counts: Mapping[str, int], noun: str) -> list[str]:
    """A table of counts by code."""
    if not counts:
        return [f"{title}: none.", ""]
    return [
        f"| {title} | {noun} |",
        "| --- | ---: |",
        *(f"| `{code}` | {count} |" for code, count in counts.items()),
        "",
    ]


def _bins(title: str, counts: Mapping[str, Any], noun: str) -> list[str]:
    """A table of counts by bin."""
    return [
        f"| {title} ({counts['unit']}) | {noun} |",
        "| --- | ---: |",
        *(f"| {_range(each)} | {each['count']} |" for each in counts["bins"]),
        "",
    ]


def _range(each: Mapping[str, Any]) -> str:
    low, high = each["from"], each["to"]
    if low is None:
        return f"below {high:g}"
    if high is None:
        return f"{low:g} or more"
    return f"{low:g} to under {high:g}"
