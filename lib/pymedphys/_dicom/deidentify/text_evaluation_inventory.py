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

"""Count what a collection's DICOM files are, before the text detector is
evaluated on them (D-056).

:func:`inventory` reads each file's attributes up to its Pixel Data and
counts the files of each collection, and of all together, by:

- SOP Class, by the name in pydicom's dictionary, or a code for a private
  or unknown one;
- Modality, among the defined terms of :data:`MODALITIES`;
- Manufacturer, as one of the vendors of :data:`VENDORS`, matched by fixed
  patterns, or ``other``;
- Rows, Columns, and the larger of them, in fixed bins of pixels;
- the larger pixel spacing, in fixed bins of millimetres, from the Pixel
  Measures functional group, Pixel Spacing, Image Plane Pixel Spacing, or
  Imager Pixel Spacing;
- Number of Frames, in fixed bins;
- each value of Image Type among :data:`IMAGE_TYPES`, such as
  ``LOCALIZER`` or ``SCREEN SAVE``, with ``other`` for any other;
- Burned In Annotation and Recognizable Visual Features (``YES``, ``NO``,
  absent, or ``other``);
- Photometric Interpretation, among its defined terms;
- Bits Stored, as its number;
- the Transfer Syntax, by its name in pydicom's dictionary;
- whether the file holds Pixel Data;

and in the crosses that sampling needs (:data:`CROSSES`). It also counts
the distinct patients, studies, and series of each collection, a patient
being an ID with its issuer within one collection, and the frames of each
SOP Class, which sets how long the detector takes.

Every label is a defined term or standard value, a bin, or one of the
fixed codes ``absent`` (the attribute is not there or is empty),
``malformed`` (it cannot be read as its type), and ``other`` (it is
neither, such as a vendor's own term), so no free text of a file, and no
identifier, value, or path, reaches the inventory
(:data:`INVENTORY_FORMAT`); a file that cannot be read is counted by why,
and one whose reading raises by the exception's type and place, never its
message. Identifiers are only counted, through a salted digest held in
memory.
"""

from __future__ import annotations

import dataclasses
import hashlib
import importlib.metadata
import pathlib
import re
import zipfile
from collections.abc import Iterable, Iterator, Mapping, Sequence
from typing import IO, Any

from pymedphys._imports import pydicom

from .face_validation import PIXEL_SPACING, Bins, crash_site
from .pixel_text_validation import SLICE_SIDE
from .text_evaluation import _label
from .text_evaluation_sources import _numbers, _sop_class_name, _spacing, _text

INVENTORY_FORMAT = "pymedphys-deid-dicom-inventory/1"
_DIGEST_SALT = "pymedphys-dicom-inventory-identifier/1"

# The defined terms of Modality (0008,0060) in the DICOM Standard's
# Information Object Definitions; any other value counts as ``other``.
MODALITIES = frozenset(
    {
        "AR", "ASMT", "AU", "BDUS", "BI", "BMD", "CFM", "CR", "CT", "CTPROTOCOL",
        "DMS", "DG", "DOC", "DX", "ECG", "EEG", "EMG", "EOG", "EPS", "ES", "FID",
        "GM", "HC", "HD", "IO", "IOL", "IVOCT", "IVUS", "KER", "KO", "LEN", "LS",
        "MG", "MR", "M3D", "NM", "OAM", "OCT", "OP", "OPM", "OPT", "OPTBSV",
        "OPTENF", "OPV", "OSS", "OT", "PA", "PLAN", "POS", "PR", "PT", "PX",
        "REG", "RESP", "RF", "RTDOSE", "RTIMAGE", "RTINTENT", "RTPLAN", "RTRAD",
        "RTRECORD", "RTSEGANN", "RTSTRUCT", "RWV", "SEG", "SM", "SMR", "SR",
        "SRF", "STAIN", "TEXTUREMAP", "TG", "US", "VA", "XA", "XAPROTOCOL", "XC",
    }
)  # fmt: skip

