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

"""A development check of the Clean Pixel Data Option and the Clean
Recognizable Visual Features Option on public floating-point Parametric
Maps, which writes only counts.

NCI's Imaging Data Commons holds, in the version of its index that
:data:`~.text_evaluation_idc.INDEX_WHEEL` pins, one source of Parametric
Maps: the 691 maps of the ``tcga_gbm360`` analysis results of the TCGA-GBM
collection, under CC BY 4.0, each one frame of Float Pixel Data
(7FE0,0008). :func:`select` takes the index's Parametric Maps and refuses
the selection unless every one is of that analysis, collection, licence,
and DOI, is one instance, and is kept in IDC's public bucket, and there are
:data:`SERIES` of them; :func:`manifest` writes them as an ``s5cmd``
manifest, each series in a folder named by IDC's identifier of it.

:func:`check` refuses the downloaded files unless their count and the
SHA-256 of their sorted SHA-256s are those that :data:`SERIES` and
:data:`FILES_SHA256` pin, then gives each file to a de-identification
transform as a run does: under the Clean Pixel Data Option with the text
finder, counting each outcome, whether the written file holds its pixel
data in the element that held them with the same data type and shape, and
how many regions were blacked out; and under the Clean Recognizable Visual
Features Option, counting whether it is held without a verdict, whether the
QC pack previews it and shows it whole, and whether a face verdict of
absent, bound to the written pixel data as a reviewer's is, releases it
with Recognizable Visual Features (0028,0302) NO. A file whose check raises
is counted by the exception's type and place, never its message.

The maps are real patients' data, and this repository's logs and artefacts
are public, so the summary, labelled :data:`FORMAT`, and its page give only
counts, codes, digests, versions, and the data set's public identifiers: no
UID, name, date, path, or value of any file.

Run as ``python -m pymedphys._dicom.deidentify.parametric_map_check``. It
is not registered with the ``pymedphys`` command: nothing de-identification
related joins the public command line before the first supported release.
"""

from __future__ import annotations

import argparse
import collections
import dataclasses
import hashlib
import importlib.metadata
import io
import json
import pathlib
import platform
import re
import sys
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Protocol

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom

from . import policy, qc_previews, run
from .diagnostics import redacted_diagnostics
from .face_review import FaceReview, contour_data_sha256, pixel_data_sha256
from .face_validation import crash_site
from .instance_transform import HeldEvidence, InstanceTransform
from .keys import DeidKey
from .run_qc import RedactionMaterial
from .references import InstanceRecord
from .text_detection import TextBox
from .text_evaluation_idc import (
    INDEX_WHEEL,
    INDEX_WHEEL_SHA256,
    canonical_licence,
    index_rows,
)

FORMAT = "pymedphys-deid-parametric-map-check/1"
SOURCE = "NCI Imaging Data Commons"
COLLECTION_ID = "tcga_gbm"
ANALYSIS_RESULT_ID = "tcga_gbm360"
LICENCE = "CC BY 4.0"
DOI = "10.5281/zenodo.17470190"
PARAMETRIC_MAP_STORAGE = "1.2.840.10008.5.1.4.1.1.30"
# How many maps the pinned index holds, and the SHA-256 of their files'
# SHA-256s, each as 64 lower-case hex digits and a line feed, in order.
SERIES = 691
FILES_SHA256 = "610be3b8f65a128731a4d6705c0e70159315083483f39d4e4ef3f1e4d50a8a58"
# The columns of IDC's index that a selection reads.
COLUMNS = (
    "collection_id",
    "analysis_result_id",
    "crdc_series_uuid",
    "SOPClassUID",
    "license_short_name",
    "source_DOI",
    "series_aws_url",
    "instanceCount",
)
JSON_NAME = "parametric-map-check.json"
MARKDOWN_NAME = "parametric-map-check.md"
MANIFEST_NAME = "manifest.s5cmd"
SELECTION_NAME = "selection.json"
# The bins of how many regions a file's frame had blacked out.
REGION_BINS = ((0, 0), (1, 1), (2, 2), (3, 5), (6, 10), (11, None))

