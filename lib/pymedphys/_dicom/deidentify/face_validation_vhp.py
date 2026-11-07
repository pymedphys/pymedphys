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
# One module runs the finder three ways on each series, measures each
# outcome against reference globes, defaces, and renders, and documents
# each measure, so it is long.

"""The face block and CT defacing, checked on the NLM Visible Human
Project's CT (D-057).

The U.S. National Library of Medicine's Visible Human Project scanned two
cadavers, a man and a woman, from head to toe. NCI Imaging Data Commons
(IDC) converted the scans to DICOM, as the collection
``nlm_visible_human_project``, and serves them from its public bucket under
NLM's Terms and Conditions. They are real human heads, with globes, orbital
fat, bony orbits, a closed skull, and a face, which no phantom that this
project has found has together, and they are held-out evidence: the
finder's tests were set without them, and its settings are not to be tuned
to them.

:data:`SERIES` pins each of the collection's CT series, by IDC's
``crdc_series_uuid``, its file count, and the digest of its files
(:func:`manifest_digest`). :func:`check_visible_human` reads each series
from ``<directory>/<uuid>/``, refuses one whose files differ, and gives its
slices to the finder three ways:

1. **As a run gives them** (``engine``): every file of the series to
   :func:`~pymedphys._dicom.deidentify.face_blocks.find_face_blocks`, as a
   run's records, so that the stack checks, the 400 mm head reach, and the
   air check apply, as they do in a run.
2. **By stack** (``stacks``): the slices that share orientation, pixel
   spacing, rows and columns, and in-plane origin, each stack given to
   ``find_face_blocks`` as a series of its own. IDC keeps each scan as one
   series whose field of view, and so pixel spacing, changes along the
   body, so a run refuses every series whole as ``not-one-stack``; this is
   what a run would find if each field of view were its own series.
3. **Resampled** (``resampled``): the slices within the head reach of the
   series' superior end, each resampled by linear interpolation onto the
   in-plane grid of the stack with the largest field of view, the finer
   where two are as large, and given to
   :class:`~pymedphys._dicom.deidentify.defacing.FaceFinder` directly, with
   points outside a slice's own field of view as padding. A run does not
   resample, so this is evidence on the finder's anatomy tests alone.

Each way's outcome is measured (:func:`finding`): the finder's outcome,
what its inspection saw (balls considered and kept, pairs tested), the
globes and block that it found, and, for the three series that hold a head,
how those compare with reference globe centres placed by hand on the
native slices (:attr:`VhpSeries.globes`), independently of the finder's
output: the distance from each found globe to the reference on its side,
whether the sides are swapped, and the ball that the finder considered
nearest each reference globe, with its surround test's shares, so that a
refusal can be traced to the test that gave it.

For each block found, and for a reference block placed from the reference
globes as the finder places one from its globes (:func:`reference_block`),
so that defacing is exercised on real anatomy even where the finder
refuses, each slice is given to
:class:`~pymedphys._dicom.deidentify.face_blocks.CtDefacer`, as a run gives
it, and what it would write is measured (:func:`defacing_measures`): the
slices and volume written as air, the tissue among it, the tissue in the
block that is kept, as the brain is, any pixel written outside the block,
and how much of each reference globe, a sphere of
:data:`REFERENCE_RADIUS`, is written as air. The tissue about each
reference globe is measured too (:func:`reference_tissue`): the median
Hounsfield units in its core and in a shell about it, where a living
globe's orbital fat lies, and each one's share within the finder's soft
tissue window.

Only :attr:`VhpSeries.rendered` series, the three heads, are
rendered (:func:`render_series`): the QC pack's skin surface views of its
head alone, its axial slices from :data:`HEAD_BELOW` below the reference
globes to :data:`HEAD_ABOVE` above them, of any stack, resampled onto the
grid of the stack that holds the globes, as received and as each block
would deface each slice in its own geometry, and slices through
each reference globe with the globes and blocks marked, each image carrying
NLM's attribution (:data:`ATTRIBUTION`) and :data:`NOTICE`.

The JSON summary, labelled :data:`FORMAT`, gives the source, its terms,
the attribution, the software's versions, and the engine's settings with
the measures. Nothing here changes a setting of the finder or the defacer.
"""

from __future__ import annotations

import collections
import dataclasses
import functools
import hashlib
import math
import os
import pathlib
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom
from pymedphys._imports import scipy

from . import defacing, face_blocks, qc_surfaces
from .defacing import FaceBlock, FaceBlockRefused, FaceFinder, FaceInspection
from .face_blocks import CT_IMAGE, CtDefacer, SeriesDefacing
from .face_validation import (
    FaceValidationRefused,
    _settings,
    _software,
    crash_site,
)
from .references import InstanceRecord

Point = tuple[float, float, float]

FORMAT = "pymedphys-deid-face-validation-vhp/1"
BUCKET = "s3://idc-open-data"
COLLECTION = "nlm_visible_human_project"
IDC_RELEASE = "v19"
# The Zenodo record of IDC's manifests for the collection at IDC_RELEASE.
RECORD_DOI = "10.5281/zenodo.16114440"
LICENCE = "National Library of Medicine Terms and Conditions; May 21, 2019"
TERMS = "https://www.nlm.nih.gov/databases/download/terms_and_conditions.html"
# NLM's Terms and Conditions ask each user to acknowledge NLM as the source
# with this phrase, "in a clear and conspicuous manner".
ATTRIBUTION = "Courtesy of the U.S. National Library of Medicine."
# And each redistributor not to imply NLM's endorsement, and to keep the
# most current version or say clearly that it may not be current.
NOTICE = (
    "NLM Visible Human Project CT, as converted to DICOM by NCI Imaging Data "
    f"Commons (collection {COLLECTION}, IDC data release {IDC_RELEASE}). "
    "NLM has not endorsed PyMedPhys or these results, which may not reflect "
    "the most current or accurate data available from NLM."
)
HELD_OUT = (
    "Held-out evidence: the face block finder's settings were not set from "
    "these scans and are not to be tuned to them."
)
# A typical adult globe's radius, about half its axial length: the sphere
# about each reference centre whose removal is measured, and the radius of
# the globes from which reference_block places its block.
REFERENCE_RADIUS = 12.0  # millimetres
# How far, at most, a reference centre placed by hand may lie from the
# globe's true centre, as judged when it was placed.
REFERENCE_TOLERANCE = 3.0  # millimetres
# The core about a reference centre, and the shell about the globe, where
# the orbital fat about a living globe lies, whose values are measured.
CORE = 6.0  # millimetres
SHELL = (1.1 * REFERENCE_RADIUS, 1.5 * REFERENCE_RADIUS)  # millimetres
_ROUND = 1  # decimals of millimetres reported
ANTERIOR = (0.0, -1.0, 0.0)  # the patient's anterior, in patient coordinates
# The heights about the reference globes that a render shows: from below
# the chin to above the vertex of an adult head.
HEAD_BELOW = 110.0  # millimetres below the lower globe's centre
HEAD_ABOVE = 130.0  # millimetres above the higher globe's centre
# How near a slice must lie to a globe's height for its stack to hold it.
GLOBE_SLICE = 3.0  # millimetres
# The longest gap between slices that a volume spans; the series' slices
# are 1 to 6 mm apart, except where part of the body was left unscanned.
_LONGEST_GAP = 10.0  # millimetres
JSON_NAME = "face-validation-vhp.json"
MARKDOWN_NAME = "face-validation-vhp.md"
RENDERS = "renders"