# Vendors, each with the patterns, matched in Manufacturer (0008,0070)
# without regard to case, that name it. The first vendor that matches
# names the file; a value that none matches is ``other``.
VENDORS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("GE", (r"\bGE\b", r"GENERAL ELECTRIC", r"\bGEMS\b")),
    ("Siemens", (r"SIEMENS",)),
    ("Philips", (r"PHILIPS", r"\bADAC\b", r"\bMARCONI\b", r"\bPICKER\b")),
    ("Canon or Toshiba", (r"CANON", r"TOSHIBA")),
    ("Hitachi or Fujifilm", (r"HITACHI", r"FUJI")),
    ("United Imaging", (r"UNITED IMAGING", r"\bUIH\b")),
    ("Neusoft", (r"NEUSOFT",)),
    ("Samsung", (r"SAMSUNG",)),
    ("Carestream or Kodak", (r"CARESTREAM", r"KODAK")),
    ("Agfa", (r"AGFA",)),
    ("Konica Minolta", (r"KONICA",)),
    ("Hologic", (r"HOLOGIC",)),
    ("Varian", (r"VARIAN",)),
    ("Elekta", (r"ELEKTA", r"\bIMPAC\b")),
    ("Accuray", (r"ACCURAY", r"TOMOTHERAPY")),
    ("ViewRay", (r"VIEWRAY",)),
    ("Brainlab", (r"BRAINLAB",)),
    ("RaySearch", (r"RAYSEARCH",)),
    ("MIM Software", (r"\bMIM\b",)),
    ("Mirada", (r"MIRADA",)),
    ("Velocity", (r"VELOCITY",)),
    ("IBA", (r"\bIBA\b",)),
    ("Mevion", (r"MEVION",)),
    ("Bruker", (r"BRUKER",)),
    ("Mediso", (r"MEDISO",)),
)
_VENDOR_PATTERNS = tuple(
    (name, tuple(re.compile(each, re.IGNORECASE) for each in patterns))
    for name, patterns in VENDORS
)

# Values of Image Type (0008,0008) that are counted by name: its defined
# terms in the IODs in scope; any other value counts as ``other``.
IMAGE_TYPES = frozenset(
    {
        "ORIGINAL", "DERIVED", "PRIMARY", "SECONDARY",
        "AXIAL", "LOCALIZER", "VOLUME", "MPR", "MIP", "MINIP", "REFORMATTED",
        "PROJECTION IMAGE", "CINE", "SCREEN SAVE", "SNAPSHOT",
        "DRR", "PORTAL", "SIMULATOR", "RADIOGRAPH", "BLANK", "FLUENCE",
        "STATIC", "DYNAMIC", "GATED", "WHOLE BODY", "IMAGE", "RECON TOMO",
        "TOMO", "GATED TOMO", "RECON GATED TOMO",
        "M", "P", "R", "I", "MAGNITUDE", "PHASE", "REAL", "IMAGINARY",
        "NONE", "MIXED",
    }
)  # fmt: skip
PHOTOMETRIC = frozenset(
    {
        "MONOCHROME1", "MONOCHROME2", "PALETTE COLOR", "RGB", "YBR_FULL",
        "YBR_FULL_422", "YBR_PARTIAL_420", "YBR_PARTIAL_422", "YBR_ICT",
        "YBR_RCT", "HSV", "ARGB", "CMYK",
    }
)  # fmt: skip
FRAMES = Bins("frames", (1, 2, 3, 17, 65, 257, 1025))
SIDE = SLICE_SIDE
DIMENSIONS = (
    "sop_class",
    "modality",
    "manufacturer",
    "rows",
    "columns",
    "larger_side",
    "pixel_spacing",
    "frames",
    "image_type",
    "burned_in_annotation",
    "recognizable_visual_features",
    "photometric",
    "bits_stored",
    "transfer_syntax",
    "pixel_data",
)
# The crosses that sampling is planned by.
CROSSES: tuple[tuple[str, ...], ...] = (
    ("sop_class", "modality"),
    ("sop_class", "burned_in_annotation"),
    ("sop_class", "image_type"),
    ("sop_class", "larger_side"),
    ("sop_class", "frames"),
    ("modality", "manufacturer"),
)


