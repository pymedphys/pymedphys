"""Check whether AAPM has published a TG-263 spreadsheet other than the pinned one.

``pymedphys dev tg263-check`` runs :func:`run`. It reads AAPM's Radiation
Oncology Nomenclature Resource Page and lists the downloads it links to, and
downloads the pinned spreadsheet to compare its SHA-256 with the pin. AAPM
publishes a new edition as a new file, so a link to a download that
maintainers have not reviewed, a page that no longer links to the pinned
spreadsheet, or a pinned file that has changed or gone is reported as a
change. An edition published only on another page is not seen. The report
names URLs, digests, and types of error, never the page's text.
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
import re
import sys
import tempfile
import urllib.error
import urllib.parse
from collections.abc import Callable, Iterable

from pymedphys._data.download import download_with_progress
from pymedphys._nomenclature import tg263_published

# The exit status for each result, as for pymedphys dev deid-tables
# --check-current.
EXIT_STATUS = {"unchanged": 0, "changed": 1, "failed": 3}

# Links whose path ends in one of these are downloads that could hold an
# edition: spreadsheets in any format AAPM might use, and archives.
DOWNLOAD_EXTENSIONS = (".xls", ".xlsx", ".xlsm", ".ods", ".csv", ".zip")

# Every download linked from PAGE_URL that maintainers have reviewed, besides
# the pinned edition: earlier editions, editions reviewed and not adopted, and
# other files. A linked download outside this set, and the pinned edition, is
# reported as a change, so when a new edition is reviewed, add its URL here,
# and keep the URL of an edition the pin moves away from.
REVIEWED = frozenset(
    {
        # Eclipse structure templates using TG-263 names, not an edition.
        tg263_published.PAGE_URL + "EclipseStructureTemplates.zip",
    }
)

# A pinned file that the server says is not there has been moved or
# withdrawn, which is a change rather than a failure to check.
_GONE = frozenset({"HTTP 404", "HTTP 410"})
# At most this many URLs are listed under each heading of the report.
_LISTED = 50
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")

Fetch = Callable[[str], bytes]


@dataclasses.dataclass(frozen=True)
class EditionCheck:
    """What the resource page and the pinned spreadsheet show now.

    URLs are normalised as :func:`normalised_url` describes.

    Attributes
    ----------
    page_url : str
        The resource page.
    pinned_sheet, pinned_url, pinned_sha256 : str
        The pinned edition's worksheet, URL, and SHA-256.
    reviewed : tuple of str
        The reviewed downloads other than the pinned edition, sorted.
    linked : tuple of str
        The URL of each download the page links to, sorted, each once.
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
    reviewed: tuple[str, ...]
    linked: tuple[str, ...]
    page_error: str | None
    current_sha256: str | None
    pinned_error: str | None

    @property
    def unreviewed(self) -> tuple[str, ...]:
        """The linked downloads that are neither pinned nor reviewed."""
        known = {self.pinned_url, *self.reviewed}
        return tuple(url for url in self.linked if url not in known)

    @property
    def pinned_gone(self) -> bool:
        """Whether the server says the pinned file is not there."""
        return self.pinned_error in _GONE

    @property
    def status(self) -> str:
        """``"failed"``, ``"changed"``, or ``"unchanged"``, in that precedence.

        A page that could not be fetched links to nothing. A page that links
        to no download has failed, since the check can no longer see what
        AAPM publishes, as has a pinned file that could not be fetched for any
        reason but that it is not there.
        """
        if (self.pinned_error and not self.pinned_gone) or not self.linked:
            return "failed"
        # A pinned file that is gone has no current SHA-256, so it differs.
        if (
            self.unreviewed
            or self.pinned_url not in self.linked
            or self.current_sha256 != self.pinned_sha256
        ):
            return "changed"
        return "unchanged"


def normalised_url(url: str) -> str:
    """Return a URL with its scheme and host in lower case, and http as https.

    AAPM serves the page over both, so a link that changes only in these
    respects is the same link.
    """
    parts = urllib.parse.urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme == "http":
        scheme = "https"
    return urllib.parse.urlunsplit(
        parts._replace(scheme=scheme, netloc=parts.netloc.lower())
    )