_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_BUCKET = re.compile(r"s3://idc-open-data/")
# A key and a QC pack reference that bind nothing outside the check.
_KEY = DeidKey(bytes(range(32)))
_REFERENCE = "A-" + "0123456789abcdef" * 2
_PIXEL_KEYWORDS = ("FloatPixelData", "DoubleFloatPixelData", "PixelData")


class CheckRefused(Exception):
    """The index, the files, or the arguments are not those the check
    pins; the message quotes no value of them."""


class Finder(Protocol):
    """What finds text in a frame, as a run's finder does, and describes
    what decides its boxes."""

    @property
    def method(self) -> Mapping[str, object]:
        """What decides the boxes, such as the model and its parameters."""
        raise NotImplementedError

    def find(self, frame: np.ndarray) -> tuple[TextBox, ...]:
        """Return the boxes around text in one frame."""
        raise NotImplementedError


@dataclasses.dataclass(frozen=True)
class MapSeries:
    """A Parametric Map's series in IDC's index, by IDC's identifier of its
    files and where they are kept."""

    crdc_series_uuid: str
    aws_url: str


def select(
    rows: Iterable[Mapping[str, object]], series: int = SERIES
) -> tuple[MapSeries, ...]:
    """Return the index's Parametric Maps, ordered by IDC's identifier of
    each.

    Raises
    ------
    CheckRefused
        Unless every Parametric Map is of :data:`ANALYSIS_RESULT_ID` in
        :data:`COLLECTION_ID`, under :data:`LICENCE` and :data:`DOI`, one
        instance, and kept in IDC's public bucket, and there are ``series``
        of them.
    """
    selected = []
    for row in rows:
        if row.get("SOPClassUID") != PARAMETRIC_MAP_STORAGE:
            continue
        if (
            row.get("analysis_result_id") != ANALYSIS_RESULT_ID
            or row.get("collection_id") != COLLECTION_ID
        ):
            raise CheckRefused("A Parametric Map is of another collection or analysis.")
        if canonical_licence(str(row.get("license_short_name"))) != LICENCE:
            raise CheckRefused("A Parametric Map is under another licence.")
        if row.get("source_DOI") != DOI:
            raise CheckRefused("A Parametric Map is of another DOI.")
        if row.get("instanceCount") != 1:
            raise CheckRefused("A Parametric Map's series is not one instance.")
        uuid, url = str(row.get("crdc_series_uuid")), str(row.get("series_aws_url"))
        bucket = _BUCKET.match(url)
        if not (
            _UUID.fullmatch(uuid) and bucket and url[bucket.end() :] == f"{uuid}/*"
        ):
            raise CheckRefused("A Parametric Map's files are not IDC's own.")
        selected.append(MapSeries(uuid, url))
    if len({each.crdc_series_uuid for each in selected}) != len(selected):
        raise CheckRefused("A Parametric Map's series is listed twice.")
    if len(selected) != series:
        raise CheckRefused("The index does not hold the pinned number of maps.")
    return tuple(sorted(selected, key=lambda each: each.crdc_series_uuid))


def manifest(selected: Sequence[MapSeries], destination: str) -> str:
    """The selected series as an ``s5cmd run`` manifest: each copied to a
    folder of its own, named by IDC's identifier of it, under
    ``destination``."""
    if not re.fullmatch(r"[A-Za-z0-9._/-]+", destination):
        raise CheckRefused("The destination must be a plain path.")
    folder = destination.rstrip("/") or "."
    return "".join(
        f"cp '{each.aws_url}' '{folder}/{each.crdc_series_uuid}/'\n"
        for each in selected
    )


def files_sha256(paths: Iterable[pathlib.Path]) -> tuple[str, int]:
    """The SHA-256 of the files' SHA-256s, each as 64 lower-case hex digits
    and a line feed, in order, and the files' total size in bytes."""
    digests, size = [], 0
    for path in paths:
        data = path.read_bytes()
        digests.append(hashlib.sha256(data).hexdigest())
        size += len(data)
    joined = "".join(f"{each}\n" for each in sorted(digests))
    return hashlib.sha256(joined.encode("ascii")).hexdigest(), size


