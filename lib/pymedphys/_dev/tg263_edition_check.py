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

"""Check whether AAPM has published a TG-263 spreadsheet other than the pinned one.

``pymedphys dev tg263-check`` runs :func:`run`. It reads AAPM's Radiation
Oncology Nomenclature Resource Page and lists the spreadsheets it links to,
and downloads the pinned spreadsheet to compare its SHA-256 with the pin.
AAPM publishes a new edition as a new file, so a link to any other
spreadsheet, a page that no longer links to the pinned one, or a pinned file
whose bytes have changed is reported as a change. Its report names URLs and
digests and types of error, never the page's text.
"""

from __future__ import annotations

import contextlib
import dataclasses
import hashlib
import html.parser
import http.client
import json
import pathlib
import posixpath
import sys
import tempfile
import urllib.error
import urllib.parse
from collections.abc import Callable

from pymedphys._data.download import download_with_progress
from pymedphys._nomenclature import tg263_published

# The exit status for each result, as for pymedphys dev deid-tables
# --check-current.
EXIT_STATUS = {"unchanged": 0, "changed": 1, "failed": 3}

_SPREADSHEET_EXTENSIONS = (".xls", ".xlsx")

Fetch = Callable[[str], bytes]


@dataclasses.dataclass(frozen=True)
class EditionCheck:
    """What the resource page and the pinned spreadsheet show now.

    Attributes
    ----------
    page_url : str
        The resource page.
    pinned_sheet, pinned_url, pinned_sha256 : str
        The pinned edition's worksheet, URL, and SHA-256.
    linked : tuple of str
        The URL of each spreadsheet the page links to, sorted, each once.
    page_error : str or None
        Why the page could not be fetched, as the type of error.
    current_sha256 : str or None
        The SHA-256 of the file now at the pinned URL, or None if it could
        not be fetched.
    pinned_error : str or None
        Why the pinned file could not be fetched, as the type of error.
    """

    page_url: str
    pinned_sheet: str
    pinned_url: str
    pinned_sha256: str
    linked: tuple[str, ...]
    page_error: str | None
    current_sha256: str | None
    pinned_error: str | None

    @property
    def others(self) -> tuple[str, ...]:
        """The linked spreadsheets other than the pinned one."""
        return tuple(url for url in self.linked if url != self.pinned_url)

    @property
    def status(self) -> str:
        """``"failed"``, ``"changed"``, or ``"unchanged"``, in that precedence.

        A page that could not be fetched links to nothing. A page that links
        to no spreadsheet has failed, since the check can no longer see what
        AAPM publishes. One that links to a spreadsheet, but not the pinned
        one, has changed.
        """
        if self.pinned_error or not self.linked:
            return "failed"
        if self.others or self.current_sha256 != self.pinned_sha256:
            return "changed"
        return "unchanged"


class _Links(html.parser.HTMLParser):
    """Collects every ``href`` value, whatever element carries it."""

    def __init__(self):
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag, attrs):
        self.hrefs.extend(value for name, value in attrs if name == "href" and value)


def spreadsheet_links(page: bytes, page_url: str) -> tuple[str, ...]:
    """Return the absolute URL of each spreadsheet a page links to.

    A link is to a spreadsheet when its path ends in ``.xls`` or ``.xlsx``,
    in any case. Fragments are dropped; queries are kept.
    """
    parser = _Links()
    parser.feed(page.decode("utf-8", errors="replace"))
    parser.close()
    urls = set()
    for href in parser.hrefs:
        url, _ = urllib.parse.urldefrag(urllib.parse.urljoin(page_url, href.strip()))
        path = urllib.parse.urlsplit(url).path
        if posixpath.splitext(path)[1].lower() in _SPREADSHEET_EXTENSIONS:
            urls.add(url)
    return tuple(sorted(urls))


