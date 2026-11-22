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

"""A development check of the Clean Graphics Option on public human DICOM
that holds graphics, which writes only counts.

DRAFT: the module's description is written once its runs are settled.
"""

from __future__ import annotations

import dataclasses
import hashlib
import io
import re
import zipfile
from collections.abc import Callable, Iterable, Sequence
from typing import BinaryIO

from pymedphys._imports import pydicom

from .text_evaluation_archives import ARCHIVES, Archive, archive_index, http_opener
from .text_evaluation_frames import EvaluationRefused

FORMAT = "pymedphys-deid-clean-graphics-check/1"
GRAYSCALE_SOFTCOPY_PRESENTATION_STATE = "1.2.840.10008.5.1.4.1.1.11.1"
PSEUDO_COLOR_SOFTCOPY_PRESENTATION_STATE = "1.2.840.10008.5.1.4.1.1.11.3"
RT_IMAGE = "1.2.840.10008.5.1.4.1.1.481.1"
# The archives that the members are read from, by the keys that
# text_evaluation_archives gives them: a Zenodo record and the MD5 of its
# file, and a path of the University of Sydney's data store.
CARDIAC_MR_COLLECTION = "zenodo_cardiac_mr_0p55t"
CARDIAC_MR = "23089164/aa60c0f515584b4214849cc7fa1382f5"
BRAVEHEART_COLLECTION = "sydney_braveheart_rt_image"
BRAVEHEART = "32833_Byrne_2/P01-P05 (Anonymised).zip"
# Ranges of 1 MiB: an archive's central directory, then each member, take
# few requests and fetch little beyond them.
BLOCK = 1 << 20

_SHA256 = re.compile(r"[0-9a-f]{64}")


class CheckRefused(Exception):
    """An archive or member is not one that the check pins; the message
    quotes no value of it."""


@dataclasses.dataclass(frozen=True)
class PinnedMember:
    """One member of a pinned archive, which the check reads.

    It is named by its collection, its archive, and its place in the
    archive's central directory, never by its name in the archive, which
    may hold a person's identifier.

    Attributes
    ----------
    collection : str
        The archive's collection, as :mod:`~.text_evaluation_archives`
        names it.
    archive : str
        The archive's key, as :mod:`~.text_evaluation_archives` gives it.
    entry : int
        Its 0-based place in the archive's central directory.
    sha256 : str
        The SHA-256 of its bytes, as 64 lower-case hex digits.
    sop_class : str
        Its SOP Class UID.
    """

    collection: str
    archive: str
    entry: int
    sha256: str
    sop_class: str

    def __post_init__(self):
        if self.entry < 0:
            raise CheckRefused("A member's place must be in range.")
        if not _SHA256.fullmatch(self.sha256):
            raise CheckRefused("A member needs its digest.")

    @property
    def label(self) -> str:
        """The member's name in the summary: its collection and its place."""
        return f"{self.collection} #{self.entry}"


MEMBERS: tuple[PinnedMember, ...] = (
    PinnedMember(
        CARDIAC_MR_COLLECTION,
        CARDIAC_MR,
        382,
        "6121e7401a99d2e3237039db7655762b53434eb5c3222e5e10445286cc0ba62e",
        GRAYSCALE_SOFTCOPY_PRESENTATION_STATE,
    ),
    PinnedMember(
        CARDIAC_MR_COLLECTION,
        CARDIAC_MR,
        383,
        "75fd5e35e640b7654d1021d284ba1cdfbae8a0a602c5bf6f22dc2313544be230",
        GRAYSCALE_SOFTCOPY_PRESENTATION_STATE,
    ),
    PinnedMember(
        CARDIAC_MR_COLLECTION,
        CARDIAC_MR,
        385,
        "92885bc599b340b16a38d2f13bdeb4c66ee67115f1e5b95ba3ba9019d6159fce",
        PSEUDO_COLOR_SOFTCOPY_PRESENTATION_STATE,
    ),
    PinnedMember(
        BRAVEHEART_COLLECTION,
        BRAVEHEART,
        11388,
        "a09abcba3ceda2562355647e4e4cb9fab8c183a7f78b58557ba5a01627b515c8",
        RT_IMAGE,
    ),
    PinnedMember(
        BRAVEHEART_COLLECTION,
        BRAVEHEART,
        11389,
        "7437e86804b202fac6415a914b69ae9b25a4aba798a235e3db8ae482197e1c53",
        RT_IMAGE,
    ),
    PinnedMember(
        BRAVEHEART_COLLECTION,
        BRAVEHEART,
        11390,
        "1f69579931a6e0b3e3342c31917b53b50796a2b865b13462fa1bf9efedc3bc12",
        RT_IMAGE,
    ),
    PinnedMember(
        BRAVEHEART_COLLECTION,
        BRAVEHEART,
        11391,
        "4b4ec440c720ae33431ef53424682a34b88744cbbf97c413c3993f707b5f395b",
        RT_IMAGE,
    ),
)


