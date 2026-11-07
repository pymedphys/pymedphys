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
# One module for the downloader's pins, its sources, and its command line.

"""Download an NCI MIDI-B test data set for the MIDI benchmark (D-018).

A development tool, run as
``python -m pymedphys._dicom.deidentify.midi_download``. It is not
registered with the ``pymedphys`` command, and stays out of the public
command line until the first supported release.

:func:`download` fetches one subset of MIDI-B
(https://doi.org/10.7937/cf2p-aw56, CC BY 4.0), as ``midi_data.toml``
pins it, and, when one is pinned or given, the subset's answer key. It
takes the images from TCIA itself, as TCIA's dated manifest for the
subset's synthetic collection and each series it lists from TCIA's public
NBIA API, or from a copy of them pinned as one ZIP file that :func:`pack`
wrote, such as on Zenodo, falling back to TCIA when that copy cannot be
fetched. It writes, into a destination directory that must not exist:

- ``images/``, every DICOM file of the subset, renamed
  ``<series>/<instance>.dcm`` by the series' position in the manifest and
  the file's position in its series' archive, so no path carries a value
  from the data set. The pinned copy holds the same files under the same
  names;
- ``answer-key.db``, the answer key, when there is one. TCIA publishes
  each subset's key as a ZIP file holding one SQLite database; the digest
  pinned for it is the ZIP file's, so a copy elsewhere, such as on Zenodo,
  is checked as byte for byte TCIA's file, and the database is extracted
  from it;
- ``download.json``, what was downloaded and from where: counts, digests,
  whether each digest matched its pin, and the versions, and no value from
  the files.

:func:`pack` writes a download's images into one ZIP file, the same bytes
each time, for such a copy, and :func:`verify` checks a copy of the images,
however it was downloaded.

The manifest and the series archives list the data set's UIDs, and its
files carry synthetic identifiers, which the project treats as it would
real ones: the destination is made for its owner alone where the platform
allows, and no message here quotes a UID, a file name inside an archive, or
an attribute value.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import dataclasses
import functools
import hashlib
import http.client
import json
import re
import shutil
import sys
import tempfile
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
import zipfile
import zlib
from collections.abc import Callable, Mapping, Sequence
from importlib import resources
from pathlib import Path
from typing import BinaryIO, TypeVar

from . import midi_images

FORMAT = "pymedphys-deid-midi-download/1"
PACK_FORMAT = "pymedphys-deid-midi-pack/1"
PINS = "midi_data.toml"
NBIA_IMAGES = "https://services.cancerimagingarchive.net/nbia-api/services/v1/getImage"
USER_AGENT = "pymedphys-midi-download"
DOWNLOAD_JSON = "download.json"
ANSWER_KEY = "answer-key.db"
IMAGES = midi_images.IMAGES
# Where download takes the images from: the pinned copy, when one is pinned
# and can be fetched, else TCIA; or TCIA alone.
IMAGES_FROM = ("pinned", "tcia")
ATTEMPTS = 6
# Seconds to wait before each retry: TCIA's servers can refuse or drop
# connections for minutes at a time.
WAITS = (10.0, 20.0, 40.0, 80.0, 120.0)
TIMEOUT_SECONDS = 600
CHUNK = 1 << 20
# A long fetch reports its progress after each gibibyte.
GIB = 1 << 30
_PREAMBLE = midi_images.PREAMBLE
_MAGIC = midi_images.MAGIC
_SQLITE = b"SQLite format 3\x00"
_UID = re.compile(r"[0-9]+(\.[0-9]+)+")
_SHA256 = re.compile(r"[0-9a-f]{64}")
# A collection's name also names the folder in its images' ZIP file.
_COLLECTION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
# What a note in the User-Agent header may hold: characters that an RFC 9110
# comment allows unquoted.
_AGENT_NOTE = re.compile(r"[A-Za-z0-9 .:;/_=,+-]{1,200}")

Opener = Callable[[str], BinaryIO]
_T = TypeVar("_T")


class DownloadError(Exception):
    """A download failed or did not match its pin. The message quotes no value."""


@dataclasses.dataclass(frozen=True)
class Subset:
    """One MIDI-B subset, as ``midi_data.toml`` pins it."""

    key: str
    collection: str
    name: str
    manifest_url: str
    manifest_sha256: str
    series: int
    instances: int
    content_sha256: str
    images_url: str
    images_sha256: str
    answer_key_url: str
    answer_key_sha256: str


@dataclasses.dataclass(frozen=True)
class Checked:
    """A digest, and how it compares with its pin."""

    sha256: str
    pinned: str

    @property
    def status(self) -> str:
        """``matched``, or ``not pinned``; a mismatch is refused, not recorded."""
        return "matched" if self.pinned else "not pinned"

    def as_dict(self) -> dict[str, str]:
        return {"sha256": self.sha256, "pin": self.status}


def load_subsets(text: str | None = None) -> dict[str, Subset]:
    """Read the pinned subsets from ``midi_data.toml``, or from ``text``.

    Raises
    ------
    DownloadError
        If an entry is incomplete, a URL or digest is malformed, a copy's
        URL is pinned without its digest, or the collection is not a plain
        name.
    """
    if text is None:
        text = (
            resources.files("pymedphys._dicom.deidentify")
            .joinpath(PINS)
            .read_text(encoding="utf-8")
        )
    subsets = {}
    for key, entry in tomllib.loads(text).items():
        try:
            subset = Subset(key=key, **entry)
        except TypeError as error:
            raise DownloadError(f"the pins of {key} are incomplete") from error
        for url in (subset.manifest_url, subset.images_url, subset.answer_key_url):
            if url and not url.startswith("https://"):
                raise DownloadError(f"a URL pinned for {key} is not HTTPS")
        for digest in (
            subset.manifest_sha256,
            subset.content_sha256,
            subset.images_sha256,
            subset.answer_key_sha256,
        ):
            if digest and not _SHA256.fullmatch(digest):
                raise DownloadError(f"a digest pinned for {key} is malformed")
        # A copy is trusted only as byte for byte the file its digest pins.
        for url, digest in (
            (subset.images_url, subset.images_sha256),
            (subset.answer_key_url, subset.answer_key_sha256),
        ):
            if url and not digest:
                raise DownloadError(f"a URL pinned for {key} has no SHA-256")
        if not _COLLECTION.fullmatch(subset.collection):
            raise DownloadError(f"the collection pinned for {key} is not a plain name")
        subsets[key] = subset
    return subsets


def user_agent(note: str | None = None) -> str:
    """Return the User-Agent header, with ``note`` as a comment if given.

    A note, such as the address of the machine that downloads and the run it
    belongs to, lets the server's operator find the run's requests in the
    server's logs.

    >>> user_agent("runner 192.0.2.1; run 7/1")
    'pymedphys-midi-download (runner 192.0.2.1; run 7/1)'

    Raises
    ------
    DownloadError
        If the note is empty, longer than 200 characters, or holds a
        character other than a letter, a digit, a space, or one of
        ``. : ; / _ = , + -``.
    """
    if note is None:
        return USER_AGENT
    if not _AGENT_NOTE.fullmatch(note):
        raise DownloadError(
            "a user agent note may hold only up to 200 letters, digits, "
            "spaces, and . : ; / _ = , + -"
        )
    return f"{USER_AGENT} ({note})"


def open_url(url: str, *, agent: str = USER_AGENT) -> BinaryIO:
    """Open an HTTPS URL for reading, sending ``agent`` as the User-Agent."""
    if not url.startswith("https://"):
        raise DownloadError("only HTTPS URLs are fetched")
    request = urllib.request.Request(url, headers={"User-Agent": agent})
    # The scheme is checked above: only HTTPS is opened.
    return urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS)  # nosec B310


def parse_manifest(text: str) -> tuple[str, ...]:
    """The Series Instance UIDs that a TCIA ``.tcia`` manifest lists, in order.

    The manifest is a list of ``key=value`` settings, the last of which,
    ``ListOfSeriesToDownload=``, is followed by one UID per line.

    >>> parse_manifest("manifestVersion=3.0\\nListOfSeriesToDownload=\\n1.2.3\\n1.2.4\\n")
    ('1.2.3', '1.2.4')

    Raises
    ------
    DownloadError
        If it lists no series, lists one twice, or holds a line after the
        list that is not a UID.
    """
    lines = [line.strip() for line in text.splitlines()]
    try:
        start = lines.index("ListOfSeriesToDownload=") + 1
    except ValueError as error:
        raise DownloadError("the manifest has no list of series") from error
    series = tuple(line for line in lines[start:] if line)
    if not series:
        raise DownloadError("the manifest lists no series")
    if not all(_UID.fullmatch(uid) for uid in series):
        raise DownloadError(
            "the manifest's list of series holds a line that is not a UID"
        )
    if len(set(series)) != len(series):
        raise DownloadError("the manifest lists a series twice")
    return series


def content_digest(file_digests: Sequence[str]) -> str:
    """The digest of a set of files: of their sorted, newline-joined digests.

    >>> content_digest(["b" * 64, "a" * 64]) == content_digest(["a" * 64, "b" * 64])
    True
    """
    joined = "\n".join(sorted(file_digests)).encode("ascii")
    return hashlib.sha256(joined).hexdigest()


def _check(sha256: str, pinned: str, what: str) -> Checked:
    if pinned and sha256 != pinned:
        raise DownloadError(
            f"the {what}'s SHA-256 is {sha256}, not the pinned {pinned}"
        )
    return Checked(sha256, pinned)


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _failure(error: BaseException) -> str:
    """Name a failed fetch by its type, status, and cause, never its message.

    >>> _failure(urllib.error.URLError(TimeoutError("quoted")))
    'URLError: TimeoutError'
    """
    if isinstance(error, urllib.error.HTTPError):
        return f"HTTPError {error.code}"
    if isinstance(error, urllib.error.URLError) and isinstance(
        error.reason, BaseException
    ):
        return f"URLError: {type(error.reason).__name__}"
    return type(error).__name__


class _Retry(Exception):
    """A fetch that may succeed if tried again. The message quotes no value."""


def _fetch_once(
    url: str,
    destination: Path,
    opener: Opener,
    report: Callable[[int], None] | None = None,
) -> str:
    """Fetch ``url`` to ``destination`` once, and return its SHA-256.

    ``report``, if given, is called with the bytes received so far after
    each gibibyte.
    """
    digest = hashlib.sha256()
    received = 0
    try:
        with opener(url) as response, destination.open("wb") as file:
            expected = _content_length(response)
            while chunk := response.read(CHUNK):
                digest.update(chunk)
                file.write(chunk)
                before, received = received, received + len(chunk)
                if report is not None and received // GIB > before // GIB:
                    report(received)
    except (OSError, http.client.HTTPException) as error:
        # HTTPError, URLError, and timeouts are all OSErrors. Name the type
        # alone: its message can quote the URL, which can hold a UID.
        raise _Retry(_failure(error)) from None
    if expected is not None and received != expected:
        # urllib ends the data quietly when the server closes the connection
        # early, rather than raise IncompleteRead.
        raise _Retry(f"the transfer ended after {received} of {expected} bytes")
    return digest.hexdigest()


def _content_length(response: object) -> int | None:
    """The length that a response's headers declare, if they declare one.

    >>> _content_length(object()) is None
    True
    """
    headers = getattr(response, "headers", None)
    value = None if headers is None else headers.get("Content-Length")
    if value is None or not str(value).isdigit():
        return None
    return int(value)


def _retrying(
    what: str,
    attempt: Callable[[], _T],
    *,
    sleep: Callable[[float], None] | None = None,
    say: Callable[[str], None] | None = None,
) -> _T:
    """Call ``attempt`` until it succeeds, at most ``ATTEMPTS`` times.

    Each retry is reported to ``say`` with the time, in UTC, and the failure,
    so that a server's refusals can be matched with its own logs.
    """
    for number in range(1, ATTEMPTS + 1):
        try:
            return attempt()
        except _Retry as error:
            if number == ATTEMPTS:
                raise DownloadError(
                    f"the {what} could not be fetched after {ATTEMPTS} "
                    f"attempts ({error})"
                ) from None
            wait = WAITS[number - 1]
            if say is not None:
                say(
                    f"Fetching the {what}: attempt {number} of {ATTEMPTS} failed "
                    f"at {_utc_now()} ({error}); trying again in {wait:g} s"
                )
            (sleep or time.sleep)(wait)
    raise AssertionError("unreachable")


def _fetch(
    url: str,
    destination: Path,
    opener: Opener,
    *,
    what: str,
    sleep: Callable[[float], None] | None = None,
    say: Callable[[str], None] | None = None,
    report: Callable[[int], None] | None = None,
) -> str:
    """Fetch ``url`` to ``destination``, retrying, and return its SHA-256."""
    return _retrying(
        what,
        lambda: _fetch_once(url, destination, opener, report),
        sleep=sleep,
        say=say,
    )


def _extract(archive: Path, directory: Path) -> tuple[list[str], int, int]:
    """Write each DICOM file of ``archive`` into ``directory``, by position.

    Returns the files' SHA-256 digests, their total size, and how many
    members were skipped as not DICOM. An archive that cannot be read, or
    that holds no DICOM file, raises ``_Retry`` and leaves no directory
    behind, so that the series can be fetched again: NBIA has returned an
    archive with no DICOM file for a series that it returned whole in other
    runs.
    """
    directory.mkdir(mode=0o700)
    digests: list[str] = []
    size = skipped = 0
    try:
        with zipfile.ZipFile(archive) as zipped:
            members = sorted(
                (info for info in zipped.infolist() if not info.is_dir()),
                key=lambda info: info.filename,
            )
            for info in members:
                # Member names are never used as paths: no traversal, and no
                # UID in a path.
                with zipped.open(info) as member:
                    head = member.read(_PREAMBLE + len(_MAGIC))
                    if head[_PREAMBLE:] != _MAGIC:
                        skipped += 1
                        continue
                    digest = hashlib.sha256(head)
                    path = directory / f"{len(digests) + 1:05d}.dcm"
                    with path.open("wb") as file:
                        file.write(head)
                        while chunk := member.read(CHUNK):
                            digest.update(chunk)
                            file.write(chunk)
                    size += path.stat().st_size
                    digests.append(digest.hexdigest())
    except (zipfile.BadZipFile, zipfile.LargeZipFile, EOFError, zlib.error) as error:
        shutil.rmtree(directory)
        raise _Retry(
            f"its archive is not a readable ZIP file: {type(error).__name__}"
        ) from None
    if not digests:
        shutil.rmtree(directory)
        raise _Retry("its archive holds no DICOM file")
    return digests, size, skipped


def _series(
    index: int,
    uid: str,
    images: Path,
    scratch: Path,
    opener: Opener,
    total: int,
    say: Callable[[str], None],
) -> tuple[list[str], int, int]:
    archive = scratch / f"{index:04d}.zip"
    url = f"{NBIA_IMAGES}?{urllib.parse.urlencode({'SeriesInstanceUID': uid})}"

    def attempt() -> tuple[list[str], int, int]:
        try:
            _fetch_once(url, archive, opener)
            return _extract(archive, images / f"{index:04d}")
        finally:
            archive.unlink(missing_ok=True)

    return _retrying(f"series {index} of {total}", attempt, say=say)


def download(
    subset: Subset,
    destination: str | Path,
    *,
    answer_key_url: str | None = None,
    answer_key_sha256: str | None = None,
    answer_key_file: str | Path | None = None,
    images_from: str = "pinned",
    images_file: str | Path | None = None,
    tcia: bool = True,
    workers: int = 8,
    opener: Opener = open_url,
    progress: Callable[[str], None] | None = None,
) -> dict[str, object]:
    """Download ``subset`` into ``destination``, which must not exist.

    Parameters
    ----------
    subset : Subset
        The subset, from :func:`load_subsets`.
    destination : str or Path
        A directory that does not exist, whose parent does.
    answer_key_url, answer_key_sha256 : str, optional
        An answer key to fetch in place of the pinned one, and its digest.
    answer_key_file : str or Path, optional
        A local copy of the answer key, such as the ZIP file received from
        TCIA, to use in place of fetching the pinned one, checked against
        the pinned digest.
    images_from : {"pinned", "tcia"}, default "pinned"
        Where the images come from. ``"pinned"`` fetches the copy of them
        pinned as one ZIP file, when one is pinned, and takes them from TCIA
        when there is none or it cannot be fetched; ``"tcia"`` takes them
        from TCIA.
    images_file : str or Path, optional
        A local copy of the images' ZIP file, such as one downloaded from
        Zenodo, to use in place of fetching the images, checked against the
        pinned digest when one is pinned.
    tcia : bool, default True
        Whether the images may come from TCIA. ``False`` stops the download
        where they would, before anything is fetched when nothing else could
        give them, as for a runner whose TCP connect tests to TCIA's servers
        all timed out.
    workers : int, default 8
        How many series to fetch from TCIA at once.
    opener : callable, optional
        Opens a URL for reading; the tests replace it.
    progress : callable, optional
        Called with a line of progress, or with a failed fetch that will be
        tried again, which quotes no value.

    Returns
    -------
    dict
        The record written to ``download.json``.

    Raises
    ------
    DownloadError
        If the destination exists or its parent does not, a fetch fails, the
        manifest, the images, their ZIP file, or the answer key do not match
        the pinned digests or counts, the images' ZIP file is not as
        :func:`pack` writes one, an answer key is given without its digest,
        both a URL and a file are given for it, it is neither an SQLite
        database nor a ZIP file holding exactly one, or the images would come
        from TCIA when ``tcia`` is ``False``.
    """
    destination = Path(destination)
    if destination.exists() or not destination.parent.is_dir():
        raise DownloadError("the destination must not exist, and its parent must")
    if answer_key_url is not None and answer_key_file is not None:
        raise DownloadError("give an answer key's URL or its file, not both")
    if images_from not in IMAGES_FROM:
        raise DownloadError("the images come from the pinned copy or from TCIA")
    if images_file is not None:
        if images_from == "tcia":
            raise DownloadError(
                "give the images' ZIP file or take the images from TCIA, not both"
            )
        if not Path(images_file).is_file():
            raise DownloadError("the images' ZIP file is not a file")
    elif not tcia and (images_from == "tcia" or not subset.images_url):
        raise DownloadError(
            "the images would come from TCIA, which this download may not use"
        )
    if answer_key_file is not None:
        if not Path(answer_key_file).is_file():
            raise DownloadError("the answer key file is not a file")
        key_url, key_pin, key_source = "", subset.answer_key_sha256, "file"
    elif answer_key_url is None:
        key_url, key_pin = subset.answer_key_url, subset.answer_key_sha256
        key_source = "pinned"
    elif answer_key_sha256 and _SHA256.fullmatch(answer_key_sha256):
        key_url, key_pin, key_source = answer_key_url, answer_key_sha256, "given"
    else:
        raise DownloadError("an answer key's URL needs its SHA-256")
    say = progress or (lambda line: None)
    destination.mkdir(mode=0o700)
    images = destination / IMAGES
    images.mkdir(mode=0o700)
    with tempfile.TemporaryDirectory(dir=destination) as scratch_name:
        scratch = Path(scratch_name)
        # The answer key first: a wrong one fails before the images download.
        answer_key = _answer_key(
            answer_key_file, key_url, key_pin, scratch, destination, opener, say
        )
        if answer_key is not None:
            answer_key = {"source": key_source, **answer_key}
        fetched = _images(
            subset,
            images,
            scratch,
            images_from=images_from,
            images_file=None if images_file is None else Path(images_file),
            tcia=tcia,
            opener=opener,
            workers=workers,
            say=say,
        )
    if fetched.series != subset.series:
        raise DownloadError(
            f"the images hold {fetched.series} series, not the expected {subset.series}"
        )
    if len(fetched.digests) != subset.instances:
        raise DownloadError(
            f"the series hold {len(fetched.digests)} DICOM files, not the expected "
            f"{subset.instances}"
        )
    content = _check(
        content_digest(fetched.digests), subset.content_sha256, "image set"
    )
    record: dict[str, object] = {
        "format": FORMAT,
        "subset": subset.key,
        "collection": subset.collection,
        "name": subset.name,
        "images": fetched.source,
        "manifest": fetched.manifest,
        "series": fetched.series,
        "files": len(fetched.digests),
        "bytes": fetched.size,
        "skipped_members_not_dicom": fetched.skipped,
        "content": content.as_dict(),
        "answer_key": answer_key,
        "python": sys.version.split()[0],
    }
    (destination / DOWNLOAD_JSON).write_text(
        json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return record


@dataclasses.dataclass(frozen=True)
class _Images:
    """Where a download's images came from, and what they hold."""

    source: dict[str, object]
    manifest: dict[str, str] | None
    series: int
    digests: Sequence[str]
    size: int
    # Members of TCIA's series archives that were not DICOM files; None for
    # a ZIP file that pack wrote, which holds only its README besides.
    skipped: int | None


