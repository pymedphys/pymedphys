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

"""Check the shipped TCIA Private Tag Dictionary against TCIA's original.

``pymedphys dev tcia-check`` runs :func:`run`. It downloads the file at the
pinned URL and compares its length and SHA-256, and those of the shipped
copy, with :data:`~pymedphys._dicom.deidentify.tcia_private_tags.PIN`. It
also reads the page that links to the file, and lists the editions of the
dictionary that it links to and whether it still links to the CC BY 3.0
licence under which TCIA publishes its site, which the shipped notice relies
on. TCIA publishes a new edition as a new file, so a link to an edition that
maintainers have not reviewed, a page that no longer links to the pinned
file or to the licence, or a pinned file that has changed or gone is
reported as a change. The report names URLs, digests, and types of error,
never the page's text.
"""

from __future__ import annotations

import dataclasses
import hashlib
import html.parser
import http.client
import json
import pathlib
import posixpath
import re
import urllib.error
import urllib.parse
from collections.abc import Iterable

from pymedphys._dev.tg263_edition_check import (
    EXIT_STATUS,
    Fetch,
    download,
    normalised_url,
)
from pymedphys._dicom.deidentify import tcia_private_tags

# A link whose file name starts with this is to an edition of the dictionary.
EDITION_PREFIX = "tciaprivatetagkb"
# The licence under which TCIA publishes its site, which the shipped notice
# names.
LICENCE_URL = "https://creativecommons.org/licenses/by/3.0/"

# Every edition linked from the page that maintainers have reviewed, besides
# the pinned one. A linked edition outside this set is reported as a change,
# so when a new edition is reviewed and not adopted, add its URL here, and
# keep the URL of an edition the pin moves away from.
REVIEWED: frozenset[str] = frozenset()

# A pinned file that the server says is not there has been moved or
# withdrawn, which is a change rather than a failure to check.
_GONE = frozenset({"HTTP 404", "HTTP 410"})
# At most this many URLs are listed under each heading of the report.
_LISTED = 50
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


@dataclasses.dataclass(frozen=True)
class EditionCheck:
    """What TCIA's page and the pinned file show now.

    URLs are normalised as
    :func:`~pymedphys._dev.tg263_edition_check.normalised_url` describes.

    Attributes
    ----------
    page_url : str
        The page that links to the dictionary.
    pinned_url, pinned_sha256 : str
        The pinned file's URL and SHA-256.
    pinned_size : int
        The pinned file's length in bytes.
    shipped_matches : bool
        Whether the shipped copy has the pinned length and SHA-256.
    reviewed : tuple of str
        The reviewed editions other than the pinned one, sorted.
    linked : tuple of str
        The URL of each edition that the page links to, sorted, each once.
    licence_linked : bool
        Whether the page links to :data:`LICENCE_URL`.
    page_error : str or None
        Why the page could not be fetched, as the type of error.
    current_sha256 : str or None
        The SHA-256 of the file now at the pinned URL, or None if it could
        not be fetched.
    current_size : int or None
        Its length in bytes, or None if it could not be fetched.
    pinned_error : str or None
        Why the pinned file could not be fetched, as the type of error.
    """

    page_url: str
    pinned_url: str
    pinned_sha256: str
    pinned_size: int
    shipped_matches: bool
    reviewed: tuple[str, ...]
    linked: tuple[str, ...]
    licence_linked: bool
    page_error: str | None
    current_sha256: str | None
    current_size: int | None
    pinned_error: str | None

    @property
    def unreviewed(self) -> tuple[str, ...]:
        """The linked editions that are neither pinned nor reviewed."""
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
        to no edition has failed, since the check can no longer see what TCIA
        publishes, as has a pinned file that could not be fetched for any
        reason but that it is not there.
        """
        if (self.pinned_error and not self.pinned_gone) or not self.linked:
            return "failed"
        if (
            not self.shipped_matches
            or self.unreviewed
            or self.pinned_url not in self.linked
            or not self.licence_linked
            or self.pinned_differs
        ):
            return "changed"
        return "unchanged"

    @property
    def pinned_differs(self) -> bool:
        """Whether the file at the pinned URL differs from the pin.

        A pinned file that is gone has no current length or SHA-256, so it
        differs.
        """
        return (self.current_sha256, self.current_size) != (
            self.pinned_sha256,
            self.pinned_size,
        )


class _Links(html.parser.HTMLParser):
    """Collects every ``href`` value, whatever element carries it."""

    def __init__(self):
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag, attrs):
        self.hrefs.extend(value for name, value in attrs if name == "href" and value)


def links(page: bytes, page_url: str) -> tuple[str, ...]:
    """Return the normalised URL of every link on a page, sorted, each once.

    Fragments are dropped; queries are kept. A link that is not a valid URL
    is ignored.
    """
    parser = _Links()
    parser.feed(page.decode("utf-8", errors="replace"))
    parser.close()
    urls = set()
    for href in parser.hrefs:
        try:
            joined = urllib.parse.urljoin(page_url, href.strip())
            urls.add(normalised_url(urllib.parse.urldefrag(joined).url))
        except ValueError:
            continue
    return tuple(sorted(urls))


def is_edition(url: str) -> bool:
    """Whether a URL's file name, in any case, names an edition of the dictionary."""
    name = posixpath.basename(urllib.parse.urlsplit(url).path)
    return name.lower().startswith(EDITION_PREFIX)


