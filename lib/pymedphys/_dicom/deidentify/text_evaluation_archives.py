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

"""Openly licensed human DICOM in ZIP archives, on Zenodo and in the
University of Sydney's research data store, for the text detector's
evaluation (D-056): tier T3, beside the collections of NCI's Imaging Data
Commons.

These records fill what no IDC collection that D-056 takes holds: defaced
head CT angiography from four makers' scanners, real multi-frame Nuclear
Medicine from bone scintigraphy, real Enhanced MR from a 0.55 T scanner,
dental cone-beam CT with its screen captures, and real RT Images, of a
linear accelerator's kV imager and a planning system's DRRs, from a
breast radiotherapy trial. :data:`COLLECTIONS` names each, with its
licence, DOI, and what is known of its frames' text, and :data:`ARCHIVES`
pins each of its ZIP archives by size and by the SHA-256 of its central
directory, the index at the end of a ZIP that gives every member's name,
size, offset, and CRC-32.

Archives are read in place, over HTTP ranges, so that CI need not fetch a
25 GB archive to read some of its series. :func:`archive_index` reads an
archive's central directory and refuses one whose digest is not the
pinned one; every member read afterwards is then checked against the
CRC-32 that the pinned index gives it. Members are taken by their leaf
folder, which in these records holds one series, or one patient's
examination: :func:`select_folders` takes each collection's folders in an
order fixed by a salted SHA-256 of their archive and path, up to a number
and a size of each, and the collections take turns until the selection
reaches its size, as :func:`~.text_evaluation_idc.select_series` does.
:func:`fetch` writes each member of a selected folder under
``<destination>/<collection>/<folder digest>/<member digest>.dcm``, so that
no member's own name, which may hold a person's identifier, is kept. A
collection limited to some SOP Classes, as the RT Images of an archive
that also holds CT are, has only members of those classes written.

:func:`archive_cases` reads the folders written as cases of tier T3, grouped
by series, with the patient as the subject where the files name one. They
are counted only: the per-case report (:mod:`~.text_evaluation_cases`)
withholds them, as it withholds every case that IDC or the seven TCIA
collections do not name.

Nothing here runs outside CI's runners, and no member's name, path, or
value is written to the selection's counts.
"""

from __future__ import annotations

import collections
import dataclasses
import functools
import hashlib
import io
import json
import math
import pathlib
import re
import time
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Callable, Iterable, Mapping
from types import MappingProxyType
from typing import BinaryIO

from pymedphys._imports import pydicom

from .text_evaluation_converted import ConvertedCase
from .text_evaluation_frames import KNOWN_TEXT, EvaluationRefused
from .text_evaluation_sources import DicomCase, SkippedFiles, dicom_folder_cases
from .text_evaluation_archive_pins import HOSTED_PINS, PINS

TIER = "T3"
SALT = "pymedphys-text-detector-evaluation-zenodo/1"
HOSTS = ("Zenodo", "University of Sydney")
SYDNEY = "https://ses-data.library.sydney.edu.au/public/"
RT_IMAGE = "1.2.840.10008.5.1.4.1.1.481.1"
# The members read as DICOM: those named ``.dcm``, and those with no
# extension, as some exports name their files.
_DICOM_NAME = re.compile(r"(?:[^/]*\.dcm|[^/.]+)", re.IGNORECASE)
_SHA256 = re.compile(r"[0-9a-f]{64}")
_MD5 = re.compile(r"[0-9a-f]{32}")
_DOI = re.compile(r"10\.[0-9]{4,9}/\S+")
# A path of the Sydney store: a dataset's folder and an archive's name.
_SYDNEY_PATH = re.compile(r"[0-9]+_[A-Za-z0-9_]+/[A-Za-z0-9_.() -]+\.zip")