def _images(
    subset: Subset,
    images: Path,
    scratch: Path,
    *,
    images_from: str,
    images_file: Path | None,
    tcia: bool,
    opener: Opener,
    workers: int,
    say: Callable[[str], None],
) -> _Images:
    """Write the subset's images into ``images``, from where they are asked for."""
    if images_file is not None:
        checked = _check(_sha256(images_file), subset.images_sha256, "images' ZIP file")
        return _from_zip(
            images_file, {"source": "file", **checked.as_dict()}, subset, images, say
        )
    source: dict[str, object] = {"source": "tcia"}
    if images_from == "pinned" and subset.images_url:
        archive = scratch / "images.zip"
        try:
            sha256 = _fetch(
                subset.images_url,
                archive,
                opener,
                what="images' ZIP file",
                say=say,
                report=lambda received: say(
                    f"{received // GIB} GiB of the images' ZIP file received"
                ),
            )
        except DownloadError as error:
            # Only a failed fetch falls back to TCIA. A copy that does not
            # match its pin stops the download, below, to be looked into.
            archive.unlink(missing_ok=True)
            if not tcia:
                raise DownloadError(
                    f"{error}, and this download may not take the images from TCIA"
                ) from None
            say(f"Taking the images from TCIA instead: {error}")
            source["fallback"] = {"from": subset.images_url, "failure": str(error)}
        else:
            checked = _check(sha256, subset.images_sha256, "images' ZIP file")
            fetched = _from_zip(
                archive,
                {"source": "pinned", "url": subset.images_url, **checked.as_dict()},
                subset,
                images,
                say,
            )
            archive.unlink()
            return fetched
    return _from_tcia(subset, source, images, scratch, opener, workers, say)


