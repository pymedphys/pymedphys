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
(:func:`pixel_data_sha256`), which its previews show. An instance that
carries visual features (:func:`carries_visual_features`) satisfies the
option only where the SHA-256 of its source file is that of an instance of
a series marked absent, and the pixel data that the second run writes are
those that the first run wrote of it; any other such instance is held for
review (:func:`FaceReview.hold_reason`), so it is never released. A source
file changed since the review no longer matches, and nor does one whose
pixel data the second run writes otherwise, such as a CT slice defaced
since the reviewer saw it as received, or blacked out in other regions.

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

from pymedphys._imports import pydicom

from .qc_attestation import Face, attested_pack
from .qc_pack import QcPackError
from .reasons import VisualFeaturesReason

# Float Pixel Data (7FE0,0008), Double Float Pixel Data (7FE0,0009), and
# Pixel Data (7FE0,0010), in the order that their digest takes them.
PIXEL_DATA_TAGS = (0x7FE00008, 0x7FE00009, 0x7FE00010)
# The IOD whose contours can trace a face, although it has no pixel data.
_RT_STRUCTURE_SET = "RT Structure Set"
_SHA256 = re.compile(r"[0-9a-f]{64}")


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
        marked :attr:`~.qc_attestation.Face.ABSENT`.
    present : frozenset of bytes
        Likewise, of each series marked :attr:`~.qc_attestation.Face.PRESENT`.
    absent_pixels : frozenset of (bytes, bytes)
        The SHA-256 of each source file in ``absent`` whose written file the
        pack had, with the :func:`pixel_data_sha256` of that file's pixel
        data; empty by default, so that no instance satisfies the option.
    """

    reference: str
    absent: frozenset[bytes]
    present: frozenset[bytes]
    absent_pixels: frozenset[tuple[bytes, bytes]] = frozenset()

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
        if not isinstance(self.absent_pixels, frozenset) or not all(
            isinstance(pair, tuple)
            and len(pair) == 2
            and all(isinstance(d, bytes) and len(d) == 32 for d in pair)
            and pair[0] in self.absent
            for pair in self.absent_pixels
        ):
            raise QcPackError(
                "a face review's pixel data are SHA-256 digests of files marked absent"
            )

    def __repr__(self) -> str:
        return (
            f"FaceReview(reference={self.reference!r}, absent={len(self.absent)}, "
            f"present={len(self.present)})"
        )

    def hold_reason(
        self, digest: bytes, pixels: bytes | None
    ) -> VisualFeaturesReason | None:
        """Return why an instance cannot claim the option.

        Parameters
        ----------
        digest : bytes
            The SHA-256 of the instance's source file.
        pixels : bytes or None
            The :func:`pixel_data_sha256` of the pixel data that the run
            writes of it, or None where that cannot be found.

        Returns
        -------
        VisualFeaturesReason or None
            None where the reviewer marked its series absent, and not also a
            series with the same file present, which a pack never holds, and
            the run writes the pixel data that the reviewed run wrote of it.
        """
        if digest in self.present:
            return VisualFeaturesReason.FACE_PRESENT
        if (digest, pixels) in self.absent_pixels:
            return None
        if digest in self.absent:
            return VisualFeaturesReason.OTHER_PIXEL_DATA
        return VisualFeaturesReason.NO_FACE_VERDICT


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
        Empty of files where the attestation gives no verdict.

    Raises
    ------
    QcPackError
        If the directory holds no QC pack, or the pack has not been
        attested; if either is not of its format, or the attestation is for
        another pack; if the pack or a preview changed after it was attested;
        or if a verdict names a series that the pack does not list. The
        message names no path and no value.
    """
    attestation, data = attested_pack(pack_directory)
    files = _series_files(data)
    by_face: dict[Face, set[_File]] = {face: set() for face in Face}
    for verdict in attestation.faces:
        if verdict.series not in files:
            raise QcPackError(
                "a face verdict names a series that the QC pack does not list"
            )
        by_face[verdict.face].update(files[verdict.series])
    return FaceReview(
        attestation.reference,
        frozenset(source for source, _ in by_face[Face.ABSENT]),
        frozenset(source for source, _ in by_face[Face.PRESENT]),
        frozenset(
            (source, pixels)
            for source, pixels in by_face[Face.ABSENT]
            if pixels is not None
        ),
    )


# A source file's SHA-256, and that of the pixel data written of it, if any.
_File = tuple[bytes, bytes | None]


def _series_files(data: bytes) -> dict[int, frozenset[_File]]:
    """Return each series' files, by the series' first run position."""
    malformed = QcPackError("the QC pack is not of its format")
    document = json.loads(data.decode("ascii"))  # attested_pack has parsed it
    instances = document.get("instances")
    series = document.get("series")
    if not isinstance(instances, list) or not isinstance(series, list):
        raise malformed
    digests: dict[int, _File] = {}
    for instance in instances:
        if not isinstance(instance, dict):
            raise malformed
        position, digest = instance.get("position"), instance.get("source_sha256")
        pixels = instance.get("pixel_sha256")
        if isinstance(position, int) and isinstance(digest, str):
            if not _SHA256.fullmatch(digest) or not (
                pixels is None
                or (isinstance(pixels, str) and _SHA256.fullmatch(pixels))
            ):
                raise malformed
            digests[position] = (
                bytes.fromhex(digest),
                None if pixels is None else bytes.fromhex(pixels),
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


def carries_visual_features(dataset: pydicom.Dataset, iod: str) -> bool:
    """Whether an instance can show a face, so that it needs a verdict.

    An instance does where it holds Pixel Data, Float Pixel Data, or Double
    Float Pixel Data, or is an RT Structure Set, whose contours can trace
    the skin surface. Any other, such as an RT Plan or an MR Spectroscopy
    instance, has nothing that can show a face, so it satisfies the option
    without a verdict.
    """
    return iod == _RT_STRUCTURE_SET or any(tag in dataset for tag in PIXEL_DATA_TAGS)