class _Links(html.parser.HTMLParser):
    """Collects every ``href`` value, whatever element carries it."""

    def __init__(self):
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag, attrs):
        self.hrefs.extend(value for name, value in attrs if name == "href" and value)


def download_links(page: bytes, page_url: str) -> tuple[str, ...]:
    """Return the normalised URL of each download a page links to.

    A link is to a download when its path ends in one of
    :data:`DOWNLOAD_EXTENSIONS`, in any case. Fragments are dropped; queries
    are kept. A link that is not a valid URL is ignored.
    """
    parser = _Links()
    parser.feed(page.decode("utf-8", errors="replace"))
    parser.close()
    urls = set()
    for href in parser.hrefs:
        try:
            joined = urllib.parse.urljoin(page_url, href.strip())
            url = normalised_url(urllib.parse.urldefrag(joined).url)
            path = urllib.parse.urlsplit(url).path
        except ValueError:
            continue
        if posixpath.splitext(path)[1].lower() in DOWNLOAD_EXTENSIONS:
            urls.add(url)
    return tuple(sorted(urls))


def check_current(
    edition: tg263_published.Edition,
    page_url: str,
    fetch: Fetch,
    reviewed: Iterable[str] = (),
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
    reviewed : iterable of str, optional
        The reviewed downloads other than the pinned edition, such as
        :data:`REVIEWED`.

    Returns
    -------
    EditionCheck
        The page and the pinned file are both fetched, whichever fails.
    """
    linked: tuple[str, ...] = ()
    page_error = None
    try:
        linked = download_links(fetch(page_url), page_url)
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
        pinned_url=normalised_url(edition.url),
        pinned_sha256=edition.sha256,
        reviewed=tuple(sorted({normalised_url(url) for url in reviewed})),
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
        lines.append("The page links to no download.")
    else:
        lines.append(f"Downloads linked from {result.page_url}:")
        lines.extend(_listed(result.linked))
        if result.pinned_url not in result.linked:
            lines.append("The page no longer links to the pinned spreadsheet.")
    if result.pinned_gone:
        lines.append(f"The pinned spreadsheet is gone ({result.pinned_error}).")
    elif result.pinned_error:
        lines.append(f"Could not fetch {result.pinned_url} ({result.pinned_error}).")
    elif result.current_sha256 != result.pinned_sha256:
        lines.append(
            f"The pinned spreadsheet's SHA-256 is now {result.current_sha256}, "
            f"not {result.pinned_sha256}."
        )
    if result.unreviewed:
        lines.append("Downloads not yet reviewed:")
        lines.extend(_listed(result.unreviewed))
    lines.append(f"Result: {result.status}")
    return lines


def _listed(urls: tuple[str, ...]) -> list[str]:
    """Indent each URL, without control characters, listing at most _LISTED."""
    lines = [f"  {_CONTROL.sub('', url)}" for url in urls[:_LISTED]]
    if len(urls) > _LISTED:
        lines.append(f"  and {len(urls) - _LISTED} more")
    return lines


def run(
    edition: tg263_published.Edition,
    page_url: str,
    json_path: pathlib.Path | None = None,
    fetch: Fetch | None = None,
    reviewed: Iterable[str] = (),
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
    reviewed : iterable of str, optional
        As for :func:`check_current`.

    Returns
    -------
    int
        0 when nothing has changed; 1 when the page links to a download
        that has not been reviewed, no longer links to the pinned
        spreadsheet, or the pinned file has changed or is gone (HTTP 404 or
        410); 3 when the page or the pinned file could not be fetched for any
        other reason, or the page links to no download, whether or not
        anything else changed.
    """
    result = check_current(
        edition, page_url, download if fetch is None else fetch, reviewed
    )
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
        reviewed=REVIEWED,
    )
    if status:
        raise SystemExit(status)