@dataclasses.dataclass(frozen=True)
class VhpSeries:
    """One pinned CT series of the collection.

    Attributes
    ----------
    uuid : str
        IDC's ``crdc_series_uuid``: the series' folder in the bucket.
    subject : str
        IDC's Patient ID: ``VHP-F`` for the female cadaver, ``VHP-M`` for
        the male.
    description : str
        What the series covers, from IDC's metadata and its headers.
    files : int
        How many files the series has.
    sha256 : str
        :func:`manifest_digest` of its files.
    globes : tuple of tuple of float, optional
        The reference centre of each globe, the patient's right first, in
        millimetres in the series' patient coordinates, placed by hand on
        the native slices as the midpoint of the globe's extent along each
        axis, within :data:`REFERENCE_TOLERANCE`; None for a series without
        a head.
    rendered : bool
        Whether its face is rendered.
    name : str
        The name of its renders' files; its subject's where empty.
    """

    uuid: str
    subject: str
    description: str
    files: int
    sha256: str
    globes: tuple[Point, Point] | None = None
    rendered: bool = False
    name: str = ""


# Placed on 1 November 2026 from axial, coronal, and sagittal views and
# Hounsfield unit profiles through each globe, before any reference
# measure was taken.
SERIES: tuple[VhpSeries, ...] = (
    VhpSeries(
        "2397283b-eb7d-41f7-b310-cc2bc0181865",
        "VHP-F",
        "female, head to thighs, head first supine, 1 mm slices",
        985,
        "1f5785d9305d390f1890e40aeca50444fe4b131b4f7fc4c1786e2f52e63bb1ab",
        ((-33.5, -88.0, -143.5), (26.5, -86.5, -143.5)),
        rendered=True,
    ),
    VhpSeries(
        "e82cd88f-9865-49c8-a14f-7b67c40dac90",
        "VHP-F",
        "female, femur to toes, feet first supine, 1 mm slices",
        749,
        "01918bb7f664434efd502d7d05a7944de1a429a13066b069ddacae7fad58876a",
    ),
    VhpSeries(
        "477cf391-d387-4ec0-8daa-85207c808a77",
        "VHP-M",
        "male, before freezing, pelvis to vertex, head first supine, 1 and 3 mm slices",
        417,
        "92f4961414cf99fddde2bb55832799ec06386df47e55d87fd007f93f45f8ea20",
        ((-33.5, -145.5, 295.0), (30.0, -145.0, 295.0)),
        rendered=True,
        name="VHP-M-before-freezing",
    ),
    VhpSeries(
        "29c772e1-1ea7-4c7e-8de0-dedafb72e347",
        "VHP-M",
        "male, before freezing, whole body, feet first supine, 5 mm slices",
        104,
        "4265c6212183d59823106bf6a718e0f0a2a1bff509b440359907d1c51d198e57",
    ),
    VhpSeries(
        "f3a311eb-3abb-4b22-a28d-36ede7ddf127",
        "VHP-M",
        "male, frozen, head to thighs, head first supine, 1 mm slices",
        844,
        "4873a77612efa11702c6063541a0f957d80a1f7982235eacf4b7e625fa7818c3",
        ((-32.5, -103.0, -121.0), (38.0, -103.0, -123.5)),
        rendered=True,
        name="VHP-M-frozen",
    ),
    VhpSeries(
        "aa81356d-32f2-4b71-ad81-c1defa3175ca",
        "VHP-M",
        "male, frozen, lower body, feet first supine, 1 mm slices",
        809,
        "ad9f164c259d3146a1bf763c9f7ecd50ec347c3054d2b929b1eb5a8e9d87d577",
    ),
    VhpSeries(
        "3455adc0-1341-4058-88a2-c511e38e72ef",
        "VHP-M",
        "male, frozen, legs, feet first supine, 1 mm slices",
        224,
        "9e8e2317cdef0e9db642382f5e202d28561ebd1b13ebffeb2482f194d714ebef",
    ),
    VhpSeries(
        "8b6ea205-de0e-4f5d-9e35-da656a19193e",
        "VHP-M",
        "male, frozen, one projection image",
        1,
        "ca31ba3e3f7567e31f7d7c55b2eb85aeaf4b282c74acdecbdb1ac18752ca4850",
    ),
    VhpSeries(
        "3453f22d-8656-412b-8583-0d84eb73b7ca",
        "VHP-M",
        "male, frozen, one projection image",
        1,
        "d2b6a2262ec91115e7fb18e10a5233a76b22bb24576553df932dcdffae14b97d",
    ),
    VhpSeries(
        "60aa046a-8577-40d9-ae34-9eddd164d8e6",
        "VHP-M",
        "male, frozen, one projection image",
        1,
        "f0254f6b1228ef15b0470faee7e53c1908a558bbeb0f2763aa85b7ff8d078341",
    ),
    VhpSeries(
        "87bd805f-6b39-4ee3-99db-ccf4f8b38a24",
        "VHP-M",
        "male, frozen, one projection image",
        1,
        "663dd086bb09603d2eccb3c84211284dccffd3b24079fe4357ba6dfd03355040",
    ),
)