@dataclasses.dataclass(frozen=True)
class ArchiveCollection:
    """A record, or a set of them, taken as one collection.

    Attributes
    ----------
    name : str
        The collection's name in the summary.
    licence : str
        As :data:`~.text_evaluation_idc.OPEN_LICENCES` spells it.
    doi : str
    title : str
        The record's title, for its citation.
    known_text : str
        What is known of its frames' text as received, one of
        :data:`~.text_evaluation_frames.KNOWN_TEXT`.
    subjects : str
        ``"patients"`` or ``"volunteers"``.
    classic : bool
        Whether its images include classic CT, MR, or PET, which the
        converted measurement reads as Legacy Converted Enhanced.
    host : str
        Where its archives are served, one of :data:`HOSTS`.
    sop_classes : frozenset of str
        The SOP Classes of its members that are taken; empty, every class.
    per_collection : int or None
        The most folders taken from it, where not the selection's limit:
        more for one whose folders hold few files each.
    """

    name: str
    licence: str
    doi: str
    title: str
    known_text: str
    subjects: str
    classic: bool
    host: str = "Zenodo"
    sop_classes: frozenset[str] = frozenset()
    per_collection: int | None = None

    def __post_init__(self):
        prefix = {"Zenodo": "zenodo", "University of Sydney": "sydney"}.get(self.host)
        if prefix is None or not re.fullmatch(rf"{prefix}_[a-z0-9_]+", self.name):
            raise EvaluationRefused("A collection needs a plain name of its host.")
        if self.licence not in {"CC BY 4.0", "CC BY NC 4.0", "CC0 1.0"}:
            raise EvaluationRefused("A collection must be openly licensed.")
        if not _DOI.fullmatch(self.doi):
            raise EvaluationRefused("A collection needs its DOI.")
        if self.known_text not in KNOWN_TEXT or self.known_text == "annotated":
            raise EvaluationRefused("What is known of its text must be known.")
        if self.subjects not in {"patients", "volunteers"}:
            raise EvaluationRefused("Its subjects must be patients or volunteers.")
        if self.per_collection is not None and self.per_collection < 1:
            raise EvaluationRefused("A collection's limit must take something.")


COLLECTIONS: Mapping[str, ArchiveCollection] = MappingProxyType(
    {
        each.name: each
        for each in (
            ArchiveCollection(
                "zenodo_head_cta",
                "CC BY 4.0",
                "10.5281/zenodo.15697196",
                "Open dataset of annotated DICOM images of head CTA for "
                "intracranial aneurysm detection",
                known_text="none",
                subjects="patients",
                classic=True,
            ),
            ArchiveCollection(
                "zenodo_bone_scintigraphy",
                "CC BY 4.0",
                "10.5281/zenodo.15549552",
                "Psoriatic arthritis: SPECT/CT and three-phase bone "
                "scintigraphy (DICOM imagings)",
                known_text="none",
                subjects="patients",
                classic=True,
            ),
            # Its archives hold CBCT slices and screen captures, which
            # commonly carry text.
            ArchiveCollection(
                "zenodo_dental_cbct",
                "CC BY 4.0",
                "10.5281/zenodo.16738223",
                "CBCT dataset of different types of Dens Invaginatus",
                known_text="unknown",
                subjects="patients",
                classic=True,
            ),
            ArchiveCollection(
                "zenodo_cardiac_mr_0p55t",
                "CC BY 4.0",
                "10.5281/zenodo.23089164",
                "0.55T cine, T1 and T2 mapping of the heart",
                known_text="none",
                subjects="volunteers",
                classic=False,
            ),
            ArchiveCollection(
                "zenodo_knee_mr_0p55t",
                "CC BY 4.0",
                "10.5281/zenodo.23964089",
                "0.55T knee MRI",
                known_text="none",
                subjects="volunteers",
                classic=False,
            ),
            # The RT Images alone, of an On-Board Imager and of ARIA's
            # DRRs; the archives' CT is left, as IDC holds much CT. Their
            # text is unknown: they were not curated for burned-in text,
            # and some systems burn scales or labels into such images.
            ArchiveCollection(
                "sydney_braveheart_rt_image",
                "CC BY 4.0",
                "10.25910/7by0-vf89",
                "Breast Radiotherapy Audio Visual Enhancement for Sparing "
                "the Heart (BRAVEHeart) prosective",
                known_text="unknown",
                subjects="patients",
                classic=False,
                host="University of Sydney",
                sop_classes=frozenset({RT_IMAGE}),
                # Most of its folders hold one or two DRRs.
                per_collection=8,
            ),
        )
    }
)
_RECORDS = MappingProxyType(
    {
        15697196: "zenodo_head_cta",
        15549552: "zenodo_bone_scintigraphy",
        16738223: "zenodo_dental_cbct",
        23089164: "zenodo_cardiac_mr_0p55t",
        23964089: "zenodo_knee_mr_0p55t",
    }
)


