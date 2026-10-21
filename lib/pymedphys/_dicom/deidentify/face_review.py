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

"""A reviewer's face verdicts, for the Clean Recognizable Visual Features Option.

A run claims the option (PS3.15 E.3.2) only for an instance that cannot
show a face, or in which a reviewer found no recognisable face, whether or
not it removes a face block from the instance
(:mod:`~pymedphys._dicom.deidentify.face_blocks`). The reviewer records a verdict for
each series of a first run's QC pack, by its first run position, in the
pack's attestation (:mod:`~pymedphys._dicom.deidentify.qc_attestation`),
and the pack records the SHA-256 of each source file of each series. A
second run of the same files under a policy that selects the option is
given that pack (:func:`read_face_review`). The pack also records the
SHA-256 of the pixel data of each file that the first run wrote
(:func:`pixel_data_sha256`), only where previews that could show a face
draw every frame of them, which for an RT Dose (:func:`is_rt_dose`) only
dose-levels previews do, and the second run holds pixel data of more frames
than they listed;
and of the contours of each RT Structure Set that it wrote
(:func:`contour_data_sha256`), only where its contour sheet shows them. An
instance that carries visual features (:func:`carries_visual_features`)
satisfies the option only where the SHA-256 of its source file is that of
an instance of a series marked absent, and the pixel data and contours that
the second run writes are those that the first run wrote of it; any other
such instance is held for review (:func:`FaceReview.hold_reason`), so it is
never released. A source file changed since the review no longer matches,
and nor does one whose pixel data or contours the second run writes
otherwise, such as a CT slice defaced since the reviewer saw it as
received, or blacked out in other regions, or a structure set cut by a face
block that the first run did not find.

The verdicts are read by digest, never by path or run position, so the
second run may discover the files in another order, or among others, which
have no verdict.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
import struct

from pymedphys._imports import pydicom

from .qc_attestation import Face, Outcome, attested_pack
from .qc_pack import (
    NO_CONTOURS_SHA256,
    NO_PIXELS_SHA256,
    NotPreviewedReason,
    PreviewKind,
    QcPackError,
    pictured_frames,
)
from .qc_surfaces import RT_DOSE_STORAGE
from .reasons import VisualFeaturesReason

# Float Pixel Data (7FE0,0008), Double Float Pixel Data (7FE0,0009), and
# Pixel Data (7FE0,0010), in the order that their digest takes them.
PIXEL_DATA_TAGS = (0x7FE00008, 0x7FE00009, 0x7FE00010)
# The IOD whose contours can trace a face, although it has no pixel data.
_RT_STRUCTURE_SET = "RT Structure Set"
_SHA256 = re.compile(r"[0-9a-f]{64}")
_NO_PIXELS = bytes.fromhex(NO_PIXELS_SHA256)


@dataclasses.dataclass(frozen=True, repr=False)
class FaceReview:
    """The source files of a reviewed QC pack's series, by the reviewer's verdict.

    Its ``repr`` shows only the pack's reference and the counts.

    Attributes
    ----------
    reference : str
        The reviewed QC pack's opaque reference, ``A-`` and 32 hex digits,
        which the release report records.
    absent : frozenset of bytes
        The SHA-256 of each source file of each series that the reviewer
        marked :attr:`~.qc_attestation.Face.ABSENT`, other than one that the
        reviewed run held beside a CT series that it defaced
        (:attr:`~.reasons.VisualFeaturesReason.UNDEFACED_IN_DEFACED_FRAME`),
        by its frame, by naming none, or by a reference to a defaced slice,
        or held as an RT Dose with too much dose in that series' block to
        set to zero (:attr:`~.reasons.VisualFeaturesReason.DOSE_IN_FACE_BLOCK`).
    present : frozenset of bytes
        Likewise, of each series marked :attr:`~.qc_attestation.Face.PRESENT`.
    absent_pixels : frozenset of (bytes, bytes)
        The SHA-256 of each source file in ``absent`` whose written file the
        pack had, with the :func:`pixel_data_sha256` of that file's pixel
        data; empty by default, so that no instance satisfies the option.
    absent_contours : frozenset of (bytes, bytes)
        Likewise, with the :func:`contour_data_sha256` of that file's
        contours.
    absent_frames : frozenset of (bytes, bytes, int), optional
        For each pair in ``absent_pixels`` other than of no pixel data, how
        many frames, from the first, the pack's previews showed of it; an
        instance with more is held. :func:`read_face_review` always gives
        it; None, the default, bounds no instance's frames.
    absent_dose_frames : frozenset of (bytes, bytes, int), optional
        Likewise, how many frames its dose-levels previews showed, which
        alone show an RT Dose as it could show a face, so bound an RT
        Dose's. :func:`read_face_review` always gives it; None, the
        default, releases no RT Dose with pixel data.
    """

    reference: str
    absent: frozenset[bytes]
    present: frozenset[bytes]
    absent_pixels: frozenset[tuple[bytes, bytes]] = frozenset()
    absent_contours: frozenset[tuple[bytes, bytes]] = frozenset()
    absent_frames: frozenset[tuple[bytes, bytes, int]] | None = None
    absent_dose_frames: frozenset[tuple[bytes, bytes, int]] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.reference, str) or not re.fullmatch(
            r"A-[0-9a-f]{32}", self.reference
        ):
            raise QcPackError("a face review needs the reviewed pack's reference")
        for digests in (self.absent, self.present):
            if not isinstance(digests, frozenset) or not all(
                isinstance(d, bytes) and len(d) == 32 for d in digests
            ):
                raise QcPackError("a face review's files are SHA-256 digests")
        for pairs in (self.absent_pixels, self.absent_contours):
            if not isinstance(pairs, frozenset) or not all(
                isinstance(pair, tuple)
                and len(pair) == 2
                and all(isinstance(d, bytes) and len(d) == 32 for d in pair)
                and pair[0] in self.absent
                for pair in pairs
            ):
                raise QcPackError(
                    "a face review's pixel data and contours are SHA-256 "
                    "digests of files marked absent"
                )
        for counts in (self.absent_frames, self.absent_dose_frames):
            if counts is not None and (
                not isinstance(counts, frozenset)
                or not all(
                    isinstance(each, tuple)
                    and len(each) == 3
                    and each[:2] in self.absent_pixels
                    and isinstance(each[2], int)
                    and not isinstance(each[2], bool)
                    and each[2] >= 1
                    for each in counts
                )
            ):
                raise QcPackError(
                    "a face review's frames shown are counts of pixel data "
                    "marked absent"
                )

    def __repr__(self) -> str:
        return (
            f"FaceReview(reference={self.reference!r}, absent={len(self.absent)}, "
            f"present={len(self.present)})"
        )

    def hold_reason(
        self,
        digest: bytes,
        pixels: bytes | None,
        contours: bytes | None,
        frames: int | None = None,
        dose: bool = False,
    ) -> VisualFeaturesReason | None:
        """Return why an instance cannot claim the option.

        Parameters
        ----------
        digest : bytes
            The SHA-256 of the instance's source file.
        pixels : bytes or None
            The :func:`pixel_data_sha256` of the pixel data that the run
            writes of it, or None where that cannot be found.
        contours : bytes or None
            The :func:`contour_data_sha256` of the contours that the run
            writes of it, or None where that cannot be found.
        frames : int, optional
            How many frames the pixel data that the run writes have, or None
            where that cannot be found. Where ``absent_frames`` is given,
            pixel data other than none are held unless the pack showed at
            least this many of their frames.
        dose : bool, optional
            Whether the instance is an RT Dose (:func:`is_rt_dose`), whose
            pixel data other than none are held unless its dose-levels
            previews showed at least ``frames`` of their frames, and so
            always where ``absent_dose_frames`` is not given.

        Returns
        -------
        VisualFeaturesReason or None
            None where the reviewer marked its series absent, and not also a
            series with the same file present, which a pack never holds, and
            the run writes the pixel data and contours that the reviewed run
            wrote of it, and the pack showed every frame of those pixel data,
            which it records only where its previews draw them all.
        """
        if digest in self.present:
            return VisualFeaturesReason.FACE_PRESENT
        if digest not in self.absent:
            return VisualFeaturesReason.NO_FACE_VERDICT
        if (digest, pixels) not in self.absent_pixels:
            return VisualFeaturesReason.OTHER_PIXEL_DATA
        # Pixel data with more frames than the pack showed were not all
        # seen, and only dose levels show an RT Dose.
        counts = self.absent_dose_frames if dose else self.absent_frames
        if (
            (dose or counts is not None)
            and pixels != _NO_PIXELS
            and not any(
                (source, written) == (digest, pixels)
                and frames is not None
                and 1 <= frames <= shown
                for source, written, shown in counts or ()
            )
        ):
            return VisualFeaturesReason.OTHER_PIXEL_DATA
        if (digest, contours) not in self.absent_contours:
            return VisualFeaturesReason.OTHER_CONTOURS
        return None


def read_face_review(pack_directory: os.PathLike | str) -> FaceReview:
    """Read the face verdicts of an attested QC pack.

    Parameters
    ----------
    pack_directory : path-like
        The directory of a first run's QC pack, which a reviewer has
        attested with face verdicts.

    Returns
    -------
    FaceReview
        Empty of files where the attestation gives no verdict. A file that
        the pack lists as held because the run defaced its frame, or as an
        RT Dose with too much dose in the face block to set to zero, is not
        taken as absent, since its verdict was on the defaced images beside
        it; nor is one whose contours the pack could not show, since its
        verdict was on none of them.

    Raises
    ------
    QcPackError
        If the directory holds no QC pack, or the pack has not been
        attested, or its attestation's outcome is rejected, whose verdicts
        release nothing; if either is not of its format, or the attestation
        is for another pack; if the pack or a preview changed after it was
        attested; or if a verdict names a series that the pack does not
        list, or an instance's contours' or pixel data's SHA-256 has no
        preview that shows them. The message names no path and no value.
    """
    attestation, data = attested_pack(pack_directory)
    if attestation.outcome is not Outcome.ATTESTED:
        raise QcPackError(
            "the QC pack's attestation rejected it, so its verdicts release nothing"
        )
    files = _series_files(data)
    by_face: dict[Face, set[_File]] = {face: set() for face in Face}
    for verdict in attestation.faces:
        if verdict.series not in files:
            raise QcPackError(
                "a face verdict names a series that the QC pack does not list"
            )
        by_face[verdict.face].update(files[verdict.series])
    # A file that the reviewed run held beside a CT series that it defaced
    # was judged beside defaced images, while its own outlines or pixel data
    # were left as they were, so a verdict of absent does not cover it,
    # whatever a later run defaces. One whose contours no contour sheet
    # showed was judged without them.
    absent = {each for each in by_face[Face.ABSENT] if not each[3]}
    return FaceReview(
        attestation.reference,
        frozenset(each[0] for each in absent),
        frozenset(each[0] for each in by_face[Face.PRESENT]),
        frozenset(
            (source, pixels) for source, pixels, *_ in absent if pixels is not None
        ),
        frozenset(
            (source, contours)
            for source, _, contours, *_ in absent
            if contours is not None
        ),
        frozenset(
            (source, pixels, shown)
            for source, pixels, _, _, shown, _ in absent
            if pixels is not None and shown is not None
        ),
        frozenset(
            (source, pixels, shown)
            for source, pixels, _, _, _, shown in absent
            if pixels is not None and shown is not None
        ),
    )


# A source file's SHA-256, those of the pixel data and the contours written
# of it, if any, whether a verdict of absent leaves it out: where the run
# held it beside a CT series that it defaced, as received, or the pack could
# not show its contours; and how many frames of pixel data other than none
# its previews showed, from the first, where it has their digest, and how
# many its dose-levels previews showed, where they show any so.
_File = tuple[bytes, bytes | None, bytes | None, bool, int | None, int | None]
# Those holds' reasons as the QC pack words them, which run_qc.reason_text
# gives.
UNDEFACED_TEXT = (
    "HeldVisualFeatures(reason="
    f"{VisualFeaturesReason.UNDEFACED_IN_DEFACED_FRAME.value})"
)
DOSE_IN_FACE_BLOCK_TEXT = (
    f"HeldVisualFeatures(reason={VisualFeaturesReason.DOSE_IN_FACE_BLOCK.value})"
)


def _series_files(data: bytes) -> dict[int, frozenset[_File]]:
    """Return each series' files, by the series' first run position."""
    malformed = QcPackError("the QC pack is not of its format")
    document = json.loads(data.decode("ascii"))  # attested_pack has parsed it
    instances = document.get("instances")
    series = document.get("series")
    if not isinstance(instances, list) or not isinstance(series, list):
        raise malformed
    shown, unshown, pictured, dosed = _previews(document)
    digests: dict[int, _File] = {}
    for instance in instances:
        if not isinstance(instance, dict):
            raise malformed
        position, digest = instance.get("position"), instance.get("source_sha256")
        pixels = instance.get("pixel_sha256")
        contours = instance.get("contour_sha256")
        reasons = instance.get("reasons")
        if isinstance(position, int) and isinstance(digest, str):
            if (
                not _SHA256.fullmatch(digest)
                or not all(
                    each is None or (isinstance(each, str) and _SHA256.fullmatch(each))
                    for each in (pixels, contours)
                )
                or not isinstance(reasons, list)
            ):
                raise malformed
            # Contours' digest binds a verdict only to contours that a
            # contour sheet showed.
            if contours not in (None, NO_CONTOURS_SHA256) and position not in shown:
                raise malformed
            # Likewise, pixel data's binds it only to the frames previewed.
            frames = dose_frames = None
            if pixels not in (None, NO_PIXELS_SHA256):
                if position not in pictured:
                    raise malformed
                frames = pictured[position]
                dose_frames = dosed.get(position)
            digests[position] = (
                bytes.fromhex(digest),
                None if pixels is None else bytes.fromhex(pixels),
                None if contours is None else bytes.fromhex(contours),
                UNDEFACED_TEXT in reasons
                or DOSE_IN_FACE_BLOCK_TEXT in reasons
                or position in unshown,
                frames,
                dose_frames,
            )
    files: dict[int, frozenset[_File]] = {}
    for entry in series:
        positions = entry.get("positions") if isinstance(entry, dict) else None
        if not isinstance(positions, list) or not positions:
            raise malformed
        if not all(isinstance(p, int) and p in digests for p in positions):
            raise malformed
        files[positions[0]] = frozenset(digests[p] for p in positions)
    return files


def _previews(
    document: dict,
) -> tuple[set[int], set[int], dict[int, int], dict[int, int]]:
    """The run positions whose contours a pack's contour sheet shows, those
    that it lists as not shown, and how many frames of each other position
    its other previews, and its dose-levels previews, show in a way that
    could show a face, as :func:`~.qc_pack.pictured_frames` counts them."""
    malformed = QcPackError("the QC pack is not of its format")
    previews, missing = document.get("previews"), document.get("not_previewed")
    if not isinstance(previews, list) or not isinstance(missing, list):
        raise malformed
    shown, unshown, framed = set(), set(), []
    for preview in previews:
        if not isinstance(preview, dict) or not isinstance(preview.get("frames"), list):
            raise malformed
        if not all(
            isinstance(frame, dict)
            and all(
                isinstance(frame.get(key), int) and not isinstance(frame[key], bool)
                for key in ("position", "frame")
            )
            for frame in preview["frames"]
        ):
            raise malformed
        if preview.get("kind") == PreviewKind.STRUCTURE_SET_CONTOURS.value:
            if not preview["frames"]:
                raise malformed
            shown.add(preview["frames"][0]["position"])
        framed.append(
            (
                preview.get("kind"),
                [(frame["position"], frame["frame"]) for frame in preview["frames"]],
            )
        )
    for entry in missing:
        if not isinstance(entry, dict):
            raise malformed
        if entry.get("reason") == NotPreviewedReason.CONTOURS_NOT_SHOWN.value:
            unshown.add(entry.get("position"))
    refused = {entry.get("position") for entry in missing}
    pictured = pictured_frames(framed, refused)
    dosed = pictured_frames(framed, refused, {PreviewKind.SERIES_DOSE_LEVELS.value})
    return shown, unshown, pictured, dosed


def pixel_data_sha256(dataset: pydicom.Dataset) -> bytes:
    """Return the SHA-256 of a data set's top-level pixel data.

    The digest is of the value field of each of Float Pixel Data
    (7FE0,0008), Double Float Pixel Data (7FE0,0009), and Pixel Data
    (7FE0,0010) that the data set holds, in that order, each after its tag
    and the value's length, so that the same bytes under another of these
    tags differ. A value of odd length is taken with the trailing null byte
    that a file writes to make it even. Encapsulated Pixel Data is taken as
    its items. A data set with none of them, such as an RT Structure Set's,
    gives the digest of no pixel data, which is the same for each.

    Raises
    ------
    ValueError
        If a value is not bytes.
    """
    digest = hashlib.sha256()
    for tag in PIXEL_DATA_TAGS:
        if tag not in dataset:
            continue
        value = dataset[tag].value
        value = b"" if value is None else value
        if not isinstance(value, bytes):
            raise ValueError("pixel data are not bytes")
        if len(value) % 2:
            value += b"\0"
        digest.update(tag.to_bytes(4, "big"))
        digest.update(len(value).to_bytes(8, "big"))
        digest.update(value)
    return digest.digest()


def contour_data_sha256(dataset: pydicom.Dataset) -> bytes:
    """Return the SHA-256 of the contours of a data set's ROI Contour
    Sequence (3006,0039).

    The digest is of each item's contours, in order: each contour's Contour
    Geometric Type, as its text, and the values of its Contour Data,
    Contour Offset Vector, and Contour Slab Thickness, as 64-bit
    floating-point numbers, each item, contour, type, and list of values
    after its count, so that the same contours under another ROI, split
    otherwise, moved, or given depth differ. A data set without a contour,
    as every one but an RT Structure Set's is, gives the digest of no
    contours, which is the same for each, however many items it has.

    Raises
    ------
    ValueError
        If a contour cannot be read, without a message that quotes it.
    """
    digest = hashlib.sha256()
    try:
        items = dataset.get("ROIContourSequence") or []
        if not any(len(item.get("ContourSequence") or []) for item in items):
            items = []
        digest.update(struct.pack(">Q", len(items)))
        for item in items:
            contours = item.get("ContourSequence") or []
            digest.update(struct.pack(">Q", len(contours)))
            for contour in contours:
                kind = str(contour.get("ContourGeometricType") or "").encode(
                    "utf-8", "surrogateescape"
                )
                data = contour.get("ContourData")
                values = (
                    []
                    if data is None
                    else [float(each) for each in data]
                    if isinstance(data, (list, tuple, pydicom.multival.MultiValue))
                    else [float(data)]
                )
                digest.update(struct.pack(">Q", len(kind)) + kind)
                digest.update(struct.pack(f">Q{len(values)}d", len(values), *values))
                # Each places or gives depth to the contour, so is part of it.
                for keyword in ("ContourOffsetVector", "ContourSlabThickness"):
                    extra = _floats(contour.get(keyword))
                    digest.update(struct.pack(f">Q{len(extra)}d", len(extra), *extra))
    # pydicom raises many types for a value it cannot read, and a message
    # can quote the value.
    except Exception:  # pylint: disable = broad-exception-caught
        raise ValueError("contours cannot be read") from None
    return digest.digest()


def _floats(value: object) -> list[float]:
    """A value's numbers, none where it is absent or empty."""
    if value is None or value == "":
        return []
    if isinstance(value, (list, tuple, pydicom.multival.MultiValue)):
        return [float(each) for each in value]
    return [float(value)]


