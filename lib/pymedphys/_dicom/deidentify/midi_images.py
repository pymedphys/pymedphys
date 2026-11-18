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

"""A MIDI-B subset's images as one ZIP file, the same bytes every time (D-018).

:func:`pack` writes the ``images`` folder that
:func:`pymedphys._dicom.deidentify.midi_download.download` writes into one
ZIP file, so that the subset can be copied somewhere other than TCIA, such
as Zenodo, and fetched from there. :func:`unpack` writes such a file's DICOM
files back into the same folders, under the same names.

The ZIP file holds, in a folder named after the collection, ``README.txt``
and then each DICOM file as ``images/<series>/<instance>.dcm``, in order of
position. Every member is stored uncompressed, with the same date and
attributes, so packing the same files gives the same bytes on any platform:
compressed bytes can differ between builds of zlib. Stored members also mean
that unpacking writes no more than the ZIP file's own size.

Neither function reads a value from the files: a file's name is its
position, and only its digest is kept. No message quotes a member's name.
"""

from __future__ import annotations

import dataclasses
import hashlib
import re
import zipfile
from collections.abc import Sequence
from pathlib import Path

README = "README.txt"
IMAGES = "images"
CHUNK = 1 << 20
# A Part 10 file holds "DICM" after its 128-byte preamble.
PREAMBLE = 128
MAGIC = b"DICM"
# The earliest date a ZIP file can record, MS-DOS's epoch.
_DATE = (1980, 1, 1, 0, 0, 0)
# Recorded as made on Unix, as a regular file that its owner may write and
# anyone may read, whatever the platform that packs it.
_UNIX = 3
_FILE_MODE = 0o100644 << 16
_ROOT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_SERIES = re.compile(r"[0-9]{4}")
_INSTANCE = re.compile(r"([0-9]{5})\.dcm")
_MEMBER = re.compile(r"images/([0-9]{4})/([0-9]{5})\.dcm")

# TCIA's data citation for MIDI-B, as its collection page gives it.
CITATION = (
    "Rutherford, M. W., Nolan, T., Pei, L., Wagner, U., Pan, Q., Farmer, P., "
    "Smith, K., Kopchick, B., Laura Opsahl-Ong, Sutton, G., Clunie, D. A., "
    "Farahani, K., & Prior, F. (2025). Data in Support of the MIDI-B "
    "Challenge (MIDI-B-Synthetic-Validation, MIDI-B-Curated-Validation, "
    "MIDI-B-Synthetic-Test, MIDI-B-Curated-Test) (Version 1) [Data set]. The "
    "Cancer Imaging Archive. https://doi.org/10.7937/cf2p-aw56"
)
POLICY = "https://www.cancerimagingarchive.net/data-usage-policies-and-restrictions/"
LICENCE = "https://creativecommons.org/licenses/by/4.0/"


class ArchiveError(Exception):
    """A folder or ZIP file is not as :func:`pack` writes it.

    The message quotes no value and no name.
    """


@dataclasses.dataclass(frozen=True)
class Files:
    """The files packed or unpacked: how many series, and each file's
    SHA-256 and the files' total size, in order of position."""

    series: int
    digests: tuple[str, ...]
    size: int