def check_current(
    pin: tcia_private_tags.Pin,
    fetch: Fetch,
    shipped: bytes,
    reviewed: Iterable[str] = (),
) -> EditionCheck:
    """Compare TCIA's page, the pinned file, and the shipped copy with the pin.

    Parameters
    ----------
    pin : ~pymedphys._dicom.deidentify.tcia_private_tags.Pin
        The pinned file and the page that links to it.
    fetch : callable
        Returns the bytes at a URL, or raises ``OSError`` or
        ``http.client.HTTPException``.
    shipped : bytes
        The shipped copy.
    reviewed : iterable of str, optional
        The reviewed editions other than the pinned one, such as
        :data:`REVIEWED`.

    Returns
    -------
    EditionCheck
        The page and the pinned file are both fetched, whichever fails.
    """
    linked: tuple[str, ...] = ()
    licence_linked = False
    page_error = None
    try:
        on_page = links(fetch(pin.page_url), pin.page_url)
    except (OSError, http.client.HTTPException) as error:
        page_error = _error(error)
    else:
        linked = tuple(url for url in on_page if is_edition(url))
        licence_linked = normalised_url(LICENCE_URL) in on_page

    current_sha256 = None
    current_size = None
    pinned_error = None
    try:
        current = fetch(pin.url)
    except (OSError, http.client.HTTPException) as error:
        pinned_error = _error(error)
    else:
        current_sha256 = hashlib.sha256(current).hexdigest()
        current_size = len(current)

    return EditionCheck(
        page_url=normalised_url(pin.page_url),
        pinned_url=normalised_url(pin.url),
        pinned_sha256=pin.sha256,
        pinned_size=pin.size,
        shipped_matches=(
            len(shipped) == pin.size
            and hashlib.sha256(shipped).hexdigest() == pin.sha256
        ),
        reviewed=tuple(sorted({normalised_url(url) for url in reviewed})),
        linked=linked,
        licence_linked=licence_linked,
        page_error=page_error,
        current_sha256=current_sha256,
        current_size=current_size,
        pinned_error=pinned_error,
    )


def _error(error: BaseException) -> str:
    if isinstance(error, urllib.error.HTTPError):
        return f"HTTP {error.code}"
    return type(error).__name__


def report_lines(result: EditionCheck) -> list[str]:
    """Return the plain-text report of ``result``, one line per entry."""
    lines = [f"Pinned file: {result.pinned_url}"]
    if not result.shipped_matches:
        lines.append("The shipped copy does not have the pinned length and SHA-256.")
    if result.page_error:
        lines.append(f"Could not fetch {result.page_url} ({result.page_error}).")
    else:
        if not result.linked:
            lines.append("The page links to no edition of the dictionary.")
        else:
            lines.append(f"Editions linked from {result.page_url}:")
            lines.extend(_listed(result.linked))
            if result.pinned_url not in result.linked:
                lines.append("The page no longer links to the pinned file.")
        if not result.licence_linked:
            lines.append(f"The page no longer links to {LICENCE_URL}.")
    if result.pinned_gone:
        lines.append(f"The pinned file is gone ({result.pinned_error}).")
    elif result.pinned_error:
        lines.append(f"Could not fetch {result.pinned_url} ({result.pinned_error}).")
    elif result.pinned_differs:
        lines.append(
            f"The pinned file is now {result.current_size} bytes with SHA-256 "
            f"{result.current_sha256}, not {result.pinned_size} bytes with "
            f"{result.pinned_sha256}."
        )
    if result.unreviewed:
        lines.append("Editions not yet reviewed:")
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
    pin: tcia_private_tags.Pin,
    shipped: bytes,
    json_path: pathlib.Path | None = None,
    fetch: Fetch | None = None,
    reviewed: Iterable[str] = (),
) -> int:
    """Check TCIA's page and file, print the report, and return the exit status.

    Parameters
    ----------
    pin : ~pymedphys._dicom.deidentify.tcia_private_tags.Pin
        The pinned file.
    shipped : bytes
        The shipped copy.
    json_path : pathlib.Path, optional
        Also write the result here as JSON, with its ``status``.
    fetch : callable, optional
        As for :func:`check_current`. Defaults to
        :func:`~pymedphys._dev.tg263_edition_check.download`.
    reviewed : iterable of str, optional
        As for :func:`check_current`.

    Returns
    -------
    int
        0 when nothing has changed; 1 when the shipped copy does not match
        the pin, the page links to an edition that has not been reviewed, no
        longer links to the pinned file or to the licence, or the pinned file
        has changed or is gone (HTTP 404 or 410); 3 when the page or the
        pinned file could not be fetched for any other reason, or the page
        links to no edition, whether or not anything else changed.
    """
    result = check_current(pin, download if fetch is None else fetch, shipped, reviewed)
    print("\n".join(report_lines(result)))
    if json_path is not None:
        document = {"status": result.status, **dataclasses.asdict(result)}
        json_path.write_text(json.dumps(document, indent=1) + "\n", encoding="utf-8")
    return EXIT_STATUS[result.status]


def tcia_check_cli(args) -> None:
    """Run ``pymedphys dev tcia-check``."""
    pin = tcia_private_tags.PIN
    status = run(
        pin,
        (tcia_private_tags.TCIA_DIR / pin.file_name).read_bytes(),
        json_path=pathlib.Path(args.json) if args.json else None,
        fetch=download,
        reviewed=REVIEWED,
    )
    if status:
        raise SystemExit(status)