@dataclasses.dataclass
class _Counts:
    """The counts that :func:`check` adds up, file by file."""

    elements: collections.Counter[str] = dataclasses.field(
        default_factory=collections.Counter
    )
    cleaned: collections.Counter[str] = dataclasses.field(
        default_factory=collections.Counter
    )
    reviewed: collections.Counter[str] = dataclasses.field(
        default_factory=collections.Counter
    )
    not_previewed: collections.Counter[str] = dataclasses.field(
        default_factory=collections.Counter
    )
    regions: collections.Counter[str] = dataclasses.field(
        default_factory=collections.Counter
    )
    crashed: collections.Counter[str] = dataclasses.field(
        default_factory=collections.Counter
    )


def check(
    folder: pathlib.Path,
    finder: Finder,
    *,
    series: int = SERIES,
    sha256: str = FILES_SHA256,
) -> dict[str, Any]:
    """Check each file below ``folder``, as the module describes, and
    return the summary.

    Raises
    ------
    CheckRefused
        Unless the files are ``series`` in number and the SHA-256 of their
        SHA-256s is ``sha256``.
    """
    paths = sorted(path for path in folder.rglob("*") if path.is_file())
    if len(paths) != series:
        raise CheckRefused("The folder does not hold the pinned number of files.")
    digest, size = files_sha256(paths)
    if digest != sha256:
        raise CheckRefused("The files are not the pinned ones.")
    counts = _Counts()
    cleaner = _transform([policy.CLEAN_PIXEL_DATA], finder=finder)
    holder = _transform(
        [policy.CLEAN_RECOGNIZABLE_VISUAL_FEATURES],
        face_review=FaceReview(
            _REFERENCE, frozenset(), frozenset(), frozenset(), frozenset()
        ),
    )
    with redacted_diagnostics():
        for path in paths:
            data = path.read_bytes()
            try:
                _check_file(data, cleaner, holder, counts)
            # Anything that a file raises is counted, by where; its message,
            # which could quote a value, is dropped.
            except Exception as error:  # pylint: disable = broad-exception-caught
                counts.crashed[crash_site(error)] += 1
    return {
        "format": FORMAT,
        "data": {
            "source": SOURCE,
            "collection_id": COLLECTION_ID,
            "analysis_result_id": ANALYSIS_RESULT_ID,
            "licence": LICENCE,
            "doi": DOI,
            "index": {"wheel": INDEX_WHEEL, "sha256": INDEX_WHEEL_SHA256},
            "files": len(paths),
            "bytes": size,
            "files_sha256": digest,
        },
        "software": _software(),
        "finder": dict(finder.method),
        "pixel_data_elements": _sorted(counts.elements),
        "clean_pixel_data": {
            **_sorted(counts.cleaned),
            "regions_per_file": {
                _bin_name(low, high): counts.regions[_bin_name(low, high)]
                for low, high in REGION_BINS
            },
        },
        "clean_recognizable_visual_features": {
            **_sorted(counts.reviewed),
            "not_previewed": _sorted(counts.not_previewed),
        },
        "crashed": _sorted(counts.crashed),
    }


def _check_file(
    data: bytes, cleaner: InstanceTransform, holder: InstanceTransform, counts: _Counts
) -> None:
    source = pydicom.dcmread(io.BytesIO(data))
    keyword = next((each for each in _PIXEL_KEYWORDS if each in source), "none")
    counts.elements[keyword] += 1
    cleaned = cleaner(data, InstanceRecord.from_file(data))
    if isinstance(cleaned, run.Sequestered):
        for reason in cleaned.reasons:
            counts.cleaned[f"sequestered: {reason.value}"] += 1
    else:
        _count_cleaned(source, keyword, cleaned, counts)
    held = holder(data, InstanceRecord.from_file(data))
    if isinstance(held, run.Sequestered):
        for reason in held.reasons:
            counts.reviewed[f"sequestered: {reason.value}"] += 1
        return
    if not isinstance(held.evidence, HeldEvidence):
        counts.reviewed["released without a verdict"] += 1
        return
    counts.reviewed["held without a verdict"] += 1
    previews = qc_previews.previews_of({0: held.data}, {0})
    counts.reviewed["previewed"] += bool(previews.previews)
    for entry in previews.not_previewed:
        counts.not_previewed[entry.reason.value] += 1
    if 0 not in previews.pixels_shown:
        counts.reviewed["not shown whole"] += 1
        return
    counts.reviewed["shown whole"] += 1
    released = _transform(
        [policy.CLEAN_RECOGNIZABLE_VISUAL_FEATURES],
        face_review=_absent(data, held.data),
    )(data, InstanceRecord.from_file(data))
    if isinstance(released, run.Sequestered) or isinstance(
        released.evidence, HeldEvidence
    ):
        counts.reviewed["held after a face verdict of absent"] += 1
        return
    written = pydicom.dcmread(io.BytesIO(released.data))
    feature = written.get("RecognizableVisualFeatures")
    counts.reviewed[
        "released on a face verdict of absent"
        + (", Recognizable Visual Features NO" if feature == "NO" else "")
    ] += 1