def check_current(
    edition: tg263_published.Edition, page_url: str, fetch: Fetch
) -> EditionCheck:
    """Compare what the resource page links to, and the pinned file, with the pin.

    Parameters
    ----------
    edition : ~pymedphys._nomenclature.tg263_published.Edition
        The pinned edition.
    page_url : str
        The resource page that links to each published edition.
    fetch : callable
        Returns the bytes at a URL, or raises ``OSError`` or
        ``http.client.HTTPException``.

    Returns
    -------
    EditionCheck
        The page and the pinned file are both fetched, whichever fails.
    """
    linked: tuple[str, ...] = ()
    page_error = None
    try:
        linked = spreadsheet_links(fetch(page_url), page_url)
    except (OSError, http.client.HTTPException) as error:
        page_error = _error(error)

    current_sha256 = None
    pinned_error = None
    try:
        current_sha256 = hashlib.sha256(fetch(edition.url)).hexdigest()
    except (OSError, http.client.HTTPException) as error:
        pinned_error = _error(error)

    return EditionCheck(
        page_url=page_url,
        pinned_sheet=edition.sheet,
        pinned_url=edition.url,
        pinned_sha256=edition.sha256,
        linked=linked,
        page_error=page_error,
        current_sha256=current_sha256,
        pinned_error=pinned_error,
    )


def _error(error: BaseException) -> str:
    if isinstance(error, urllib.error.HTTPError):
        return f"HTTP {error.code}"
    return type(error).__name__


def download(url: str) -> bytes:
    """Download the bytes at ``url``.

    What the downloader prints, such as that it will retry, goes to standard
    error, so that standard output carries only the report.
    """
    with (
        tempfile.TemporaryDirectory() as work_dir,
        contextlib.redirect_stdout(sys.stderr),
    ):
        destination = pathlib.Path(work_dir) / "download"
        download_with_progress(url, destination)
        return destination.read_bytes()


def report_lines(result: EditionCheck) -> list[str]:
    """Return the plain-text report of ``result``, one line per entry."""
    lines = [f"Pinned edition: {result.pinned_sheet}, {result.pinned_url}"]
    if result.page_error:
        lines.append(f"Could not fetch {result.page_url} ({result.page_error}).")
    elif not result.linked:
        lines.append("The page links to no spreadsheet.")
    else:
        lines.append(f"Spreadsheets linked from {result.page_url}:")
        lines.extend(f"  {url}" for url in result.linked)
        if result.pinned_url not in result.linked:
            lines.append("The page no longer links to the pinned spreadsheet.")
    if result.pinned_error:
        lines.append(f"Could not fetch {result.pinned_url} ({result.pinned_error}).")
    elif result.current_sha256 != result.pinned_sha256:
        lines.append(
            f"The pinned spreadsheet's SHA-256 is now {result.current_sha256}, "
            f"not {result.pinned_sha256}."
        )
    if result.others:
        lines.append("Spreadsheets other than the pinned one:")
        lines.extend(f"  {url}" for url in result.others)
    lines.append(f"Result: {result.status}")
    return lines


def run(
    edition: tg263_published.Edition,
    page_url: str,
    json_path: pathlib.Path | None = None,
    fetch: Fetch | None = None,
) -> int:
    """Check the resource page, print the report, and return the exit status.

    Parameters
    ----------
    edition : ~pymedphys._nomenclature.tg263_published.Edition
        The pinned edition.
    page_url : str
        The resource page.
    json_path : pathlib.Path, optional
        Also write the result here as JSON, with its ``status``.
    fetch : callable, optional
        As for :func:`check_current`. Defaults to :func:`download`.

    Returns
    -------
    int
        0 when nothing has changed; 1 when the page links to another
        spreadsheet, no longer links to the pinned one, or the pinned file
        has changed; 3 when the page or the pinned file could not be fetched,
        or the page links to no spreadsheet, whether or not anything else
        changed.
    """
    result = check_current(edition, page_url, download if fetch is None else fetch)
    print("\n".join(report_lines(result)))
    if json_path is not None:
        document = {"status": result.status, **dataclasses.asdict(result)}
        json_path.write_text(json.dumps(document, indent=1) + "\n", encoding="utf-8")
    return EXIT_STATUS[result.status]


def tg263_check_cli(args) -> None:
    """Run ``pymedphys dev tg263-check``."""
    status = run(
        tg263_published.PUBLISHED,
        tg263_published.PAGE_URL,
        json_path=pathlib.Path(args.json) if args.json else None,
        fetch=download,
    )
    if status:
        raise SystemExit(status)