def readme(
    *, collection: str, series: int, files: int, manifest: str, content_sha256: str
) -> bytes:
    """The ``README.txt`` that :func:`pack` writes first into the ZIP file.

    It attributes the data as TCIA asks, names the licence, links TCIA's
    Data Usage Policy, and says how this copy differs from TCIA's.
    """
    paragraphs = [
        f"{collection}: an unofficial copy of TCIA's DICOM files",
        f"This ZIP file holds the {files:,} DICOM files of the {series:,} "
        f"series that TCIA's manifest {manifest} lists, each exactly as "
        "TCIA's NBIA API served it. They are part of MIDI-B, which The "
        "Cancer Imaging Archive (TCIA) publishes under the Creative Commons "
        f"Attribution 4.0 International licence (CC BY 4.0, {LICENCE}).",
        "TCIA requires anyone who uses the data to follow its Data Usage "
        "Policy, which includes not using the data to identify or contact "
        f"participants ({POLICY}), and to cite the data as follows, with its "
        "DOI:",
        CITATION,
        "How this copy differs from TCIA's: NBIA serves each series as a ZIP "
        "file of its own, which also holds a LICENSE file with TCIA's Data "
        "Usage Policy. Here the DICOM files of every series are gathered "
        "into this one ZIP file, stored uncompressed, and named "
        "images/<series>/<file>.dcm, numbered by the series' position in "
        "the manifest and the file's position in NBIA's ZIP file for the "
        "series, so no name carries a value from the data set. The LICENSE "
        "files are left out in favour of the link above, and this README is "
        "added. The DICOM files themselves are unchanged.",
        "This ZIP file was made with the MIDI-B downloader of PyMedPhys "
        "(https://github.com/pymedphys/pymedphys), which benchmarks its DICOM "
        "de-identification against MIDI-B. It is not published or endorsed "
        "by the MIDI-B authors or TCIA, and TCIA's copy remains the "
        "canonical source.",
        "To check the files: the SHA-256 of their SHA-256 digests, written "
        "in lower-case hexadecimal, sorted, and joined by newlines, is "
        f"{content_sha256}. PyMedPhys pins this value as content_sha256 in "
        "lib/pymedphys/_dicom/deidentify/midi_data.toml, and its downloader "
        "checks a copy against it.",
    ]
    return ("\n\n".join(_wrap(paragraph) for paragraph in paragraphs) + "\n").encode(
        "ascii"
    )


def _wrap(paragraph: str, width: int = 76) -> str:
    """Wrap ``paragraph`` at spaces, leaving a longer word, such as a URL, whole.

    >>> _wrap("one two three", width=7)
    'one two\\nthree'
    """
    lines: list[str] = []
    line = ""
    for word in paragraph.split(" "):
        if line and len(line) + 1 + len(word) > width:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}" if line else word
    lines.append(line)
    return "\n".join(lines)


def layout(images: Path) -> list[list[Path]]:
    """The files of an ``images`` folder as a download writes it, by series.

    The folder must hold only the folders ``0001``, ``0002``, and so on,
    each holding only the files ``00001.dcm``, ``00002.dcm``, and so on,
    numbered without a gap.

    Raises
    ------
    ArchiveError
        If ``images`` is not such a folder.
    """
    if images.is_symlink() or not images.is_dir():
        raise ArchiveError("there is no images folder to pack")
    folders = sorted(images.iterdir())
    if (
        not folders
        or not _numbered(folders, _SERIES, 4)
        or any(folder.is_symlink() or not folder.is_dir() for folder in folders)
    ):
        raise ArchiveError(
            "the images folder must hold only the series folders that a "
            "download writes, numbered from 0001 without a gap"
        )
    series = []
    for position, folder in enumerate(folders, start=1):
        files = sorted(folder.iterdir())
        if (
            not files
            or not _numbered(files, _INSTANCE, 5)
            or any(path.is_symlink() or not path.is_file() for path in files)
        ):
            raise ArchiveError(
                f"series folder {position} must hold only the files that a "
                "download writes, numbered from 00001.dcm without a gap"
            )
        series.append(files)
    return series


def _numbered(paths: Sequence[Path], pattern: re.Pattern[str], digits: int) -> bool:
    """Whether ``paths`` are named 1, 2, 3, and so on, by ``pattern``."""
    expected = range(1, len(paths) + 1)
    names = [path.name for path in paths]
    return all(pattern.fullmatch(name) for name in names) and [
        int(name[:digits]) for name in names
    ] == list(expected)


def _member(name: str, size: int) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=_DATE)
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = _UNIX
    info.external_attr = _FILE_MODE
    info.file_size = size
    return info


def pack(
    series: Sequence[Sequence[Path]], archive: Path, *, root: str, readme_text: bytes
) -> Files:
    """Write ``readme_text`` and the files of ``series`` into ``archive``.

    ``series`` is :func:`layout`'s result. ``archive`` is written over.

    Raises
    ------
    ArchiveError
        If ``root`` is not a plain name, or a file is not a Part 10 file.
    """
    if not _ROOT.fullmatch(root):
        raise ArchiveError("the ZIP file's folder must be a plain name")
    digests: list[str] = []
    size = 0
    with zipfile.ZipFile(archive, "w", allowZip64=True) as zipped:
        zipped.writestr(_member(f"{root}/{README}", len(readme_text)), readme_text)
        for series_number, files in enumerate(series, start=1):
            for file_number, path in enumerate(files, start=1):
                name = f"{root}/{IMAGES}/{series_number:04d}/{file_number:05d}.dcm"
                digest, file_size = _pack_file(zipped, name, path)
                digests.append(digest)
                size += file_size
    return Files(len(series), tuple(digests), size)


