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

"""Download an NCI MIDI-B test data set for the MIDI benchmark (D-018).

A development tool, run as
``python -m pymedphys._dicom.deidentify.midi_download``. It is not
registered with the ``pymedphys`` command, and stays out of the public
command line until the first supported release.

:func:`download` fetches one subset of MIDI-B
(https://doi.org/10.7937/cf2p-aw56, CC BY 4.0), as ``midi_data.toml``
pins it: TCIA's dated manifest for the subset's synthetic collection, each
series it lists from TCIA's public NBIA API, and, when one is pinned or
given, the subset's answer key. It writes, into a destination directory that
must not exist:

- ``images/``, every DICOM file of the subset, renamed
  ``<series>/<instance>.dcm`` by the series' position in the manifest and
  the file's position in its series' archive, so no path carries a value
  from the data set;
- ``answer-key.db``, the answer key, when there is one;
- ``download.json``, what was downloaded: counts, digests, whether each
  digest matched its pin, and the versions, and no value from the files.

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
import hashlib
import http.client
import json
import re
import sys
import tempfile
import time
import tomllib
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Callable, Mapping, Sequence
from importlib import resources
from pathlib import Path
from typing import BinaryIO

FORMAT = "pymedphys-deid-midi-download/1"
PINS = "midi_data.toml"
NBIA_IMAGES = "https://services.cancerimagingarchive.net/nbia-api/services/v1/getImage"
DOWNLOAD_JSON = "download.json"
ANSWER_KEY = "answer-key.db"
IMAGES = "images"
ATTEMPTS = 4
TIMEOUT_SECONDS = 600
CHUNK = 1 << 20
# A Part 10 file holds "DICM" after its 128-byte preamble.
_PREAMBLE = 128
_MAGIC = b"DICM"
_UID = re.compile(r"[0-9]+(\.[0-9]+)+")
_SHA256 = re.compile(r"[0-9a-f]{64}")

Opener = Callable[[str], BinaryIO]


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
        If an entry is incomplete, or a URL or digest is malformed.
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
        for url in (subset.manifest_url, subset.answer_key_url):
            if url and not url.startswith("https://"):
                raise DownloadError(f"a URL pinned for {key} is not HTTPS")
        for digest in (
            subset.manifest_sha256,
            subset.content_sha256,
            subset.answer_key_sha256,
        ):
            if digest and not _SHA256.fullmatch(digest):
                raise DownloadError(f"a digest pinned for {key} is malformed")
        subsets[key] = subset
    return subsets


def open_url(url: str) -> BinaryIO:
    """Open an HTTPS URL for reading."""
    if not url.startswith("https://"):
        raise DownloadError("only HTTPS URLs are fetched")
    request = urllib.request.Request(
        url, headers={"User-Agent": "pymedphys-midi-download"}
    )
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


def _fetch(
    url: str,
    destination: Path,
    opener: Opener,
    *,
    what: str,
    sleep: Callable[[float], None] | None = None,
) -> str:
    """Fetch ``url`` to ``destination``, retrying, and return its SHA-256."""
    for attempt in range(1, ATTEMPTS + 1):
        digest = hashlib.sha256()
        try:
            with opener(url) as response, destination.open("wb") as file:
                while chunk := response.read(CHUNK):
                    digest.update(chunk)
                    file.write(chunk)
            return digest.hexdigest()
        except (OSError, http.client.HTTPException) as error:
            # HTTPError, URLError, and timeouts are all OSErrors. Name the type
            # alone:
            # its message can quote the URL, which can hold a UID.
            if attempt == ATTEMPTS:
                raise DownloadError(
                    f"the {what} could not be fetched after {ATTEMPTS} "
                    f"attempts ({type(error).__name__})"
                ) from None
            (sleep or time.sleep)(2.0**attempt)
    raise AssertionError("unreachable")


def _extract(archive: Path, directory: Path, what: str) -> tuple[list[str], int, int]:
    """Write each DICOM file of ``archive`` into ``directory``, by position.

    Returns the files' SHA-256 digests, their total size, and how many
    members were skipped as not DICOM.
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
    except (zipfile.BadZipFile, zipfile.LargeZipFile) as error:
        raise DownloadError(
            f"the {what}'s archive is not a readable ZIP file ({type(error).__name__})"
        ) from None
    if not digests:
        raise DownloadError(f"the {what}'s archive holds no DICOM file")
    return digests, size, skipped


def _series(
    index: int,
    uid: str,
    images: Path,
    scratch: Path,
    opener: Opener,
    total: int,
) -> tuple[list[str], int, int]:
    what = f"series {index} of {total}"
    archive = scratch / f"{index:04d}.zip"
    url = f"{NBIA_IMAGES}?{urllib.parse.urlencode({'SeriesInstanceUID': uid})}"
    _fetch(url, archive, opener, what=what)
    try:
        return _extract(archive, images / f"{index:04d}", what)
    finally:
        archive.unlink()