def _count_cleaned(
    source: pydicom.Dataset, keyword: str, cleaned: run.Transformed, counts: _Counts
) -> None:
    held = cleaned.evidence
    reasons = (
        [each.reason.value for each in held.held]
        if isinstance(held, HeldEvidence)
        else ["released"]
    )
    for reason in reasons:
        counts.cleaned[f"outcome: {reason}"] += 1
    written = pydicom.dcmread(io.BytesIO(cleaned.data))
    others = [each for each in _PIXEL_KEYWORDS if each != keyword and each in written]
    before, after = source.pixel_array, written.pixel_array
    kept = keyword in written and not others and after.dtype == before.dtype
    kept = kept and after.shape == before.shape
    counts.cleaned[
        "written in the element that held it, same data type and shape"
        if kept
        else "written otherwise"
    ] += 1
    if not kept:
        return
    changed = before.view(np.uint8) != after.view(np.uint8)
    counts.cleaned["pixels changed" if changed.any() else "pixels unchanged"] += 1
    regions = sum(
        len(boxes)
        for entry in cleaned.qc
        if isinstance(entry, RedactionMaterial)
        for _, boxes in entry.regions
    )
    for low, high in REGION_BINS:
        if regions >= low and (high is None or regions <= high):
            counts.regions[_bin_name(low, high)] += 1


def _absent(source: bytes, written: bytes) -> FaceReview:
    """A face verdict of absent on ``source``, bound to its written file's
    pixel data and contours, as a reviewed pack's is."""
    dataset = pydicom.dcmread(io.BytesIO(written))
    sha = hashlib.sha256(source).digest()
    pixels = pixel_data_sha256(dataset)
    frames = int(dataset.get("NumberOfFrames") or 1)
    return FaceReview(
        _REFERENCE,
        frozenset({sha}),
        frozenset(),
        frozenset({(sha, pixels)}),
        frozenset({(sha, contour_data_sha256(dataset))}),
        absent_frames=frozenset({(sha, pixels, frames)}),
    )


def _transform(options, **kwargs) -> InstanceTransform:
    return InstanceTransform(
        policy.compose_custom_policy(options), _KEY, unvalidated_policy=True, **kwargs
    )


def _bin_name(low: int, high: int | None) -> str:
    if high is None:
        return f"{low} or more"
    return str(low) if low == high else f"{low} to {high}"


def _sorted(counter: Mapping[str, int]) -> dict[str, int]:
    return dict(sorted(counter.items()))