def _pack_file(zipped: zipfile.ZipFile, name: str, path: Path) -> tuple[str, int]:
    with path.open("rb") as reader:
        head = reader.read(PREAMBLE + len(MAGIC))
        if head[PREAMBLE:] != MAGIC:
            raise ArchiveError("a file in the images folder is not a DICOM file")
        digest = hashlib.sha256(head)
        size = len(head)
        with zipped.open(_member(name, path.stat().st_size), "w") as writer:
            writer.write(head)
            while chunk := reader.read(CHUNK):
                digest.update(chunk)
                writer.write(chunk)
                size += len(chunk)
    return digest.hexdigest(), size


def unpack(archive: Path, images: Path, *, root: str) -> Files:
    """Write the DICOM files of ``archive``, as :func:`pack` wrote it, into
    the empty folder ``images``.

    Every member's name is checked before anything is written, and each file
    is written by its position, never by the member's name.

    Raises
    ------
    ArchiveError
        If the ZIP file cannot be read, holds a member that :func:`pack`
        would not write, a compressed member, or a file that is not a Part
        10 file, or numbers its series or files with a gap or twice.
    """
    try:
        with zipfile.ZipFile(archive) as zipped:
            series = _positions(zipped.infolist(), root)
            digests: list[str] = []
            size = 0
            for series_number, members in enumerate(series, start=1):
                folder = images / f"{series_number:04d}"
                folder.mkdir(mode=0o700)
                for file_number, info in enumerate(members, start=1):
                    digest, file_size = _unpack_file(
                        zipped, info, folder / f"{file_number:05d}.dcm"
                    )
                    digests.append(digest)
                    size += file_size
    except (zipfile.BadZipFile, zipfile.LargeZipFile, EOFError) as error:
        raise ArchiveError(
            f"the images' ZIP file is not readable ({type(error).__name__})"
        ) from None
    return Files(len(series), tuple(digests), size)


def _positions(
    members: Sequence[zipfile.ZipInfo], root: str
) -> list[list[zipfile.ZipInfo]]:
    """The DICOM members of a ZIP file that :func:`pack` wrote, by series."""
    prefix = f"{root}/"
    found: dict[int, dict[int, zipfile.ZipInfo]] = {}
    count = 0
    for info in members:
        if info.filename == prefix + README:
            continue
        match = (
            _MEMBER.fullmatch(info.filename[len(prefix) :])
            if info.filename.startswith(prefix)
            else None
        )
        if match is None:
            raise ArchiveError(
                "the images' ZIP file holds a member that is not "
                f"{root}/images/<series>/<file>.dcm or the README"
            )
        if info.compress_type != zipfile.ZIP_STORED:
            raise ArchiveError("the images' ZIP file holds a compressed member")
        found.setdefault(int(match[1]), {})[int(match[2])] = info
        count += 1
    numbered = sorted(found) == list(range(1, len(found) + 1)) and all(
        sorted(files) == list(range(1, len(files) + 1)) for files in found.values()
    )
    if not found or not numbered or count != sum(map(len, found.values())):
        raise ArchiveError(
            "the images' ZIP file does not number its series and files from 1 "
            "without a gap, each once"
        )
    return [
        [found[series][number] for number in sorted(found[series])]
        for series in sorted(found)
    ]


def _unpack_file(
    zipped: zipfile.ZipFile, info: zipfile.ZipInfo, path: Path
) -> tuple[str, int]:
    with zipped.open(info) as member:
        head = member.read(PREAMBLE + len(MAGIC))
        if head[PREAMBLE:] != MAGIC:
            raise ArchiveError("a file in the images' ZIP file is not a DICOM file")
        digest = hashlib.sha256(head)
        size = len(head)
        with path.open("wb") as file:
            file.write(head)
            while chunk := member.read(CHUNK):
                digest.update(chunk)
                file.write(chunk)
                size += len(chunk)
    return digest.hexdigest(), size