@dataclasses.dataclass(frozen=True)
class _Header:
    """What the check needs of one slice, read without its pixels."""

    path: pathlib.Path
    position: tuple[float, float, float]
    orientation: tuple[float, ...]
    spacing: tuple[float, float]
    shape: tuple[int, int]
    rescale: tuple[float, float]  # slope, then intercept

    @property
    def normal(self) -> np.ndarray:
        return np.cross(self.orientation[:3], self.orientation[3:])

    def points(self) -> np.ndarray:
        """The x, y, and z of each pixel's centre, rows by columns by 3."""
        rows = np.arange(self.shape[0], dtype=float)[:, None, None] * self.spacing[0]
        columns = np.arange(self.shape[1], dtype=float)[None, :, None] * self.spacing[1]
        return (
            np.asarray(self.position)
            + columns * np.asarray(self.orientation[:3])
            + rows * np.asarray(self.orientation[3:])
        )

    def hounsfield(self) -> np.ndarray:
        """The slice's values, in Hounsfield units."""
        dataset = pydicom.dcmread(self.path)
        return dataset.pixel_array * self.rescale[0] + self.rescale[1]


def manifest_digest(folder: os.PathLike[str] | str) -> tuple[int, str]:
    """The count and digest of the files in a series' folder.

    The digest is the SHA-256 of the lines ``<SHA-256 of a file>  <its
    name>``, each ended by a line feed, in the order of the names' bytes,
    as ``sha256sum * | LC_ALL=C sort -k2 | sha256sum`` gives it.
    """
    files = sorted(
        (path for path in pathlib.Path(folder).iterdir() if path.is_file()),
        key=lambda path: path.name.encode(),
    )
    lines = []
    for path in files:
        digest = hashlib.sha256()
        with path.open("rb") as file:
            for block in iter(functools.partial(file.read, 1 << 20), b""):
                digest.update(block)
        lines.append(f"{digest.hexdigest()}  {path.name}\n")
    return len(files), hashlib.sha256("".join(lines).encode()).hexdigest()