def is_rt_dose(dataset: pydicom.Dataset) -> bool:
    """Whether an instance is an RT Dose, which only a QC pack's
    dose-levels previews show as it could show a face (D-017).

    Its SOP Class UID being RT Dose Storage, or its Modality possibly being
    RTDOSE (:func:`_dose_modality`), makes it one, so that a file of either
    alone is never counted as shown, nor released under the option. A SOP
    Class UID that cannot be read leaves the Modality to decide.
    """
    return _sop_class(dataset) == RT_DOSE_STORAGE or _dose_modality(dataset)


def _sop_class(dataset: pydicom.Dataset) -> str:
    """The SOP Class UID as stripped text, or "" where it cannot be read."""
    try:
        return str(dataset.get("SOPClassUID") or "").strip()
    # Whatever reading the value raises, it names no class.
    except Exception:  # pylint: disable = broad-exception-caught
        return ""


def _dose_modality(dataset: pydicom.Dataset) -> bool:
    """Whether the Modality may be RTDOSE.

    It may where it cannot be read, is not text, holds more than one value,
    holds a character outside printable ASCII once its padding is gone, such
    as a control character, a letter outside ASCII, or a fullwidth form, or
    is RTDOSE in any case, since text that may be RTDOSE in another spelling
    cannot rule it out, as :mod:`~pymedphys._dicom.deidentify.face_blocks`
    compares Patient IDs. A missing or empty Modality says nothing about
    dose, so it is not.
    """
    try:
        value = dataset.get("Modality")
        if value is None:
            return False
        if isinstance(value, (list, tuple, pydicom.multival.MultiValue)):
            if len(value) > 1:
                return True
            value = value[0] if value else ""
        if not isinstance(value, str):
            return True
        text = value.rstrip(" \0").lstrip(" ")
    # Whatever reading the value raises, it may be RTDOSE.
    except Exception:  # pylint: disable = broad-exception-caught
        return True
    if not (text.isascii() and text.isprintable()) or "\\" in text:
        return True
    return text.casefold() == "rtdose"


def carries_visual_features(dataset: pydicom.Dataset, iod: str) -> bool:
    """Whether an instance can show a face, so that it needs a verdict.

    An instance does where it holds Pixel Data, Float Pixel Data, or Double
    Float Pixel Data, or is an RT Structure Set, whose contours can trace
    the skin surface. Any other, such as an RT Plan or an MR Spectroscopy
    instance, has nothing that can show a face, so it satisfies the option
    without a verdict.
    """
    return iod == _RT_STRUCTURE_SET or any(tag in dataset for tag in PIXEL_DATA_TAGS)