def download(  # pylint: disable = too-many-locals
    subset: Subset,
    destination: str | Path,
    *,
    answer_key_url: str | None = None,
    answer_key_sha256: str | None = None,
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
    workers : int, default 8
        How many series to fetch at once.
    opener : callable, optional
        Opens a URL for reading; the tests replace it.
    progress : callable, optional
        Called with a line of progress, which quotes no value.

    Returns
    -------
    dict
        The record written to ``download.json``.

    Raises
    ------
    DownloadError
        If the destination exists or its parent does not, a fetch fails, the
        manifest or the images do not match the pinned digests or counts, or
        an answer key is given without its digest.
    """
    destination = Path(destination)
    if destination.exists() or not destination.parent.is_dir():
        raise DownloadError("the destination must not exist, and its parent must")
    if answer_key_url is None:
        key_url, key_pin = subset.answer_key_url, subset.answer_key_sha256
    elif answer_key_sha256 and _SHA256.fullmatch(answer_key_sha256):
        key_url, key_pin = answer_key_url, answer_key_sha256
    else:
        raise DownloadError("an answer key's URL needs its SHA-256")
    say = progress or (lambda line: None)
    destination.mkdir(mode=0o700)
    images = destination / IMAGES
    images.mkdir(mode=0o700)
    with tempfile.TemporaryDirectory(dir=destination) as scratch_name:
        scratch = Path(scratch_name)
        manifest_path = scratch / "manifest.tcia"
        manifest = _check(
            _fetch(subset.manifest_url, manifest_path, opener, what="manifest"),
            subset.manifest_sha256,
            "manifest",
        )
        uids = parse_manifest(manifest_path.read_text(encoding="utf-8"))
        if len(uids) != subset.series:
            raise DownloadError(
                f"the manifest lists {len(uids)} series, not the expected {subset.series}"
            )
        say(f"Fetching {len(uids)} series of {subset.collection}")
        digests: list[str] = []
        size = skipped = done = 0
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=workers)
        try:
            futures = [
                pool.submit(_series, index, uid, images, scratch, opener, len(uids))
                for index, uid in enumerate(uids, start=1)
            ]
            for future in concurrent.futures.as_completed(futures):
                series_digests, series_size, series_skipped = future.result()
                digests += series_digests
                size += series_size
                skipped += series_skipped
                done += 1
                if done % 20 == 0 or done == len(uids):
                    say(f"{done} of {len(uids)} series, {len(digests)} files")
        finally:
            # On a failure, stop at once rather than fetch the rest.
            pool.shutdown(wait=True, cancel_futures=True)
    if len(digests) != subset.instances:
        raise DownloadError(
            f"the series hold {len(digests)} DICOM files, not the expected "
            f"{subset.instances}"
        )
    content = _check(content_digest(digests), subset.content_sha256, "image set")
    answer_key: dict[str, object] | None = None
    if key_url:
        if not key_url.startswith("https://"):
            raise DownloadError("the answer key's URL is not HTTPS")
        checked = _check(
            _fetch(key_url, destination / ANSWER_KEY, opener, what="answer key"),
            key_pin,
            "answer key",
        )
        answer_key = {
            "source": "given" if answer_key_url else "pinned",
            **checked.as_dict(),
        }
    record: dict[str, object] = {
        "format": FORMAT,
        "subset": subset.key,
        "collection": subset.collection,
        "name": subset.name,
        "manifest": {"url": subset.manifest_url, **manifest.as_dict()},
        "series": len(uids),
        "files": len(digests),
        "bytes": size,
        "skipped_members_not_dicom": skipped,
        "content": content.as_dict(),
        "answer_key": answer_key,
        "python": sys.version.split()[0],
    }
    (destination / DOWNLOAD_JSON).write_text(
        json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return record


def main(
    argv: Sequence[str] | None = None, subsets: Mapping[str, Subset] | None = None
) -> int:
    """Download a MIDI-B subset and print ``download.json``.

    Raises
    ------
    SystemExit
        With a message that quotes no value, and no traceback.
    """
    try:
        subsets = load_subsets() if subsets is None else subsets
    except DownloadError as error:
        raise SystemExit(str(error)) from None
    parser = argparse.ArgumentParser(
        prog="python -m pymedphys._dicom.deidentify.midi_download",
        description=(
            "Download a MIDI-B test data set from TCIA for the MIDI benchmark "
            "(D-018). For development only."
        ),
    )
    parser.add_argument("--subset", required=True, choices=sorted(subsets))
    parser.add_argument(
        "--dest", required=True, help="A directory, which must not exist."
    )
    parser.add_argument(
        "--answer-key-url", help="An answer key to fetch in place of the pinned one."
    )
    parser.add_argument("--answer-key-sha256", help="The given answer key's SHA-256.")
    parser.add_argument("--workers", type=int, default=8)
    arguments = parser.parse_args(argv)
    try:
        record = download(
            subsets[arguments.subset],
            arguments.dest,
            answer_key_url=arguments.answer_key_url,
            answer_key_sha256=arguments.answer_key_sha256,
            workers=arguments.workers,
            progress=lambda line: print(line, file=sys.stderr, flush=True),
        )
    except DownloadError as error:
        raise SystemExit(str(error)) from None
    sys.stdout.write(json.dumps(record, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