@dataclasses.dataclass(frozen=True)
class ZenodoArchive:
    """One ZIP archive of a record, pinned.

    Attributes
    ----------
    record : int
    size : int
        Its length in bytes.
    md5 : str
        The MD5 that Zenodo's record gives it, by which the record's file is
        found: its name is not pinned, as some of these records name a
        patient's archive by what may be the patient's initials.
    central_directory_sha256 : str
        The SHA-256 of its bytes from its central directory to its end.
    """

    record: int
    size: int
    md5: str
    central_directory_sha256: str

    def __post_init__(self):
        if self.record not in _RECORDS:
            raise EvaluationRefused("An archive must be of a vetted record.")
        if self.size <= 0:
            raise EvaluationRefused("An archive's size must be in range.")
        if not (
            _MD5.fullmatch(self.md5)
            and _SHA256.fullmatch(self.central_directory_sha256)
        ):
            raise EvaluationRefused("An archive needs its digests.")

    @property
    def collection(self) -> ArchiveCollection:
        return COLLECTIONS[_RECORDS[self.record]]

    @property
    def key(self) -> str:
        """The archive's name, as the selection's digests take it."""
        return f"{self.record}/{self.md5}"

    def url(self) -> str:
        """Where Zenodo serves it, as its record lists it now."""
        return archive_url(self, _record_files(self.record))


@dataclasses.dataclass(frozen=True)
class HostedArchive:
    """One ZIP archive of the University of Sydney's research data store,
    pinned by its path, which names no person.

    Attributes
    ----------
    name : str
        Its collection's name.
    path : str
        Its dataset's folder and its file name, under :data:`SYDNEY`.
    size : int
    central_directory_sha256 : str
    folders : frozenset of str
        The digests of the leaf folders taken, as :class:`Folder` gives
        them: those that held members of its collection's SOP Classes when
        it was pinned, so that no other folder is fetched. Empty, every
        folder.
    """

    name: str
    path: str
    size: int
    central_directory_sha256: str
    folders: frozenset[str] = frozenset()

    def __post_init__(self):
        found = COLLECTIONS.get(self.name)
        if found is None or found.host != "University of Sydney":
            raise EvaluationRefused("An archive must be of a vetted record.")
        if not _SYDNEY_PATH.fullmatch(self.path) or ".." in self.path:
            raise EvaluationRefused("An archive needs a plain path.")
        if self.size <= 0:
            raise EvaluationRefused("An archive's size must be in range.")
        if not all(
            _SHA256.fullmatch(each)
            for each in (self.central_directory_sha256, *self.folders)
        ):
            raise EvaluationRefused("An archive needs its digests.")

    @property
    def collection(self) -> ArchiveCollection:
        return COLLECTIONS[self.name]

    @property
    def key(self) -> str:
        return self.path

    def url(self) -> str:
        return SYDNEY + urllib.parse.quote(self.path)


Archive = ZenodoArchive | HostedArchive