def _archive(key: str, archives: Iterable[Archive] = ARCHIVES) -> Archive:
    for each in archives:
        if each.key == key:
            return each
    raise CheckRefused("A member's archive is not a pinned one.")


def read_members(
    members: Sequence[PinnedMember] = MEMBERS,
    *,
    archives: Iterable[Archive] = ARCHIVES,
    opener: Callable[[Archive, int], BinaryIO] = http_opener,
) -> tuple[tuple[PinnedMember, bytes], ...]:
    """Read each member from its archive, in order.

    Each archive must be the pinned one: of its pinned size, with the
    pinned central directory (:func:`~.text_evaluation_archives.archive_index`).
    Each member must then match the CRC-32 that the directory gives it, as
    :mod:`zipfile` checks on reading, the SHA-256 that its pin gives it,
    and its pinned SOP Class.

    Raises
    ------
    CheckRefused
        Where an archive or a member is not the pinned one.
    """
    archives = tuple(archives)
    by_archive: dict[str, list[PinnedMember]] = {}
    for member in members:
        by_archive.setdefault(member.archive, []).append(member)
    found: dict[PinnedMember, bytes] = {}
    for key, pinned in by_archive.items():
        archive = _archive(key, archives)
        if {each.collection for each in pinned} != {archive.collection.name}:
            raise CheckRefused("A member's archive is not of its collection.")
        with opener(archive, BLOCK) as opened:
            try:
                archive_index(archive, opened)
            except EvaluationRefused:
                raise CheckRefused("An archive is not the pinned one.") from None
            with zipfile.ZipFile(opened) as index:
                entries = index.infolist()
                for member in pinned:
                    found[member] = _read(index, entries, member)
    return tuple((member, found[member]) for member in members)


def _read(
    index: zipfile.ZipFile, entries: Sequence[zipfile.ZipInfo], member: PinnedMember
) -> bytes:
    if member.entry >= len(entries) or entries[member.entry].is_dir():
        raise CheckRefused("A member is not in its archive.")
    try:
        data = index.read(entries[member.entry])
    except (zipfile.BadZipFile, OSError, NotImplementedError):
        raise CheckRefused("A member is not as its archive's index gives it.") from None
    if hashlib.sha256(data).hexdigest() != member.sha256:
        raise CheckRefused("A member is not the pinned one.")
    if sop_class_of(data) != member.sop_class:
        raise CheckRefused("A member is not of its pinned SOP Class.")
    return data


def sop_class_of(data: bytes) -> str | None:
    """A Part 10 file's SOP Class UID, from its file meta information or
    its data set, or None where neither gives one."""
    try:
        dataset = pydicom.dcmread(
            io.BytesIO(data), stop_before_pixels=True, specific_tags=[0x00080016]
        )
    # pydicom raises many types for a file it cannot read, and a message can
    # quote a value.
    except Exception:  # pylint: disable = broad-exception-caught
        return None
    meta = getattr(dataset, "file_meta", None)
    found = meta.get("MediaStorageSOPClassUID") if meta is not None else None
    found = dataset.get("SOPClassUID", found)
    return None if found is None else str(found)
