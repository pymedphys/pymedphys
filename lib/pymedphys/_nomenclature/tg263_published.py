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

"""Download AAPM's published TG-263 Structure Spreadsheet, pinned by SHA-256.

PyMedPhys does not include the spreadsheet. :func:`load` downloads the edition
that :data:`PUBLISHED` pins from AAPM's Radiation Oncology Nomenclature
Resource Page, caches it in the PyMedPhys data directory, and reads it. The
file must have the pinned SHA-256, and the entries read from it the pinned
content digest, or nothing is returned; a copy that does not match is never
used. The cache is ``tg263/`` in ``~/.pymedphys/data``, or in the directory
that ``PYMEDPHYS_DATA_DIR`` names.

AAPM publishes a new edition as a new file. ``pymedphys dev tg263-check``
reports when the page links to a spreadsheet other than the pinned one, or
the pinned file changes; moving to a new edition is a change to the pin.
"""

from __future__ import annotations

import dataclasses
import hashlib
import pathlib
import posixpath
import re
import urllib.parse
from collections.abc import Callable

from pymedphys._data.download import (
    download_lock,
    download_with_progress,
    get_data_dir,
)

from . import tg263

PAGE_URL = "https://www.aapm.org/pubs/reports/RPT_263_Supplemental/"
CACHE_DIRECTORY = "tg263"

_SHA256 = re.compile(r"[0-9a-f]{64}")

Download = Callable[[str, pathlib.Path], None]


@dataclasses.dataclass(frozen=True)
class Edition:
    """One published edition of the TG-263 Structure Spreadsheet.

    Attributes
    ----------
    sheet : str
        The name of the worksheet that holds the structures, which carries
        the edition's date, such as ``"TG263 v20170815"``.
    url : str
        Where AAPM publishes the file, over HTTPS.
    sha256 : str
        The SHA-256 of the file's bytes.
    content_sha256 : str
        :func:`~pymedphys._nomenclature.tg263.content_sha256` of the entries
        read from the file.
    """

    sheet: str
    url: str
    sha256: str
    content_sha256: str

    def __post_init__(self):
        for field in ("sha256", "content_sha256"):
            if not _SHA256.fullmatch(getattr(self, field)):
                raise ValueError(f"{field} must be 64 lowercase hexadecimal digits")
        parts = urllib.parse.urlsplit(self.url)
        if parts.scheme != "https" or not posixpath.basename(parts.path):
            raise ValueError("url must be an https URL that names a file")

    @property
    def file(self) -> str:
        """The file's name, as the last part of its URL."""
        return posixpath.basename(urllib.parse.urlsplit(self.url).path)


# The edition linked from PAGE_URL, last modified on AAPM's server on
# 2 March 2018: 717 structures.
PUBLISHED = Edition(
    sheet="TG263 v20170815",
    url=PAGE_URL + "TG263_Nomenclature_Worksheet_20170815.xls",
    sha256="5ff0b9e2ebf578793f6fa8f59c2357b3feb61fdc0f87171e9103a0495d93d150",
    content_sha256="0a0eaeacf147bdf654e0090b3e12b005d76985e6adc95441d7563365ac6e7ffc",
)


def spreadsheet_path(
    edition: Edition | None = None, *, download: Download | None = None
) -> pathlib.Path:
    """Return the cached copy of an edition, downloading it if needed.

    Parameters
    ----------
    edition : Edition, optional
        Defaults to :data:`PUBLISHED`.
    download : callable, optional
        Writes the file at a URL to a path. Defaults to PyMedPhys's
        downloader, which retries transient failures and writes nothing at
        the path until the download is complete.

    Returns
    -------
    pathlib.Path
        A file with the edition's SHA-256. A cached copy without it, such as
        one cut short, is downloaded again.

    Raises
    ------
    TG263Error
        If the downloaded file does not have the edition's SHA-256. It is
        removed.
    OSError
        If the file cannot be downloaded or written.
    """
    edition = PUBLISHED if edition is None else edition
    path: pathlib.Path = get_data_dir() / CACHE_DIRECTORY / edition.file
    path.parent.mkdir(parents=True, exist_ok=True)
    with download_lock(path):
        if path.exists() and _sha256(path) == edition.sha256:
            return path
        (download_with_progress if download is None else download)(edition.url, path)
        if _sha256(path) != edition.sha256:
            path.unlink()
            raise tg263.TG263Error(
                f"the file downloaded from {edition.url} does not have the "
                f"pinned SHA-256 {edition.sha256}"
            )
    return path


def load(
    edition: Edition | None = None,
    *,
    spreadsheet: pathlib.Path | None = None,
    download: Download | None = None,
) -> tg263.Nomenclature:
    """Read a published edition, downloading it if needed.

    Parameters
    ----------
    edition : Edition, optional
        Defaults to :data:`PUBLISHED`.
    spreadsheet : pathlib.Path, optional
        A copy of the edition's file to read instead of downloading it, such
        as on a computer without internet access. It must have the edition's
        SHA-256.
    download : callable, optional
        As for :func:`spreadsheet_path`.

    Returns
    -------
    ~pymedphys._nomenclature.tg263.Nomenclature

    Raises
    ------
    TG263Error
        If the file does not have the edition's SHA-256, or what is read
        from it does not have the edition's worksheet name and entries.
    OSError
        If the file cannot be downloaded, written, or read.
    """
    edition = PUBLISHED if edition is None else edition
    if spreadsheet is None:
        spreadsheet = spreadsheet_path(edition, download=download)
    elif _sha256(spreadsheet) != edition.sha256:
        raise tg263.TG263Error(
            f"{spreadsheet.name} does not have the pinned SHA-256 {edition.sha256} "
            f"of {edition.file}"
        )
    nomenclature = tg263.read_spreadsheet(spreadsheet)
    if nomenclature.source.sheet != edition.sheet:
        raise tg263.TG263Error(
            f"{edition.file} holds the worksheet {nomenclature.source.sheet!r}, "
            f"not the pinned {edition.sheet!r}"
        )
    entries = [dataclasses.asdict(s) for s in nomenclature.structures]
    if tg263.content_sha256(entries) != edition.content_sha256:
        raise tg263.TG263Error(
            f"the entries read from {edition.file} do not have the pinned "
            f"content digest {edition.content_sha256}"
        )
    return nomenclature


def _sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