class RangeReader(io.RawIOBase):
    """A file served over HTTP, read by ranges in blocks of ``block`` bytes,
    the last ``blocks`` of them kept, so that a ZIP's many small reads near
    one another take one request.

    Only CI's runners use it; tests read local files instead.
    """

    def __init__(
        self,
        url: str,
        size: int,
        *,
        block: int = 8 << 20,
        blocks: int = 8,
        timeout: float = 300.0,
    ):
        super().__init__()
        self._url = url
        self._size = size
        self._position = 0
        self._block = block
        self._blocks = blocks
        self._timeout = timeout
        self._cache: collections.OrderedDict[int, bytes] = collections.OrderedDict()

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self._position

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        base = {io.SEEK_SET: 0, io.SEEK_CUR: self._position, io.SEEK_END: self._size}
        self._position = base[whence] + offset
        return self._position

    def read(self, size: int | None = -1) -> bytes:
        """Up to ``size`` bytes, or to the end: fewer only at the end, as
        zipfile expects, whatever blocks the read spans."""
        if size is None or size < 0:
            size = max(0, self._size - self._position)
        found = bytearray()
        while len(found) < size:
            chunk = bytearray(size - len(found))
            count = self.readinto(chunk)
            if not count:
                break
            found += chunk[:count]
        return bytes(found)

    def readinto(self, buffer) -> int:
        if self._position >= self._size or not len(buffer):
            return 0
        index, within = divmod(self._position, self._block)
        data = self._fetched(index)[within : within + len(buffer)]
        buffer[: len(data)] = data
        self._position += len(data)
        return len(data)

    def _fetched(self, index: int) -> bytes:
        if index in self._cache:
            self._cache.move_to_end(index)
            return self._cache[index]
        start = index * self._block
        end = min(self._size, start + self._block) - 1
        request = urllib.request.Request(
            self._url, headers={"Range": f"bytes={start}-{end}"}
        )
        status, data = self._get(request)
        if status != 206 or len(data) != end - start + 1:
            raise EvaluationRefused("An archive must be served by ranges.")
        self._cache[index] = data
        while len(self._cache) > self._blocks:
            self._cache.popitem(last=False)
        return data

    def _get(self, request: urllib.request.Request) -> tuple[int, bytes]:
        """A response's status and body, tried again after a network error."""
        for attempt in range(4):
            try:
                with urllib.request.urlopen(request, timeout=self._timeout) as response:  # nosec B310
                    return response.status, response.read()
            except OSError:
                if attempt < 3:
                    time.sleep(10 * 2**attempt)
        raise EvaluationRefused("An archive was not served.")


@functools.lru_cache(maxsize=None)
def _record_files(record: int) -> Mapping[str, tuple[str, int]]:
    """A record's files as Zenodo's API lists them: each file's name and
    size by its MD5."""
    url = f"https://zenodo.org/api/records/{record}"
    with urllib.request.urlopen(url, timeout=120) as response:  # nosec B310
        found = json.load(response)
    return MappingProxyType(
        {
            str(each["checksum"]).removeprefix("md5:"): (
                str(each["key"]),
                int(each["size"]),
            )
            for each in found["files"]
        }
    )


def archive_url(archive: ZenodoArchive, files: Mapping[str, tuple[str, int]]) -> str:
    """Where Zenodo serves an archive, found in its record's files by its
    MD5, which must name one ZIP of the pinned size."""
    if archive.md5 not in files:
        raise EvaluationRefused("A pinned archive is not in its record.")
    name, size = files[archive.md5]
    if size != archive.size or not name.lower().endswith(".zip"):
        raise EvaluationRefused("A pinned archive is not in its record.")
    quoted = urllib.parse.quote(name, safe="")
    return f"https://zenodo.org/records/{archive.record}/files/{quoted}?download=1"


def http_opener(archive: Archive, block: int = 8 << 20) -> BinaryIO:
    """An archive as its host serves it, read by ranges in blocks of
    ``block`` bytes: small to read an index, large to read members."""
    return RangeReader(archive.url(), archive.size, block=block)  # type: ignore[return-value]


@dataclasses.dataclass(frozen=True)
class Folder:
    """A leaf folder of an archive, by a digest of its path.

    Attributes
    ----------
    archive : ZenodoArchive or HostedArchive
    digest : str
        A salted SHA-256 of the archive and the folder's path; the path
        itself is not kept.
    members : tuple of zipfile.ZipInfo
        Its DICOM members, in the archive's order.
    """

    archive: Archive
    digest: str
    members: tuple[zipfile.ZipInfo, ...] = dataclasses.field(repr=False)

    @property
    def collection(self) -> str:
        return self.archive.collection.name

    @property
    def size_mb(self) -> float:
        return sum(each.compress_size for each in self.members) / 1e6