def check_visible_human(
    directory: os.PathLike[str] | str,
    renders: os.PathLike[str] | str | None = None,
    series: Sequence[VhpSeries] | None = None,
) -> dict[str, Any]:
    """Check each series, as the module describes.

    Parameters
    ----------
    directory
        Holds each series' files in a folder named by its UUID.
    renders
        A directory for the renders of :attr:`VhpSeries.rendered` series,
        or None for none.
    series
        The series to check; :data:`SERIES` where None.

    Raises
    ------
    FaceValidationRefused
        If a series' folder is missing, or its files are not those pinned.
    """
    root = pathlib.Path(directory)
    series = SERIES if series is None else tuple(series)
    # Every series is verified before any is checked, so that nothing is
    # rendered from a set that is refused.
    for each in series:
        folder = root / each.uuid
        if not folder.is_dir():
            raise FaceValidationRefused(f"Series {each.uuid} is missing.")
        count, digest = manifest_digest(folder)
        if (count, digest) != (each.files, each.sha256):
            raise FaceValidationRefused(
                f"Series {each.uuid} is not the one pinned: {count} files, "
                f"digest {digest}."
            )
    checked = [check_series(each, root / each.uuid, renders) for each in series]
    return {
        "format": FORMAT,
        "source": {
            "collection": COLLECTION,
            "idc_release": IDC_RELEASE,
            "record_doi": RECORD_DOI,
            "bucket": BUCKET,
            "licence": LICENCE,
            "terms": TERMS,
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


def check_series(
    each: VhpSeries,
    folder: pathlib.Path,
    renders: os.PathLike[str] | str | None = None,
) -> dict[str, Any]:
    """One series' measures: what each way of giving its slices to the
    finder finds, and what each block would deface."""
    result: dict[str, Any] = {
        "series": each.uuid,
        "subject": each.subject,
        "description": each.description,
        "files": each.files,
        "sha256": each.sha256,
        "reference_globes": None if each.globes is None else _points(each.globes),
    }
    try:
        paths = sorted(folder.iterdir(), key=lambda path: path.name.encode())
        headers = [_header(path) for path in paths]
        stacks = stacks_of(headers)
        result["stacks"] = [_stack_description(headers, stack) for stack in stacks]
        blocks: dict[str, FaceBlock] = {}
        engine = _engine(paths)
        result["engine"] = finding(None, engine.block, _code(engine), each.globes)
        if engine.block is not None:
            blocks["engine"] = engine.block
        result["by_stack"] = []
        for number, stack in enumerate(stacks, start=1):
            outcome, inspection = _stack_outcome([paths[i] for i in stack])
            result["by_stack"].append(
                {
                    "stack": number,
                    **finding(inspection, outcome.block, _code(outcome), each.globes),
                }
            )
            if outcome.block is not None:
                blocks[f"stack {number}"] = outcome.block
        resampled = resampled_inspection(headers)
        if resampled is None:
            result["resampled"] = {"outcome": "not-applicable"}
        else:
            grid, inspection = resampled
            block, problem = _decided(inspection)
            result["resampled"] = {
                "grid": grid,
                **finding(inspection, block, problem, each.globes),
            }
            if block is not None:
                blocks["resampled"] = block
        if each.globes is not None:
            reference = reference_block(each.globes, headers)
            blocks["reference"] = reference
            result["reference_block"] = _block_geometry(reference)
            result["reference_tissue"] = reference_tissue(headers, each.globes)
        result["defacing"] = {
            label: {
                **defacing_measures(block, headers, each.globes),
                **(
                    {}
                    if label == "reference" or "reference" not in blocks
                    else {"against_reference": _against(block, blocks["reference"])}
                ),
            }
            for label, block in blocks.items()
        }
        if each.rendered and renders is not None and each.globes is not None:
            result["renders"] = render_series(
                each, headers, stacks, blocks, pathlib.Path(renders)
            )
    # Anything else that a series raises is reported by where, so that the
    # other series are still checked.
    except Exception as error:  # pylint: disable = broad-exception-caught
        result["crashed"] = crash_site(error)
    return result


def _header(path: pathlib.Path) -> _Header:
    dataset = pydicom.dcmread(path, stop_before_pixels=True)
    return _Header(
        path,
        tuple(float(v) for v in dataset.ImagePositionPatient),  # type: ignore[arg-type]
        tuple(float(v) for v in dataset.ImageOrientationPatient),
        (float(dataset.PixelSpacing[0]), float(dataset.PixelSpacing[1])),
        (int(dataset.Rows), int(dataset.Columns)),
        (
            float(dataset.get("RescaleSlope", 1) or 1),
            float(dataset.get("RescaleIntercept", 0) or 0),
        ),
    )


def stacks_of(headers: Sequence[_Header]) -> list[list[int]]:
    """The indices of the slices of each stack: those that share
    orientation, pixel spacing, rows and columns, and in-plane origin, each
    stack's in order along its normal, the stacks in order of their first
    slice."""
    keyed: dict[tuple[Any, ...], list[int]] = collections.defaultdict(list)
    for index, each in enumerate(headers):
        normal = each.normal
        position = np.asarray(each.position)
        in_plane = position - (position @ normal) * normal
        keyed[
            (
                tuple(round(v, 4) for v in each.orientation),
                tuple(round(v, 6) for v in each.spacing),
                each.shape,
                tuple(round(float(v), 2) for v in in_plane),
            )
        ].append(index)
    stacks = [
        sorted(
            indices,
            key=lambda i: float(np.asarray(headers[i].position) @ headers[i].normal),
        )
        for indices in keyed.values()
    ]
    return sorted(
        stacks,
        key=lambda s: float(np.asarray(headers[s[0]].position) @ headers[s[0]].normal),
    )


def _stack_description(headers: Sequence[_Header], stack: list[int]) -> dict[str, Any]:
    first, last = headers[stack[0]], headers[stack[-1]]
    offsets = [float(np.asarray(headers[i].position) @ first.normal) for i in stack]
    gaps = sorted({round(b - a, 3) for a, b in zip(offsets, offsets[1:])})
    return {
        "slices": len(stack),
        "pixel_spacing_mm": list(first.spacing),
        "shape": list(first.shape),
        "orientation": [round(v, 4) for v in first.orientation],
        "first_position_mm": [round(v, _ROUND) for v in first.position],
        "last_position_mm": [round(v, _ROUND) for v in last.position],
        "slice_gaps_mm": gaps,
    }


def _reader(paths: Sequence[pathlib.Path]) -> Callable[[int], bytes | None]:
    def read(position: int) -> bytes | None:
        try:
            return paths[position].read_bytes()
        except OSError:
            return None

    return read


def _records(paths: Sequence[pathlib.Path]) -> dict[int, InstanceRecord]:
    return {
        position: InstanceRecord.from_file(path.read_bytes())
        for position, path in enumerate(paths)
    }


def _engine(paths: Sequence[pathlib.Path]) -> SeriesDefacing:
    """The series' outcome as a run finds it."""
    records = _records(paths)
    outcomes = face_blocks.find_face_blocks(records, _reader(paths))
    if len(outcomes) != 1:
        raise ValueError("a pinned series is one CT Image series")
    return next(iter(outcomes.values()))


def _stack_outcome(
    paths: Sequence[pathlib.Path],
) -> tuple[SeriesDefacing, FaceInspection | None]:
    """A stack's outcome, given to the finder as a run gives it a series,
    and what the finder saw."""
    records = _records(paths)
    if any(record.iod != CT_IMAGE for record in records.values()):
        raise ValueError("a pinned series holds only CT Image instances")
    read = _reader(paths)
    outcomes = face_blocks.find_face_blocks(records, read)
    try:
        inspection = face_blocks.inspect_series(sorted(records), read)
    # The finder's ValueError for geometry that it cannot use, such as a
    # single projection image, leaves nothing to inspect, as a run leaves
    # the series undefaced.
    except ValueError:
        inspection = None
    return next(iter(outcomes.values())), inspection


def _code(outcome: SeriesDefacing) -> str | None:
    return None if outcome.problem is None else outcome.problem.value


def _decided(inspection: FaceInspection) -> tuple[FaceBlock | None, str | None]:
    try:
        return inspection.block(), None
    except FaceBlockRefused as refused:
        return None, refused.problem.value


def resampled_inspection(
    headers: Sequence[_Header],
) -> tuple[dict[str, Any], FaceInspection] | None:
    """What the finder sees in the slices within the head reach of the
    series' superior end, each resampled onto one in-plane grid, as the
    module describes; None where the slices do not share an axial
    orientation, or are fewer than two."""
    orientation = headers[0].orientation
    if any(
        not np.allclose(each.orientation, orientation, atol=1e-4) for each in headers
    ):
        return None
    normal = headers[0].normal
    if abs(abs(float(normal[2])) - 1) > 1e-4 or len(headers) < 2:
        return None
    heights = [each.position[2] for each in headers]
    top = max(heights)
    kept = [
        each
        for each in sorted(headers, key=lambda h: h.position[2])
        if each.position[2] >= top - face_blocks.HEAD_REACH
    ]
    if len(kept) < 2 or len({each.position[2] for each in kept}) != len(kept):
        return None

    def extent(each: _Header) -> tuple[float, float]:
        return (
            each.spacing[1]
            * (each.shape[1] - 1)
            * each.spacing[0]
            * (each.shape[0] - 1),
            -each.spacing[0],
        )

    target = max(kept, key=extent)
    in_plane = _in_plane(target)
    finder = FaceFinder(
        orientation,
        [(in_plane[0], in_plane[1], each.position[2]) for each in kept],
        target.spacing,
        target.shape,
    )
    for each in kept:
        finder.add(_on_grid(each.hounsfield(), each, target))
    grid = {
        "slices": len(kept),
        "pixel_spacing_mm": list(target.spacing),
        "shape": list(target.shape),
        "origin_mm": [round(float(v), _ROUND) for v in in_plane[:2]],
    }
    return grid, finder.inspect()


def _in_plane(target: _Header) -> np.ndarray:
    """The x and y of an axial slice's first pixel, at z of 0."""
    return np.array([target.position[0], target.position[1], 0.0])


def _on_grid(values: np.ndarray, each: _Header, target: _Header) -> np.ndarray:
    """An axial slice's values resampled by linear interpolation onto
    another axial slice's in-plane grid, as float32, a point outside the
    slice's own field of view as NaN, which the finder and the renders take
    as padding."""
    along_row = np.asarray(each.orientation[:3])
    down_column = np.asarray(each.orientation[3:])
    offset = _in_plane(target) - _in_plane(each)
    target_row = np.asarray(target.orientation[:3])
    target_column = np.asarray(target.orientation[3:])
    rows = np.arange(target.shape[0], dtype=float)[:, None] * target.spacing[0]
    columns = np.arange(target.shape[1], dtype=float)[None, :] * target.spacing[1]
    # Each target pixel's row and column in the slice's own grid.
    across = (
        offset @ along_row
        + columns * float(target_row @ along_row)
        + rows * float(target_column @ along_row)
    )
    down = (
        offset @ down_column
        + columns * float(target_row @ down_column)
        + rows * float(target_column @ down_column)
    )
    return scipy.ndimage.map_coordinates(
        np.asarray(values, dtype=np.float32),
        [
            np.broadcast_to(down / each.spacing[0], target.shape),
            np.broadcast_to(across / each.spacing[1], target.shape),
        ],
        order=1,
        mode="constant",
        cval=np.nan,
    ).astype(np.float32)


def finding(
    inspection: FaceInspection | None,
    block: FaceBlock | None,
    problem: str | None,
    globes: tuple[Point, Point] | None,
) -> dict[str, Any]:
    """The measures of one outcome of the finder.

    Parameters
    ----------
    inspection
        What the finder saw, or None where it was not reached or is not
        given.
    block
        The block found, or None.
    problem
        The reason that no block was found, or None.
    globes
        The reference globes, the patient's right first, or None.
    """
    result: dict[str, Any] = {"outcome": "block" if block is not None else problem}
    if inspection is not None:
        kept = [ball for ball in inspection.balls if ball.kept]
        result["inspection"] = {
            "voxel_mm": round(inspection.voxel, 3),
            "balls_considered": len(inspection.balls),
            "balls_tested": sum(ball.centre is not None for ball in inspection.balls),
            "balls_kept": len(kept),
            "pairs_tested": len(inspection.pairs),
            "pairs_in_orbits": sum(pair.in_orbits for pair in inspection.pairs),
            "pairs_passing": sum(pair.eyes for pair in inspection.pairs),
        }
    if block is not None:
        result["block"] = _block_geometry(block)
    if globes is None:
        return result
    references = [np.asarray(globe, dtype=float) for globe in globes]
    if block is not None:
        found = [np.asarray(globe, dtype=float) for globe in block.globes]
        result["globe_error_mm"] = [
            _mm(np.linalg.norm(f - r)) for f, r in zip(found, references)
        ]
        result["swapped"] = bool(
            np.linalg.norm(found[0] - references[1])
            + np.linalg.norm(found[1] - references[0])
            < np.linalg.norm(found[0] - references[0])
            + np.linalg.norm(found[1] - references[1])
        )
    if inspection is not None:
        result["at_reference"] = _at_reference(inspection, references)
    return result


def _at_reference(
    inspection: FaceInspection, references: Sequence[np.ndarray]
) -> dict[str, Any]:
    """The balls that the finder considered nearest each reference globe,
    and the tests of the pair of kept balls nearest them."""
    tested = [
        (index, ball)
        for index, ball in enumerate(inspection.balls)
        if ball.centre is not None
    ]
    sides = []
    nearest_kept = []
    for reference in references:
        side: dict[str, Any] = {}
        if tested:
            index, ball = min(tested, key=functools.partial(_distance, reference))
            side["nearest_tested"] = {
                "distance_mm": _mm(np.linalg.norm(np.asarray(ball.centre) - reference)),
                "radius_mm": _mm(ball.radius),
                "outside": round(float(ball.outside or 0.0), 3),
                "best_half": round(float(ball.best_half or 0.0), 3),
                "kept": ball.kept,
            }
        kept = [(i, b) for i, b in tested if b.kept]
        if kept:
            index, ball = min(kept, key=functools.partial(_distance, reference))
            distance = float(np.linalg.norm(np.asarray(ball.centre) - reference))
            side["nearest_kept_mm"] = _mm(distance)
            nearest_kept.append(index if distance <= REFERENCE_RADIUS else None)
        else:
            side["nearest_kept_mm"] = None
            nearest_kept.append(None)
        sides.append(side)
    result: dict[str, Any] = {"right": sides[0], "left": sides[1], "pair": None}
    if None not in nearest_kept and nearest_kept[0] != nearest_kept[1]:
        wanted = set(nearest_kept)
        for pair in inspection.pairs:
            if {pair.right, pair.left} == wanted:
                result["pair"] = _pair(pair)
    return result


def _distance(reference: np.ndarray, item: tuple[int, defacing.Ball]) -> float:
    """The distance from a reference centre to a tested ball's centre."""
    return float(np.linalg.norm(np.asarray(item[1].centre) - reference))


def _pair(pair: defacing.PairTest) -> dict[str, Any]:
    def fronts(each: tuple[defacing.Front, defacing.Front] | None) -> Any:
        if each is None:
            return None
        return [
            {
                "depth_mm": None if math.isinf(front.depth) else _mm(front.depth),
                "fat_mm": _mm(front.fat),
                "bone": front.bone,
                "open": front.open,
            }
            for front in each
        ]

    return {
        "side_by_side": pair.side_by_side,
        "lateral_bone": list(pair.lateral),
        "superior_bone": list(pair.superior),
        "front": fronts(pair.front),
        "back": fronts(pair.back),
        "passes": pair.eyes,
    }


def _block_geometry(block: FaceBlock) -> dict[str, Any]:
    anterior = np.asarray(block.anterior)
    turn = math.degrees(math.atan2(float(anterior[0]), -float(anterior[1])))
    return {
        "globes_mm": _points(block.globes),
        "origin_mm": [_mm(v) for v in block.origin],
        "anterior": [round(float(v), 4) for v in block.anterior],
        "turn_degrees": round(turn, 1),
        "inferior_limit_mm": _mm(block.inferior_limit),
    }


def reference_block(
    globes: tuple[Point, Point], headers: Sequence[_Header]
) -> FaceBlock:
    """The block that the finder would place from the reference globes, as
    globes of :data:`REFERENCE_RADIUS`: its plane :data:`~.defacing.MARGIN`
    behind their midpoint, perpendicular to the line between them, and its
    floor at their lower inferior edge, lowered by the finder's least voxel
    or by the slices' greatest gap within the globes' height, whichever is
    larger."""
    right, left = (np.asarray(globe, dtype=float) for globe in globes)
    anterior = defacing._anterior(  # pylint: disable = protected-access
        left - right
    )
    middle = (right + left) / 2
    low = min(right[2], left[2]) - REFERENCE_RADIUS
    high = max(right[2], left[2]) + REFERENCE_RADIUS
    heights = np.sort(
        [each.position[2] for each in headers if abs(each.normal[2]) > 0.5]
    )
    gap = 0.0
    if heights.size > 1:
        near = (heights[1:] >= low) & (heights[:-1] <= high)
        if near.any():
            gap = float(np.diff(heights)[near].max())
    inferior = low - max(defacing.MINIMUM_VOXEL, gap)
    return FaceBlock(
        tuple(float(v) for v in middle - defacing.MARGIN * anterior),  # type: ignore[arg-type]
        tuple(float(v) for v in anterior),  # type: ignore[arg-type]
        float(inferior),
        (
            tuple(float(v) for v in right),  # type: ignore[arg-type]
            tuple(float(v) for v in left),
        ),
    )


def _against(block: FaceBlock, reference: FaceBlock) -> dict[str, Any]:
    """How a found block lies against the reference block: its plane's
    distance ahead of the reference plane at the reference globes'
    midpoint, along the reference's anterior, the angle between their
    normals, and the height of its floor above the reference floor."""
    middle = (np.asarray(reference.globes[0]) + np.asarray(reference.globes[1])) / 2
    anterior = np.asarray(block.anterior)
    reference_anterior = np.asarray(reference.anterior)
    # Where the found plane meets the line through the midpoint along the
    # reference's anterior.
    denominator = float(anterior @ reference_anterior)
    ahead = (
        float((np.asarray(block.origin) - middle) @ anterior) / denominator
        - float((np.asarray(reference.origin) - middle) @ reference_anterior)
        if abs(denominator) > 1e-9
        else math.nan
    )
    angle = math.degrees(
        math.acos(max(-1.0, min(1.0, float(anterior @ reference_anterior))))
    )
    return {
        "plane_ahead_mm": _mm(ahead),
        "angle_degrees": round(angle, 1),
        "floor_above_mm": _mm(block.inferior_limit - reference.inferior_limit),
    }


def _gaps(headers: Sequence[_Header]) -> dict[pathlib.Path, float]:
    """Each slice's thickness for volumes.

    Slices of the same orientation are taken together whatever their stack,
    since one stack's slices can lie either side of another's. Each distinct
    position along the normal stands for the mean of its gaps to the
    distinct positions either side of it, leaving out a gap longer than
    :data:`_LONGEST_GAP`, where part of the body was left unscanned, or for
    1 mm where no gap is left. That thickness is shared among the slices at
    the position, so that a volume that two stacks image is counted once."""
    gaps: dict[pathlib.Path, float] = {}
    by_orientation: dict[tuple[float, ...], list[_Header]] = collections.defaultdict(
        list
    )
    for each in headers:
        by_orientation[tuple(round(v, 4) for v in each.orientation)].append(each)
    for group in by_orientation.values():
        normal = group[0].normal
        offsets = [float(np.asarray(each.position) @ normal) for each in group]
        distinct = sorted({round(offset, 2) for offset in offsets})
        share = collections.Counter(round(offset, 2) for offset in offsets)
        thickness: dict[float, float] = {}
        for k, offset in enumerate(distinct):
            near = [
                gap
                for j in (k - 1, k + 1)
                if 0 <= j < len(distinct)
                and (gap := abs(distinct[j] - offset)) <= _LONGEST_GAP
            ]
            thickness[offset] = float(np.mean(near)) if near else 1.0
        for each, offset in zip(group, offsets):
            key = round(offset, 2)
            gaps[each.path] = thickness[key] / share[key]
    return gaps


def defacing_measures(
    block: FaceBlock,
    headers: Sequence[_Header],
    globes: tuple[Point, Point] | None,
) -> dict[str, Any]:
    """What :class:`~.face_blocks.CtDefacer` would write of each slice of
    the series, as the module describes."""
    gaps = _gaps(headers)
    references = (
        [] if globes is None else [np.asarray(globe, dtype=float) for globe in globes]
    )
    poles = [
        reference + REFERENCE_RADIUS * np.asarray(block.anterior)
        for reference in references
    ]
    pole_best = [(math.inf, False) for _ in poles]
    sphere = [[0, 0] for _ in references]  # voxels, then those written
    totals: dict[str, float] = collections.defaultdict(float)
    slices_written = 0
    for each in headers:
        points = each.points()
        if float(points[..., 2].max()) <= block.inferior_limit:
            continue
        dataset = pydicom.dcmread(each.path)
        stored = dataset.pixel_array
        hounsfield = stored * each.rescale[0] + each.rescale[1]
        inside = block.contains(points)
        mask = CtDefacer(block, dataset).mask(0, stored)
        written = (
            np.zeros(each.shape, dtype=bool) if mask is None else mask.mask.astype(bool)
        )
        volume = each.spacing[0] * each.spacing[1] * gaps[each.path] / 1000.0  # ml
        tissue = hounsfield > defacing.BODY
        slices_written += bool(written.any())
        totals["written"] += int(written.sum())
        totals["written_ml"] += float(written.sum()) * volume
        totals["tissue_written_ml"] += float((written & tissue).sum()) * volume
        totals["tissue_kept_in_block_ml"] += (
            float((inside & tissue & ~written).sum()) * volume
        )
        totals["written_outside_block"] += int((written & ~inside).sum())
        for k, reference in enumerate(references):
            distance = np.linalg.norm(points - reference, axis=-1)
            near = distance <= REFERENCE_RADIUS
            sphere[k][0] += int(near.sum())
            sphere[k][1] += int((near & written).sum())
            pole = np.linalg.norm(points - poles[k], axis=-1)
            at = np.unravel_index(int(np.argmin(pole)), pole.shape)
            if float(pole[at]) < pole_best[k][0]:
                pole_best[k] = (float(pole[at]), bool(written[at]))
    result: dict[str, Any] = {
        "slices_written": slices_written,
        "pixels_written": int(totals["written"]),
        "written_ml": _ml(totals["written_ml"]),
        "tissue_written_ml": _ml(totals["tissue_written_ml"]),
        "tissue_kept_in_block_ml": _ml(totals["tissue_kept_in_block_ml"]),
        "pixels_written_outside_block": int(totals["written_outside_block"]),
    }
    if references:
        result["reference_globes"] = [
            {
                "share_written": round(written / voxels, 3) if voxels else None,
                "anterior_pole_written": pole_best[k][1],
            }
            for k, (voxels, written) in enumerate(sphere)
        ]
    return result


def reference_tissue(
    headers: Sequence[_Header], globes: tuple[Point, Point]
) -> list[dict[str, Any]]:
    """The Hounsfield units about each reference globe, as the module
    describes: the median and the share in the finder's soft tissue window
    of the pixels within :data:`CORE` of its centre, and of those from
    :data:`SHELL`'s inner to its outer radius."""
    low, high = defacing.SOFT_TISSUE
    result = []
    for globe in globes:
        centre = np.asarray(globe, dtype=float)
        core: list[np.ndarray] = []
        shell: list[np.ndarray] = []
        for each in headers:
            points = each.points()
            distance = np.linalg.norm(points - centre, axis=-1)
            if float(distance.min()) > SHELL[1]:
                continue
            values = each.hounsfield()
            core.append(values[distance <= CORE])
            shell.append(values[(distance >= SHELL[0]) & (distance <= SHELL[1])])
        measured = {}
        for name, parts in (("core", core), ("shell", shell)):
            values = np.concatenate(parts) if parts else np.zeros(0)
            measured[name] = {
                "pixels": int(values.size),
                "median_hu": round(float(np.median(values)), 1)
                if values.size
                else None,
                "soft_tissue_share": (
                    round(float(((values >= low) & (values <= high)).mean()), 3)
                    if values.size
                    else None
                ),
            }
        result.append(measured)
    return result


def render_series(
    each: VhpSeries,
    headers: Sequence[_Header],
    stacks: Sequence[list[int]],
    blocks: Mapping[str, FaceBlock],
    out: pathlib.Path,
) -> list[str]:
    """Render the head of a :attr:`VhpSeries.rendered` series, as the
    module describes, and return the names of the files written."""
    # Imported here, since only a rendering check needs it.
    from pymedphys._imports import plt  # pylint: disable = import-outside-toplevel

    if each.globes is None:
        return []
    out.mkdir(parents=True, exist_ok=True)
    stack = _head_stack(headers, stacks, each.globes)
    slices = [headers[i] for i in stack]
    target = slices[0]
    head = _head_slices(headers, stack, each.globes)
    directions = [
        target.normal,
        np.asarray(target.orientation[3:]),
        np.asarray(target.orientation[:3]),
    ]
    offsets = [float(np.asarray(s.position) @ target.normal) for s in head]
    grid = qc_surfaces.grid(
        directions, offsets, target.spacing, target.shape, qc_surfaces.Threshold.CT
    )
    surfaces = {"as received": qc_surfaces.Surface(grid)}
    for label in blocks:
        surfaces[label] = qc_surfaces.Surface(grid)
    # Slices through each reference globe, as received.
    near = {
        index: s.hounsfield().astype(np.float32)
        for index, s in enumerate(slices)
        if min(abs(s.position[2] - globe[2]) for globe in each.globes) <= 40.0
    }
    for s in head:
        dataset = pydicom.dcmread(s.path)
        stored = dataset.pixel_array
        values = (stored * s.rescale[0] + s.rescale[1]).astype(np.float32)
        surfaces["as received"].add(_on_grid(values, s, target))
        for label, block in blocks.items():
            mask = CtDefacer(block, dataset).mask(0, stored)
            defaced = values.copy()
            if mask is not None:
                defaced[mask.mask] = mask.value * s.rescale[0] + s.rescale[1]
            surfaces[label].add(_on_grid(defaced, s, target))
    names = []
    for label, surface in surfaces.items():
        image = surface.image()
        if image is None:
            continue
        name = f"{each.name or each.subject}-surface-{label.replace(' ', '-')}.png"
        width, height = image.shape[1] / 100, image.shape[0] / 100
        figure = plt.figure(figsize=(max(width, 6.0), height + 1.2))
        axes = figure.add_axes(
            (0.0, 0.6 / (height + 1.2), 1.0, height / (height + 1.2))
        )
        axes.imshow(image, cmap="gray", vmin=0, vmax=255, interpolation="nearest")
        axes.set_axis_off()
        title = (
            "Skin surface as received"
            if label == "as received"
            else f"Skin surface defaced by the {label} block"
        )
        _caption(figure, f"{each.name or each.subject}: {title}")
        figure.savefig(out / name, dpi=100, metadata={"Software": None})
        plt.close(figure)
        names.append(name)
    name = f"{each.name or each.subject}-globes.png"
    _globe_panels(plt, each, slices, near, blocks, out / name)
    names.append(name)
    (out / "NOTICE.txt").write_text(f"{ATTRIBUTION}\n\n{NOTICE}\n", encoding="utf-8")
    names.append("NOTICE.txt")
    return names


def _head_stack(
    headers: Sequence[_Header], stacks: Sequence[list[int]], globes: tuple[Point, Point]
) -> list[int]:
    """The stack with a slice within :data:`GLOBE_SLICE` of each reference
    globe's height, the one with most slices there where more than one
    has."""

    def near(stack: list[int], globe: Point) -> int:
        return sum(abs(headers[i].position[2] - globe[2]) <= GLOBE_SLICE for i in stack)

    holding = [stack for stack in stacks if all(near(stack, globe) for globe in globes)]
    if not holding:
        raise ValueError("no stack holds the reference globes")
    return max(holding, key=lambda stack: sum(near(stack, g) for g in globes))


def _head_slices(
    headers: Sequence[_Header], stack: list[int], globes: tuple[Point, Point]
) -> list[_Header]:
    """The axial slices of the head, from :data:`HEAD_BELOW` below the lower
    reference globe to :data:`HEAD_ABOVE` above the higher, of any stack,
    in order of height, the globes' stack's where two lie at one height."""
    low = min(globe[2] for globe in globes) - HEAD_BELOW
    high = max(globe[2] for globe in globes) + HEAD_ABOVE
    chosen: dict[float, _Header] = {}
    for index in sorted(stack) + [i for i in range(len(headers)) if i not in stack]:
        each = headers[index]
        height = round(each.position[2], 3)
        if (
            low <= height <= high
            and abs(abs(float(each.normal[2])) - 1) <= 1e-4
            and height not in chosen
        ):
            chosen[height] = each
    return [chosen[height] for height in sorted(chosen)]


def _caption(figure: Any, title: str) -> None:
    figure.text(0.01, 0.995, title, ha="left", va="top", fontsize=10, color="black")
    figure.text(
        0.01,
        0.005,
        f"{ATTRIBUTION} {HELD_OUT}",
        ha="left",
        va="bottom",
        fontsize=7,
        color="black",
        wrap=True,
    )


_COLOURS = {"reference": "tab:red", "resampled": "tab:cyan", "engine": "tab:green"}


def _globe_panels(
    plt: Any,
    each: VhpSeries,
    slices: Sequence[_Header],
    near: Mapping[int, np.ndarray],
    blocks: Mapping[str, FaceBlock],
    path: pathlib.Path,
) -> None:
    """Axial, coronal, and sagittal slices through each reference globe,
    with the reference globes (+), each block's globes (x), and each
    block's edges marked."""
    assert each.globes is not None
    indices = sorted(near)
    volume = np.stack([near[i] for i in indices])
    heights = np.array([slices[i].position[2] for i in indices])
    first = slices[indices[0]]
    x0, y0 = first.position[0], first.position[1]
    spacing = first.spacing
    half = 35.0
    figure, axes = plt.subplots(2, 3, figsize=(15, 10.6))
    for row, globe in enumerate(each.globes):
        x, y, z = globe
        column = int(round((x - x0) / spacing[1]))
        line = int(round((y - y0) / spacing[0]))
        level = int(np.argmin(np.abs(heights - z)))
        span = int(round(half / spacing[0]))
        views = (
            (
                volume[level, line - span : line + span, column - span : column + span],
                (x - half, x + half, y + half, y - half),
                f"axial at z = {heights[level]:.1f} mm",
                ("x", "y"),
            ),
            (
                volume[:, line, column - span : column + span][::-1],
                (x - half, x + half, heights[0], heights[-1]),
                f"coronal at y = {y:.1f} mm",
                ("x", "z"),
            ),
            (
                volume[:, line - span : line + span, column][::-1],
                (y - half, y + half, heights[0], heights[-1]),
                f"sagittal at x = {x:.1f} mm",
                ("y", "z"),
            ),
        )
        side = "right" if row == 0 else "left"
        for k, (image, extent, title, plane) in enumerate(views):
            axis = axes[row, k]
            axis.imshow(
                image, cmap="gray", vmin=-200, vmax=200, extent=extent, aspect="auto"
            )
            axis.set_title(f"{side} globe, {title}", fontsize=9)
            axis.set_xlim(extent[0], extent[1])
            if plane[1] == "z":
                axis.set_ylim(z - half, z + half)
            for label, block in blocks.items():
                colour = _COLOURS.get(label, "tab:orange")
                for found in block.globes:
                    coordinates = dict(zip("xyz", found))
                    axis.plot(
                        coordinates[plane[0]],
                        coordinates[plane[1]],
                        "x",
                        color=colour,
                        ms=9,
                    )
                _edges(axis, block, plane, globe, colour, label)
            for reference in each.globes:
                coordinates = dict(zip("xyz", reference))
                axis.plot(
                    coordinates[plane[0]],
                    coordinates[plane[1]],
                    "+",
                    color="tab:red",
                    ms=14,
                )
            axis.tick_params(labelsize=7)
    axes[0, 0].legend(fontsize=7, loc="lower right")
    _caption(
        figure,
        f"{each.name or each.subject}: reference globes (+, red) and each block's globes (x) "
        "and edges",
    )
    figure.savefig(path, dpi=80, metadata={"Software": None})
    plt.close(figure)


def _edges(
    axis: Any,
    block: FaceBlock,
    plane: tuple[str, str],
    globe: Point,
    colour: str,
    label: str,
) -> None:
    """Draw where a block's plane, and its floor, cross a view."""
    origin = np.asarray(block.origin)
    anterior = np.asarray(block.anterior)
    if plane == ("x", "y"):
        # The plane's trace: points with (p - origin) . anterior = 0.
        xs = np.array([globe[0] - 35.0, globe[0] + 35.0])
        if abs(anterior[1]) > 1e-6:
            ys = origin[1] - (xs - origin[0]) * anterior[0] / anterior[1]
            axis.plot(xs, ys, "-", color=colour, lw=1, label=f"{label} block")
    elif plane == ("y", "z"):
        if abs(anterior[1]) > 1e-6:
            y = origin[1] - (globe[0] - origin[0]) * anterior[0] / anterior[1]
            axis.axvline(y, color=colour, lw=1)
        axis.axhline(block.inferior_limit, color=colour, lw=1, ls="--")
    else:
        axis.axhline(block.inferior_limit, color=colour, lw=1, ls="--")


def _points(points: Sequence[Sequence[float]]) -> list[list[float]]:
    return [[_mm(v) for v in point] for point in points]


def _mm(value: float) -> float:
    return round(float(value), _ROUND)


def _ml(value: float) -> float:
    return round(float(value), 1)