class InventoryRefused(Exception):
    """An inventory that cannot be taken; the message quotes no value."""


@dataclasses.dataclass(frozen=True, repr=False)
class InventoryFile:
    """One file to count: its collection, and how to open it, never named
    in the inventory.

    Attributes
    ----------
    collection : str
    path : str
        The file's path, or the ZIP file's where ``member`` is given.
    member : str or None
        The file's name within the ZIP file.
    """

    collection: str
    path: str
    member: str | None = None

    def __repr__(self) -> str:
        return "InventoryFile()"

    def open(self) -> IO[bytes]:
        if self.member is None:
            return open(self.path, "rb")
        archive = zipfile.ZipFile(self.path)
        try:
            return _Member(archive, archive.open(self.member))
        except Exception:
            archive.close()
            raise


class _Member:
    """A ZIP member's stream that closes its archive with it."""

    def __init__(self, archive: zipfile.ZipFile, stream: IO[bytes]) -> None:
        self._archive = archive
        self._stream = stream

    def read(self, size: int = -1) -> bytes:
        return self._stream.read(size)

    def seek(self, offset: int, whence: int = 0) -> int:
        return self._stream.seek(offset, whence)

    def tell(self) -> int:
        return self._stream.tell()

    def __enter__(self) -> _Member:
        return self

    def __exit__(self, *_: object) -> None:
        self._stream.close()
        self._archive.close()


def folder_files(
    root: pathlib.Path | str, collection: str
) -> tuple[InventoryFile, ...]:
    """Every file under a folder, at any depth, in order of path."""
    root = pathlib.Path(root)
    return tuple(
        InventoryFile(collection, str(path))
        for path in sorted(each for each in root.rglob("*") if each.is_file())
    )


def zip_files(path: pathlib.Path | str, collection: str) -> tuple[InventoryFile, ...]:
    """Every file in a ZIP file, in order of name, without extracting it."""
    with zipfile.ZipFile(path) as archive:
        names = sorted(
            info.filename for info in archive.infolist() if not info.is_dir()
        )
    return tuple(InventoryFile(collection, str(path), name) for name in names)


@dataclasses.dataclass
class _Counts:
    files: int = 0
    read: int = 0
    skipped: dict[str, int] = dataclasses.field(default_factory=dict)
    crashed: dict[str, int] = dataclasses.field(default_factory=dict)
    by: dict[str, dict[str, int]] = dataclasses.field(default_factory=dict)
    crosses: dict[str, dict[tuple[str, ...], int]] = dataclasses.field(
        default_factory=dict
    )
    frames_by_sop_class: dict[str, int] = dataclasses.field(default_factory=dict)
    patients: set[bytes] = dataclasses.field(default_factory=set)
    studies: set[bytes] = dataclasses.field(default_factory=set)
    series: set[bytes] = dataclasses.field(default_factory=set)

    def add(self, labels: Mapping[str, Sequence[str]], crosses) -> None:
        self.read += 1
        for dimension, values in labels.items():
            counted = self.by.setdefault(dimension, {})
            for value in values:
                counted[value] = counted.get(value, 0) + 1
        for cross in crosses:
            counted_cross = self.crosses.setdefault("+".join(cross), {})
            for combination in _combinations([labels[name] for name in cross]):
                counted_cross[combination] = counted_cross.get(combination, 0) + 1


def _combinations(values: Sequence[Sequence[str]]) -> Iterator[tuple[str, ...]]:
    if not values:
        yield ()
        return
    for first in values[0]:
        for rest in _combinations(values[1:]):
            yield (first, *rest)


def _digest(value: str | None) -> bytes | None:
    if value is None:
        return None
    return hashlib.sha256(f"{_DIGEST_SALT}\0{value}".encode()).digest()