def archive_index(archive: Archive, opened: BinaryIO) -> tuple[Folder, ...]:
    """An archive's leaf folders of DICOM members, from its central
    directory, which must be the pinned one."""
    opened.seek(0, io.SEEK_END)
    if opened.tell() != archive.size:
        raise EvaluationRefused("An archive is not the pinned one.")
    try:
        with zipfile.ZipFile(opened) as found:
            # Where the central directory starts, as zipfile found it.
            start = int(getattr(found, "start_dir"))
            members = found.infolist()
    except zipfile.BadZipFile:
        raise EvaluationRefused("An archive is not the pinned one.") from None
    opened.seek(start)
    digest = hashlib.sha256(opened.read(archive.size - start)).hexdigest()
    if digest != archive.central_directory_sha256:
        raise EvaluationRefused("An archive is not the pinned one.")
    folders: dict[str, list[zipfile.ZipInfo]] = {}
    for member in members:
        if member.is_dir():
            continue
        path, _, name = member.filename.rpartition("/")
        if _DICOM_NAME.fullmatch(name):
            folders.setdefault(path, []).append(member)
    indexed = tuple(
        Folder(archive, _digest("folder", archive.key, path), tuple(found))
        for path, found in sorted(folders.items())
    )
    pinned = archive.folders if isinstance(archive, HostedArchive) else frozenset()
    if not pinned:
        return indexed
    if not pinned <= {each.digest for each in indexed}:
        raise EvaluationRefused("A pinned folder is not in its archive.")
    return tuple(each for each in indexed if each.digest in pinned)


def _digest(*parts: str) -> str:
    return hashlib.sha256("\0".join((SALT, *parts)).encode()).hexdigest()


@dataclasses.dataclass(frozen=True)
class Selection:
    """The folders selected, and those refused, by reason."""

    folders: tuple[Folder, ...]
    refused: Mapping[str, int]

    def described(self) -> dict[str, object]:
        """Counts of the selection, by collection, with no folder named."""
        found: dict[str, dict[str, object]] = {}
        for name in sorted({each.collection for each in self.folders}):
            members = [each for each in self.folders if each.collection == name]
            collection = COLLECTIONS[name]
            found[name] = {
                "folders": len(members),
                "files": sum(len(each.members) for each in members),
                "archives": len({each.archive.key for each in members}),
                "size_mb": sum(each.size_mb for each in members),
                "licence": collection.licence,
                "doi": collection.doi,
                "title": collection.title,
                "subjects": collection.subjects,
                "known_text": collection.known_text,
                "host": collection.host,
            }
        return {
            "collections": found,
            "refused": dict(sorted(self.refused.items())),
        }


def select_folders(
    folders: Iterable[Folder],
    *,
    per_collection: int = 2,
    max_mb: float = 2_000.0,
    max_folder_mb: float = 400.0,
) -> Selection:
    """Select folders, as the module describes.

    Parameters
    ----------
    folders : iterable of Folder
        Of archives whose central directories were checked.
    per_collection : int
        The most folders taken from one collection, where the collection
        gives no limit of its own.
    max_mb : float
        The most megabytes taken in all.
    max_folder_mb : float
        The most megabytes of one folder.
    """
    if per_collection < 1 or not all(
        math.isfinite(each) and each > 0 for each in (max_mb, max_folder_mb)
    ):
        raise EvaluationRefused("A selection must take something.")
    queues: dict[str, list[Folder]] = {}
    for folder in folders:
        queues.setdefault(folder.collection, []).append(folder)
    for queue in queues.values():
        queue.sort(key=lambda each: each.digest)
    refused: dict[str, int] = {}
    taken: list[Folder] = []
    total = 0.0
    longest = max((len(each) for each in queues.values()), default=0)
    for position in range(longest):
        for name in sorted(queues):
            queue = queues[name]
            if position >= len(queue):
                continue
            folder = queue[position]
            limit = COLLECTIONS[name].per_collection or per_collection
            if position >= limit:
                reason = "over-collection-limit"
            elif folder.size_mb > max_folder_mb:
                reason = "over-folder-size-limit"
            elif total + folder.size_mb > max_mb:
                reason = "over-size-limit"
            else:
                taken.append(folder)
                total += folder.size_mb
                continue
            refused[reason] = refused.get(reason, 0) + 1
    return Selection(tuple(taken), MappingProxyType(refused))