def _from_zip(
    archive: Path,
    source: dict[str, object],
    subset: Subset,
    images: Path,
    say: Callable[[str], None],
) -> _Images:
    say(f"Unpacking the images of {subset.collection}")
    try:
        files = midi_images.unpack(archive, images, root=subset.collection)
    except midi_images.ArchiveError as error:
        raise DownloadError(str(error)) from None
    return _Images(source, None, files.series, files.digests, files.size, None)


def _from_tcia(
    subset: Subset,
    source: dict[str, object],
    images: Path,
    scratch: Path,
    opener: Opener,
    workers: int,
    say: Callable[[str], None],
) -> _Images:
    """Fetch TCIA's manifest for the subset, and each series it lists from NBIA."""
    manifest_path = scratch / "manifest.tcia"
    manifest = _check(
        _fetch(subset.manifest_url, manifest_path, opener, what="manifest", say=say),
        subset.manifest_sha256,
        "manifest",
    )
    uids = parse_manifest(manifest_path.read_text(encoding="utf-8"))
    if len(uids) != subset.series:
        raise DownloadError(
            f"the manifest lists {len(uids)} series, not the expected {subset.series}"
        )
    say(f"Fetching {len(uids)} series of {subset.collection}")
    # Each series' digests, by its position in the manifest, so that the
    # files' digests are in the same order as a copy unpacked from a ZIP.
    by_series: dict[int, list[str]] = {}
    size = skipped = 0
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=workers)
    try:
        futures = {
            pool.submit(
                _series, index, uid, images, scratch, opener, len(uids), say
            ): index
            for index, uid in enumerate(uids, start=1)
        }
        for future in concurrent.futures.as_completed(futures):
            series_digests, series_size, series_skipped = future.result()
            by_series[futures[future]] = series_digests
            size += series_size
            skipped += series_skipped
            done = len(by_series)
            if done % 20 == 0 or done == len(uids):
                files = sum(map(len, by_series.values()))
                say(f"{done} of {len(uids)} series, {files} files")
    finally:
        # On a failure, stop at once rather than fetch the rest.
        pool.shutdown(wait=True, cancel_futures=True)
    digests = [digest for index in sorted(by_series) for digest in by_series[index]]
    return _Images(
        source,
        {"url": subset.manifest_url, **manifest.as_dict()},
        len(uids),
        digests,
        size,
        skipped,
    )