def _patient(collection: str, dataset: Any) -> bytes | None:
    """A digest of the patient, by the ID and its issuer within the
    collection, since an ID names a patient only for the authority that
    assigned it (PS3.3 Table 10-18), and two collections' IDs are not known
    to name the same patients; None where the file gives no ID."""
    patient = _text(dataset, "PatientID")
    if patient is None:
        return None
    issuer = _text(dataset, "IssuerOfPatientID") or ""
    return _digest("\0".join(("patient", collection, patient, issuer)))


ABSENT, MALFORMED, OTHER = "absent", "malformed", "other"


def _state(dataset: pydicom.Dataset, keyword: str) -> str:
    """``absent`` for an attribute not there or empty, else ``malformed``:
    what a value that cannot be read is counted as."""
    try:
        element = dataset.get(keyword)
        empty = (
            element is None
            or element == ""
            or (
                isinstance(element, (list, tuple, pydicom.multival.MultiValue))
                and not len(element)
            )
        )
    except Exception:  # pylint: disable = broad-exception-caught
        return MALFORMED
    return ABSENT if empty else MALFORMED


def _term(dataset: pydicom.Dataset, keyword: str, terms: frozenset[str]) -> str:
    """A code string attribute's value where it is one of ``terms``."""
    value = _text(dataset, keyword)
    if value is None:
        return _state(dataset, keyword)
    return value if value in terms else OTHER


def _yes_no(dataset: pydicom.Dataset, keyword: str) -> str:
    return _term(dataset, keyword, frozenset({"YES", "NO"}))


def _vendor(dataset: pydicom.Dataset) -> str:
    value = _text(dataset, "Manufacturer")
    if value is None:
        return _state(dataset, "Manufacturer")
    for name, patterns in _VENDOR_PATTERNS:
        if any(pattern.search(value) for pattern in patterns):
            return name
    return OTHER


def _image_types(dataset: pydicom.Dataset) -> list[str]:
    try:
        value = dataset.get("ImageType")
        if value in (None, ""):
            return [ABSENT]
        many = isinstance(value, (list, tuple, pydicom.multival.MultiValue))
        values = [str(each).strip() for each in (value if many else [value])]
    except Exception:  # pylint: disable = broad-exception-caught
        return [MALFORMED]
    found = sorted({each for each in values if each in IMAGE_TYPES})
    if any(each not in IMAGE_TYPES for each in values if each):
        found.append(OTHER)
    return found or [ABSENT]


def _number(dataset: pydicom.Dataset, keyword: str) -> float | str:
    """A numeric attribute's first value, or the code of why there is none."""
    numbers = _numbers(dataset, keyword)
    return numbers[0] if numbers else _state(dataset, keyword)


def _bins(bins: Bins, value: float | str) -> str:
    if isinstance(value, str):
        return value
    try:
        return _label(bins, value)
    except ValueError:
        return OTHER


def _sop_class(dataset: pydicom.Dataset) -> str:
    if _text(dataset, "SOPClassUID") is None:
        return _state(dataset, "SOPClassUID")
    return _sop_class_name(dataset)


def _bits(dataset: pydicom.Dataset) -> str:
    value = _number(dataset, "BitsStored")
    if isinstance(value, str):
        return value
    return f"{int(value)}" if value == int(value) and 1 <= value <= 64 else OTHER


def _spacing_label(dataset: pydicom.Dataset) -> str:
    """The larger pixel spacing's bin; ``malformed`` where a spacing is
    given but cannot be read as two positive numbers, else ``absent``."""
    spacing = _spacing(dataset, 0)
    if spacing is not None:
        return _bins(PIXEL_SPACING, spacing)
    keywords = ("PixelSpacing", "ImagePlanePixelSpacing", "ImagerPixelSpacing")
    if any(_state(dataset, keyword) == MALFORMED for keyword in keywords):
        return MALFORMED
    return ABSENT


def _transfer_syntax(dataset: pydicom.Dataset) -> str:
    meta = getattr(dataset, "file_meta", None)
    value = None if meta is None else _text(meta, "TransferSyntaxUID")
    if value is None:
        return ABSENT if meta is None else _state(meta, "TransferSyntaxUID")
    uid = pydicom.uid.UID(value)
    if uid.is_private:
        return "private"
    name = uid.name
    return name if name and name != str(uid) else "unknown"