def fetch(
    selection: Selection,
    destination: pathlib.Path | str,
    opener: Callable[[Archive], BinaryIO] = http_opener,
) -> dict[str, int]:
    """Write each selected folder's members under ``destination``, as the
    module describes, each checked against its pinned CRC-32, and, in a
    collection limited to some SOP Classes, only those of them; return the
    count of files written by collection."""
    root = pathlib.Path(destination)
    written: dict[str, int] = {}
    by_archive: dict[str, list[Folder]] = {}
    for folder in selection.folders:
        by_archive.setdefault(folder.archive.key, []).append(folder)
    for folders in by_archive.values():
        archive = folders[0].archive
        with opener(archive) as opened:
            # Checked again, as the archive is opened anew.
            archive_index(archive, opened)
            with zipfile.ZipFile(opened) as found:
                for folder in folders:
                    out = root / folder.collection / folder.digest
                    out.mkdir(parents=True, exist_ok=True)
                    for member in folder.members:
                        try:
                            data = found.read(member)
                        except zipfile.BadZipFile:
                            raise EvaluationRefused(
                                "A member is not as the pinned index gives it."
                            ) from None
                        if not _taken(archive.collection, data):
                            continue
                        name = _digest("member", folder.digest, member.filename)
                        (out / f"{name}.dcm").write_bytes(data)
                        written[folder.collection] = (
                            written.get(folder.collection, 0) + 1
                        )
    return dict(sorted(written.items()))


def sop_class(data: bytes) -> str | None:
    """A DICOM file's SOP Class UID, or None if it is not one."""
    try:
        found = pydicom.dcmread(
            io.BytesIO(data), stop_before_pixels=True, specific_tags=["SOPClassUID"]
        )
    except (pydicom.errors.InvalidDicomError, EOFError, ValueError):
        return None
    value = found.get("SOPClassUID")
    return None if value is None else str(value)


def _taken(collection: ArchiveCollection, data: bytes) -> bool:
    return not collection.sop_classes or sop_class(data) in collection.sop_classes


def archive_cases(
    root: pathlib.Path | str, *, converted: bool = False
) -> list[DicomCase | ConvertedCase | SkippedFiles]:
    """The fetched folders under ``root`` as cases of tier T3, grouped by
    series; with ``converted``, the cases of collections with classic
    images alone, each read as converted."""
    cases: list[DicomCase | ConvertedCase | SkippedFiles] = []
    for name, collection in COLLECTIONS.items():
        folder = pathlib.Path(root) / name
        if not folder.is_dir() or (converted and not collection.classic):
            continue
        for case in dicom_folder_cases(
            folder,
            collection=name,
            group_by="series",
            known_text=collection.known_text,
            tier=TIER,
        ):
            if converted and isinstance(case, DicomCase):
                cases.append(ConvertedCase(case))
            else:
                cases.append(case)
    return cases


ARCHIVES: tuple[Archive, ...] = tuple(ZenodoArchive(*each) for each in PINS) + tuple(
    HostedArchive(*each) for each in HOSTED_PINS
)


def check_pins() -> None:
    """Refuse pins that name an archive twice, or leave a vetted record or
    collection without one."""
    keys = [each.key for each in ARCHIVES]
    if len(set(keys)) != len(keys):
        raise EvaluationRefused("An archive is pinned twice.")
    records = {each.record for each in ARCHIVES if isinstance(each, ZenodoArchive)}
    if records != set(_RECORDS):
        raise EvaluationRefused("Every vetted record needs its archives.")
    if {each.collection.name for each in ARCHIVES} != set(COLLECTIONS):
        raise EvaluationRefused("Every vetted collection needs its archives.")


check_pins()