def _answer_key(
    file: str | Path | None,
    url: str,
    pinned: str,
    scratch: Path,
    destination: Path,
    opener: Opener,
    say: Callable[[str], None],
) -> dict[str, object] | None:
    """Copy or fetch the answer key, check it, and unpack its database."""
    received = scratch / "answer-key"
    if file is not None:
        sha256 = _copy(Path(file), received)
    elif url:
        if not url.startswith("https://"):
            raise DownloadError("the answer key's URL is not HTTPS")
        sha256 = _fetch(url, received, opener, what="answer key", say=say)
    else:
        return None
    checked = _check(sha256, pinned, "answer key")
    database = _unpack_answer_key(received, destination / ANSWER_KEY)
    received.unlink()
    return {**checked.as_dict(), "database_sha256": database}


def _unpack_answer_key(received: Path, destination: Path) -> str:
    """Write the SQLite answer key in ``received`` to ``destination``.

    ``received`` is the database itself, or a ZIP file holding exactly one
    database, as TCIA publishes it. Returns the database's SHA-256.
    """
    with received.open("rb") as file:
        if file.read(len(_SQLITE)) == _SQLITE:
            return _copy(received, destination)
    if not zipfile.is_zipfile(received):
        raise DownloadError(
            "the answer key is neither an SQLite database nor a ZIP file holding one"
        )
    try:
        with zipfile.ZipFile(received) as zipped:
            databases = []
            for info in zipped.infolist():
                if info.is_dir():
                    continue
                with zipped.open(info) as member:
                    if member.read(len(_SQLITE)) == _SQLITE:
                        databases.append(info)
            if len(databases) != 1:
                raise DownloadError(
                    f"the answer key's ZIP file holds {len(databases)} SQLite "
                    "databases, not one"
                )
            # The member's name is never used as a path.
            digest = hashlib.sha256()
            with zipped.open(databases[0]) as member, destination.open("wb") as file:
                while chunk := member.read(CHUNK):
                    digest.update(chunk)
                    file.write(chunk)
    except (zipfile.BadZipFile, zipfile.LargeZipFile) as error:
        raise DownloadError(
            f"the answer key's ZIP file is not readable ({type(error).__name__})"
        ) from None
    return digest.hexdigest()