def _labels(dataset: pydicom.Dataset, has_pixels: bool) -> dict[str, list[str]]:
    rows = _number(dataset, "Rows")
    columns = _number(dataset, "Columns")
    sides = [each for each in (rows, columns) if not isinstance(each, str)]
    frames = _number(dataset, "NumberOfFrames")
    if frames == ABSENT and has_pixels:
        frames = 1.0
    return {
        "sop_class": [_sop_class(dataset)],
        "modality": [_term(dataset, "Modality", MODALITIES)],
        "manufacturer": [_vendor(dataset)],
        "rows": [_bins(SIDE, rows)],
        "columns": [_bins(SIDE, columns)],
        "larger_side": [
            _bins(SIDE, max(sides))
            if len(sides) == 2
            else (MALFORMED if MALFORMED in (rows, columns) else ABSENT)
        ],
        "pixel_spacing": [_spacing_label(dataset)],
        "frames": [_bins(FRAMES, frames)],
        "image_type": _image_types(dataset),
        "burned_in_annotation": [_yes_no(dataset, "BurnedInAnnotation")],
        "recognizable_visual_features": [
            _yes_no(dataset, "RecognizableVisualFeatures")
        ],
        "photometric": [_term(dataset, "PhotometricInterpretation", PHOTOMETRIC)],
        "bits_stored": [_bits(dataset)],
        "transfer_syntax": [_transfer_syntax(dataset)],
        "pixel_data": ["yes" if has_pixels else "no"],
    }


_PIXEL_KEYWORDS = ("PixelData", "FloatPixelData", "DoubleFloatPixelData")


def _read(file: InventoryFile) -> pydicom.Dataset | str:
    """The file's attributes up to its pixel data, or why not."""
    try:
        with file.open() as stream:
            return pydicom.dcmread(stream, stop_before_pixels=True)
    except (OSError, KeyError, zipfile.BadZipFile):
        return "not-opened"
    except pydicom.errors.InvalidDicomError:
        return "not-dicom"


def _has_pixels(file: InventoryFile) -> bool:
    """Whether the file holds top-level pixel data, read past it no further."""
    found = []

    def stop(tag, _vr, _length) -> bool:
        if tag in (0x7FE00010, 0x7FE00008, 0x7FE00009):
            found.append(tag)
            return True
        return False

    with file.open() as stream:
        pydicom.filereader.read_partial(stream, stop_when=stop)
    return bool(found)


def inventory(
    files: Iterable[InventoryFile],
    *,
    crosses: Sequence[tuple[str, ...]] = CROSSES,
) -> dict[str, Any]:
    """Count the files, as the module describes, for JSON.

    Raises
    ------
    InventoryRefused
        For a cross of an unknown dimension.
    """
    if not all(cross and set(cross) <= set(DIMENSIONS) for cross in crosses):
        raise InventoryRefused("A cross must be of known dimensions.")
    by_collection: dict[str, _Counts] = {}
    overall = _Counts()
    for file in files:
        counts = by_collection.setdefault(file.collection, _Counts())
        for each in (counts, overall):
            each.files += 1
        try:
            dataset = _read(file)
            if isinstance(dataset, str):
                for each in (counts, overall):
                    each.skipped[dataset] = each.skipped.get(dataset, 0) + 1
                continue
            has_pixels = _has_pixels(file)
            labels = _labels(dataset, has_pixels)
            frames = _numbers(dataset, "NumberOfFrames")
            frame_count = (
                int(frames[0])
                if frames and frames[0] >= 1 and has_pixels
                else int(has_pixels)
            )
            identifiers = (
                _patient(file.collection, dataset),
                _digest(_text(dataset, "StudyInstanceUID")),
                _digest(_text(dataset, "SeriesInstanceUID")),
            )
        # A file whose reading raises is counted by where, never by its
        # message, which could quote a value.
        except Exception as error:  # pylint: disable = broad-exception-caught
            site = crash_site(error)
            for each in (counts, overall):
                each.crashed[site] = each.crashed.get(site, 0) + 1
            continue
        for each in (counts, overall):
            each.add(labels, crosses)
            sop_class = labels["sop_class"][0]
            each.frames_by_sop_class[sop_class] = (
                each.frames_by_sop_class.get(sop_class, 0) + frame_count
            )
            for found, kept in zip(
                identifiers, (each.patients, each.studies, each.series)
            ):
                if found is not None:
                    kept.add(found)
    return {
        "format": INVENTORY_FORMAT,
        "software": _software(),
        "dimensions": list(DIMENSIONS),
        "vendors": [name for name, _ in VENDORS],
        "collections": {
            name: _entry(counts) for name, counts in sorted(by_collection.items())
        },
        "overall": _entry(overall),
    }