def _software() -> dict[str, str]:
    """The versions of Python and of the packages that the counts depend on."""
    versions = {"python": platform.python_version()}
    for package in ("pymedphys", "numpy", "scipy", "pydicom", "onnxruntime"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = "unknown"
    return versions


def markdown(summary: Mapping[str, Any]) -> str:
    """Render the summary's counts as a CommonMark page, and nothing else."""
    data = summary["data"]
    lines = [
        "# Pixel options on public floating-point Parametric Maps",
        "",
        "Each map given to a de-identification transform under the Clean "
        "Pixel Data Option, with the text finder, and under the Clean "
        "Recognizable Visual Features Option, then previewed and given a "
        "face verdict of absent. Only counts are shown: no value, image, "
        "or file of the data set.",
        "",
        "| About | |",
        "| --- | --- |",
        f"| Source | {data['source']}, `{data['collection_id']}`, analysis "
        f"results `{data['analysis_result_id']}`, {data['licence']}, "
        f"doi:{data['doi']} |",
        f"| Index | `{data['index']['wheel']}`, SHA-256 `{data['index']['sha256']}` |",
        f"| Files | {data['files']}, {data['bytes']} bytes, SHA-256 of their "
        f"SHA-256s `{data['files_sha256']}` |",
        "| Software | "
        + ", ".join(
            f"{name} {version}" for name, version in summary["software"].items()
        )
        + " |",
    ]
    if summary["finder"]:
        lines.append(f"| Finder | `{json.dumps(summary['finder'], sort_keys=True)}` |")
    lines += ["", *_table("Pixel data elements", summary["pixel_data_elements"])]
    cleaned = dict(summary["clean_pixel_data"])
    regions = cleaned.pop("regions_per_file")
    lines += [*_table("Clean Pixel Data", cleaned)]
    lines += [*_table("Regions blacked out per file", regions)]
    reviewed = dict(summary["clean_recognizable_visual_features"])
    not_previewed = reviewed.pop("not_previewed")
    lines += [*_table("Clean Recognizable Visual Features", reviewed)]
    if not_previewed:
        lines += [*_table("Not previewed", not_previewed)]
    if summary["crashed"]:
        lines += [
            *_table("Files whose check raised, by type and place", summary["crashed"])
        ]
    return "\n".join(lines).rstrip("\n") + "\n"


def _table(title: str, counts: Mapping[str, int]) -> list[str]:
    return [
        f"## {title}",
        "",
        "| | Files |",
        "| --- | ---: |",
        *(f"| {name} | {count} |" for name, count in counts.items()),
        "",
    ]


def _detector() -> Finder:
    """The run's text finder."""
    # pylint: disable-next = import-outside-toplevel
    from .text_detection import TextDetector

    return TextDetector()


def main(argv: Sequence[str] | None = None) -> int:
    """Select the maps from IDC's pinned index, or check the downloaded
    maps, as the module describes.

    ``select`` takes the pinned wheel of idc-index-data, ``--downloads``,
    the folder that the manifest copies each series into, and ``--out``, a
    directory that must not exist, and writes ``manifest.s5cmd`` and
    ``selection.json``, which holds counts alone. ``check`` takes the
    downloads and ``--out``, a directory that must not exist, writes
    ``parametric-map-check.json`` and ``parametric-map-check.md``, and
    prints the page.

    Raises
    ------
    SystemExit
        With a refusal's message, which quotes no value, and no traceback.
    """
    parser = argparse.ArgumentParser(
        prog="python -m pymedphys._dicom.deidentify.parametric_map_check",
        description=(
            "Check the Clean Pixel Data and Clean Recognizable Visual Features "
            "Options on IDC's public floating-point Parametric Maps, and write "
            "only counts. For development only."
        ),
    )
    commands = parser.add_subparsers(dest="command", required=True)
    selecting = commands.add_parser("select", help="Write the maps' s5cmd manifest.")
    selecting.add_argument(
        "wheel", type=pathlib.Path, help="idc-index-data's pinned wheel."
    )
    selecting.add_argument(
        "--downloads", required=True, help="Where s5cmd copies them."
    )
    selecting.add_argument("--out", required=True, type=pathlib.Path)
    checking = commands.add_parser("check", help="Check the downloaded maps.")
    checking.add_argument("downloads", type=pathlib.Path)
    checking.add_argument("--out", required=True, type=pathlib.Path)
    arguments = parser.parse_args(argv)
    try:
        if arguments.out.exists():
            raise CheckRefused("--out must not exist.")
        if arguments.command == "select":
            selected = select(index_rows(arguments.wheel, columns=COLUMNS))
            text = manifest(selected, arguments.downloads)
            arguments.out.mkdir(parents=True)
            (arguments.out / MANIFEST_NAME).write_text(text, encoding="utf-8")
            described = {"format": FORMAT, "source": SOURCE, "series": len(selected)}
            (arguments.out / SELECTION_NAME).write_text(
                json.dumps(described, indent=2) + "\n", encoding="utf-8"
            )
            return 0
        summary = check(arguments.downloads, _detector())
    except CheckRefused as refusal:
        raise SystemExit(str(refusal)) from None
    page = markdown(summary)
    arguments.out.mkdir(parents=True)
    (arguments.out / JSON_NAME).write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    (arguments.out / MARKDOWN_NAME).write_text(page, encoding="utf-8")
    sys.stdout.write(page)
    return 0


if __name__ == "__main__":
    sys.exit(main())