def _copy(source: Path, destination: Path) -> str:
    """Copy ``source`` to ``destination``, and return its SHA-256."""
    digest = hashlib.sha256()
    with source.open("rb") as reader, destination.open("wb") as writer:
        while chunk := reader.read(CHUNK):
            digest.update(chunk)
            writer.write(chunk)
    return digest.hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while chunk := file.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _file_digest(path: Path) -> str | None:
    """The SHA-256 of a Part 10 file, or None for any other file."""
    with path.open("rb") as file:
        head = file.read(_PREAMBLE + len(_MAGIC))
        if head[_PREAMBLE:] != _MAGIC:
            return None
        digest = hashlib.sha256(head)
        while chunk := file.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def verify(
    subset: Subset, directory: str | Path, answer_key: str | Path | None = None
) -> dict[str, object]:
    """Check a copy of ``subset``, however it was downloaded, against its pins.

    Every Part 10 file below ``directory`` counts, whatever its name or
    folder, so a copy fetched with NBIA Data Retriever checks as well as one
    fetched by :func:`download`. Other files are counted and skipped.

    Given ``answer_key``, a copy of the subset's answer key as TCIA
    publishes it (the ZIP file), it checks that file's digest against the
    pinned one in the same way.

    Returns
    -------
    dict
        Counts, the content digest, and ``"matched"``, ``"not pinned"``, or
        ``"differs"``, beside whether the file count matched, and the same
        for the answer key when one is given. Nothing in it names a file.

    Raises
    ------
    DownloadError
        If ``directory`` is not a directory.
    """
    directory = Path(directory)
    if not directory.is_dir():
        raise DownloadError("the folder to verify is not a directory")
    digests: list[str] = []
    size = skipped = 0
    for path in sorted(directory.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        file_digest = _file_digest(path)
        if file_digest is None:
            skipped += 1
            continue
        digests.append(file_digest)
        size += path.stat().st_size
    content = content_digest(digests)
    record: dict[str, object] = {
        "format": FORMAT,
        "subset": subset.key,
        "collection": subset.collection,
        "files": len(digests),
        "expected_files": subset.instances,
        "bytes": size,
        "skipped_files_not_dicom": skipped,
        "content": {"sha256": content, "pin": _compare(content, subset.content_sha256)},
        "answer_key": None,
    }
    if answer_key is not None:
        if not Path(answer_key).is_file():
            raise DownloadError("the answer key file is not a file")
        key_digest = _sha256(Path(answer_key))
        record["answer_key"] = {
            "sha256": key_digest,
            "pin": _compare(key_digest, subset.answer_key_sha256),
        }
    return record


def _compare(sha256: str, pinned: str) -> str:
    if not pinned:
        return "not pinned"
    return "matched" if sha256 == pinned else "differs"


def pack(
    subset: Subset, directory: str | Path, archive: str | Path
) -> dict[str, object]:
    """Pack the images of a download of ``subset`` into one ZIP file.

    ``directory`` is the destination that :func:`download` wrote, and
    ``archive`` a ZIP file that must not exist, in a folder that does. The
    ZIP file holds a README and the DICOM files of ``images/``, under the
    same names, stored uncompressed with fixed dates and attributes, so that
    packing the same files gives the same bytes: a copy of the subset that
    :func:`download` can fetch in place of TCIA's, once its URL and digest
    are pinned. The files are checked against the pinned counts and content
    digest as they are packed, and the ZIP file is kept only if they match.

    Returns
    -------
    dict
        Counts, the content digest, and the ZIP file's name, size, and
        SHA-256, with ``"matched"``, ``"not pinned"``, or ``"differs"`` for
        how it compares with the pinned ``images_sha256``. Nothing in it
        quotes a value.

    Raises
    ------
    DownloadError
        If the subset's content digest is not pinned, ``archive`` exists or
        its folder does not, ``directory`` does not hold the images folder
        that a download writes, or the files do not match the pins.
    """
    directory, archive = Path(directory), Path(archive)
    if not subset.content_sha256:
        raise DownloadError("only a subset whose content_sha256 is pinned is packed")
    if archive.exists() or not archive.parent.is_dir():
        raise DownloadError("the ZIP file must not exist, and its folder must")
    try:
        series = midi_images.layout(directory / IMAGES)
    except midi_images.ArchiveError as error:
        raise DownloadError(str(error)) from None
    files = sum(map(len, series))
    if (len(series), files) != (subset.series, subset.instances):
        raise DownloadError(
            f"the images folder holds {len(series)} series and {files} files, "
            f"not the expected {subset.series} and {subset.instances}"
        )
    text = midi_images.readme(
        collection=subset.collection,
        series=subset.series,
        files=subset.instances,
        manifest=subset.manifest_url.rsplit("/", 1)[-1],
        content_sha256=subset.content_sha256,
    )
    with tempfile.NamedTemporaryFile(
        dir=archive.parent, prefix=f".{archive.name}.", suffix=".partial", delete=False
    ) as partial_file:
        partial = Path(partial_file.name)
    try:
        packed = midi_images.pack(
            series, partial, root=subset.collection, readme_text=text
        )
        content = _check(
            content_digest(packed.digests), subset.content_sha256, "image set"
        )
        sha256 = _sha256(partial)
        partial.replace(archive)
    except midi_images.ArchiveError as error:
        partial.unlink(missing_ok=True)
        raise DownloadError(str(error)) from None
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    return {
        "format": PACK_FORMAT,
        "subset": subset.key,
        "collection": subset.collection,
        "series": packed.series,
        "files": len(packed.digests),
        "bytes": packed.size,
        "content": content.as_dict(),
        "zip": {
            "name": archive.name,
            "bytes": archive.stat().st_size,
            "sha256": sha256,
            "pin": _compare(sha256, subset.images_sha256),
        },
        "python": sys.version.split()[0],
    }


def main(
    argv: Sequence[str] | None = None, subsets: Mapping[str, Subset] | None = None
) -> int:
    """Download a MIDI-B subset and print ``download.json``, or check or
    pack a copy.

    With ``--verify``, print :func:`verify`'s record and return 1 when the
    copy's file count or content digest differs from the pins. With
    ``--pack``, print :func:`pack`'s record and return 1 when the ZIP file
    differs from the pinned one.

    Raises
    ------
    SystemExit
        With a message that quotes no value, and no traceback.
    """
    try:
        subsets = load_subsets() if subsets is None else subsets
    except DownloadError as error:
        raise SystemExit(str(error)) from None
    parser = _parser(subsets)
    arguments = parser.parse_args(argv)
    if arguments.dest is None:
        for option, value in (
            ("--images-from", arguments.images_from),
            ("--images-file", arguments.images_file),
            ("--no-tcia", arguments.no_tcia or None),
        ):
            if value is not None:
                parser.error(f"{option} goes with --dest")
    if (arguments.pack is None) != (arguments.to is None):
        parser.error("--pack and --to go together")
    subset = subsets[arguments.subset]
    if arguments.pack is not None:
        try:
            packed = pack(subset, arguments.pack, arguments.to)
        except DownloadError as error:
            raise SystemExit(str(error)) from None
        sys.stdout.write(json.dumps(packed, indent=2) + "\n")
        archive = packed["zip"]
        return 1 if isinstance(archive, dict) and archive["pin"] == "differs" else 0
    if arguments.verify is not None:
        try:
            checked = verify(subset, arguments.verify, arguments.answer_key_file)
        except DownloadError as error:
            raise SystemExit(str(error)) from None
        sys.stdout.write(json.dumps(checked, indent=2) + "\n")
        pins = [checked["content"], checked["answer_key"]]
        differs = any(isinstance(pin, dict) and pin["pin"] == "differs" for pin in pins)
        return 1 if differs or checked["files"] != checked["expected_files"] else 0
    try:
        agent = user_agent(arguments.user_agent_note)
        record = download(
            subset,
            arguments.dest,
            answer_key_url=arguments.answer_key_url,
            answer_key_sha256=arguments.answer_key_sha256,
            answer_key_file=arguments.answer_key_file,
            images_from=arguments.images_from or "pinned",
            images_file=arguments.images_file,
            tcia=not arguments.no_tcia,
            workers=arguments.workers,
            opener=functools.partial(open_url, agent=agent),
            progress=lambda line: print(line, file=sys.stderr, flush=True),
        )
    except DownloadError as error:
        raise SystemExit(str(error)) from None
    sys.stdout.write(json.dumps(record, indent=2) + "\n")
    return 0


def _parser(subsets: Mapping[str, Subset]) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m pymedphys._dicom.deidentify.midi_download",
        description=(
            "Download a MIDI-B test data set for the MIDI benchmark, from TCIA "
            "or its pinned copy, or check or pack a copy. For development only."
        ),
    )
    parser.add_argument("--subset", required=True, choices=sorted(subsets))
    where = parser.add_mutually_exclusive_group(required=True)
    where.add_argument(
        "--dest", help="Download into this directory, which must not exist."
    )
    where.add_argument(
        "--verify",
        help=(
            "Instead of downloading, check the DICOM files below this "
            "directory, however they were downloaded, against the pins."
        ),
    )
    where.add_argument(
        "--pack",
        help=(
            "Instead of downloading, pack the images of the download in this "
            "directory, which --dest wrote, into the ZIP file given with --to, "
            "the same bytes each time, checking them against the pins."
        ),
    )
    parser.add_argument("--to", help="The ZIP file that --pack writes.")
    parser.add_argument(
        "--images-from",
        choices=IMAGES_FROM,
        help=(
            "Where the images come from: their pinned copy, when one is "
            "pinned, falling back to TCIA if it cannot be fetched (the "
            "default), or TCIA."
        ),
    )
    parser.add_argument(
        "--images-file",
        help=(
            "A local copy of the images' ZIP file, such as one downloaded "
            "from Zenodo, used in place of fetching the images and checked "
            "against the pins."
        ),
    )
    parser.add_argument(
        "--no-tcia",
        action="store_true",
        help=(
            "Stop rather than take the images from TCIA, as for a machine "
            "whose TCP connect tests to TCIA's servers all timed out."
        ),
    )
    parser.add_argument(
        "--answer-key-url", help="An answer key to fetch in place of the pinned one."
    )
    parser.add_argument("--answer-key-sha256", help="The given answer key's SHA-256.")
    parser.add_argument(
        "--answer-key-file",
        help=(
            "A local copy of the answer key, such as one received from TCIA, "
            "checked against the pinned digest: used in place of the pinned "
            "copy, or, with --verify, checked alone."
        ),
    )
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument(
        "--user-agent-note",
        help=(
            "Text to add to the User-Agent header of each request, such as "
            "the address of the machine that downloads and the run it belongs "
            "to, so that TCIA can find the run's requests in its logs."
        ),
    )
    return parser


if __name__ == "__main__":
    sys.exit(main())