def _entry(counts: _Counts) -> dict[str, Any]:
    return {
        "files": counts.files,
        "read": counts.read,
        "skipped": dict(sorted(counts.skipped.items())),
        "crashed": dict(sorted(counts.crashed.items())),
        "patients": len(counts.patients),
        "studies": len(counts.studies),
        "series": len(counts.series),
        "frames_by_sop_class": dict(sorted(counts.frames_by_sop_class.items())),
        "by": {
            dimension: dict(sorted(counts.by.get(dimension, {}).items()))
            for dimension in DIMENSIONS
        },
        "crosses": {
            name: [
                {"value": list(combination), "files": count}
                for combination, count in sorted(found.items())
            ]
            for name, found in counts.crosses.items()
        },
    }


def _software() -> dict[str, str]:
    found = {}
    for name in ("pymedphys", "pydicom"):
        try:
            found[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            found[name] = "unknown"
    return found


def inventory_markdown(summary: Mapping[str, Any]) -> str:
    """Render an inventory as CommonMark: each collection's totals, then
    its counts by each dimension."""
    lines = [
        "# DICOM inventory",
        "",
        "Counts of each collection's files by fixed labels and bins; no "
        "value, identifier, or path of any file.",
        "",
        f"Format: `{summary['format']}`.",
        "",
        "| Collection | Files | Read | Patients | Studies | Series | Not read | Crashed |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    entries: list[tuple[str, Mapping[str, Any]]] = [
        *summary["collections"].items(),
        ("All", summary["overall"]),
    ]
    for name, entry in entries:
        lines.append(
            f"| {_cell(name)} | {entry['files']} | {entry['read']} "
            f"| {entry['patients']} | {entry['studies']} | {entry['series']} "
            f"| {sum(entry['skipped'].values())} | {sum(entry['crashed'].values())} |"
        )
    lines.append("")
    for name, entry in entries:
        lines += [f"## {_cell(name)}", ""]
        lines += _table("Frames by SOP Class", entry["frames_by_sop_class"], "Frames")
        lines += _table("Not read", entry["skipped"], "Files")
        lines += _table("Crashed", entry["crashed"], "Files")
        for dimension in summary["dimensions"]:
            lines += _table(
                dimension.replace("_", " ").capitalize(),
                entry["by"][dimension],
                "Files",
            )
        for cross, rows in entry["crosses"].items():
            names = cross.split("+")
            lines += [
                "| "
                + " | ".join(each.replace("_", " ").capitalize() for each in names)
                + " | Files |",
                "| " + " | ".join("---" for _ in names) + " | ---: |",
                *(
                    "| "
                    + " | ".join(_cell(each) for each in row["value"])
                    + f" | {row['files']} |"
                    for row in rows
                ),
                "",
            ]
    return "\n".join(lines).rstrip("\n") + "\n"


def _table(title: str, counts: Mapping[str, int], noun: str) -> list[str]:
    if not counts:
        return [f"{title}: none.", ""]
    return [
        f"| {title} | {noun} |",
        "| --- | ---: |",
        *(f"| {_cell(label)} | {count} |" for label, count in counts.items()),
        "",
    ]


def _cell(text: str) -> str:
    return str(text).replace("|", "\\|")
