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

"""Check whether NEMA's current edition would change the generated tables.

``pymedphys dev deid-tables --check-current`` runs :func:`run`. It reads the
pinned pages from NEMA's unpinned ``current/`` directory, generates each
table from them with the same parsers and the pin's corrections, and compares
the digest of the table's rows with the one recorded in the committed table.
It never writes the tables, and its report names tables, pages, editions, and
types of error, never the pages' text.
"""

from __future__ import annotations

import contextlib
import dataclasses
import hashlib
import http.client
import json
import pathlib
import re
import sys
import tempfile
import urllib.error
from collections.abc import Callable, Iterator, Mapping

from pymedphys._data.download import download_with_progress

from . import generate
from .generate import _OUTPUTS, _SOURCE_URLS, Pin

# The exit status for each result. A table that would change gives 1, as a
# table that differs does for --check.
EXIT_STATUS = {"unchanged": 0, "changed": 1, "failed": 3}

# Each chtml page names its edition in its release information, and each
# single-page part in its subtitle, as "DICOM PS3.15 2026d - Security and
# System Management Profiles".
_EDITION = re.compile(rb">DICOM PS3\.[0-9]+ ([0-9]{4}[a-z]) - ")

Fetch = Callable[[str], bytes]


class _NotFetched(KeyError):
    """A table reads a page that could not be fetched."""


class _Pages(Mapping[str, bytes]):
    """The fetched pages, recording which of them a table reads."""

    def __init__(self, fetched: Mapping[str, bytes]):
        self._fetched = fetched
        self.read: list[str] = []

    def __getitem__(self, path: str) -> bytes:
        if path not in self.read:
            self.read.append(path)
        if path not in self._fetched:
            raise _NotFetched(path)
        return self._fetched[path]

    def __iter__(self) -> Iterator[str]:
        return iter(self._fetched)

    def __len__(self) -> int:
        return len(self._fetched)


@dataclasses.dataclass(frozen=True)
class TableFailure:
    """Why a table could not be generated from the current pages.

    Attributes
    ----------
    pages : tuple of str
        The pages the table read before it failed, the last of which failed.
    error : str
        ``"not fetched"``, or the type of error raised, such as
        ``"TableFormatError"``.
    """

    pages: tuple[str, ...]
    error: str


@dataclasses.dataclass(frozen=True)
class EditionCheck:
    """What regenerating the tables from the current pages would change.

    Attributes
    ----------
    pinned_edition : str
        The edition the committed tables are generated from.
    editions : dict of str to str or None
        The edition each fetched page names, keyed by its path, or None for a
        page that names none.
    changed_pages : tuple of str
        The fetched pages whose SHA-256 digest differs from the pinned one.
    unfetched_pages : dict of str to str
        Each page that could not be fetched, with the type of error.
    changed_tables : tuple of str
        The file of each table whose rows would change.
    failed_tables : dict of str to TableFailure
        The file of each table that could not be generated, and why.
    """

    pinned_edition: str
    editions: dict[str, str | None]
    changed_pages: tuple[str, ...]
    unfetched_pages: dict[str, str]
    changed_tables: tuple[str, ...]
    failed_tables: dict[str, TableFailure]

    @property
    def status(self) -> str:
        """``"failed"``, ``"changed"``, or ``"unchanged"``, in that precedence."""
        if self.unfetched_pages or self.failed_tables:
            return "failed"
        return "changed" if self.changed_tables else "unchanged"


def _error(error: BaseException) -> str:
    # A parser's message can quote the page, so only the type is reported.
    if isinstance(error, urllib.error.HTTPError):
        return f"HTTP {error.code}"
    return type(error).__name__


def _edition(page: bytes) -> str | None:
    match = _EDITION.search(page)
    return match[1].decode("ascii") if match else None


def _recorded_digest(path: pathlib.Path) -> object:
    """Return the row digest a committed table records, or None."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return document.get("content_sha256") if isinstance(document, dict) else None


def check_current(pin: Pin, tables_dir: pathlib.Path, fetch: Fetch) -> EditionCheck:
    """Compare the tables generated from ``fetch``'s pages with those committed.

    Parameters
    ----------
    pin : Pin
        Gives the pages to fetch, by their paths, and the corrections and
        named IODs that generation applies. Its digests are not checked.
    tables_dir : pathlib.Path
        The committed tables. Nothing in it is written.
    fetch : callable
        Returns the bytes of the page at a path below ``output/``, or raises
        ``OSError`` or ``http.client.HTTPException``.

    Returns
    -------
    EditionCheck
        Every table is compared, or reported as not generated with the pages
        it read, whatever error a page raises.
    """
    fetched: dict[str, bytes] = {}
    unfetched: dict[str, str] = {}
    for source in pin.sources:
        try:
            fetched[source.path] = fetch(source.path)
        except (OSError, http.client.HTTPException) as error:
            unfetched[source.path] = _error(error)

    changed: list[str] = []
    failed: dict[str, TableFailure] = {}
    for name, build in _OUTPUTS.items():
        pages = _Pages(fetched)
        try:
            digest = build(pin, pages)["content_sha256"]
        # A page that cannot be parsed must be reported whatever the parser
        # raises, and must not stop the other tables being compared.
        except Exception as error:  # pylint: disable = broad-exception-caught
            reason = "not fetched" if isinstance(error, _NotFetched) else _error(error)
            failed[name] = TableFailure(tuple(pages.read), reason)
        else:
            if digest != _recorded_digest(tables_dir / name):
                changed.append(name)

    return EditionCheck(
        pinned_edition=pin.edition,
        editions={path: _edition(page) for path, page in fetched.items()},
        changed_pages=tuple(
            source.path
            for source in pin.sources
            if source.path in fetched
            and hashlib.sha256(fetched[source.path]).hexdigest() != source.sha256
        ),
        unfetched_pages=unfetched,
        changed_tables=tuple(changed),
        failed_tables=failed,
    )


def download_current(path: str) -> bytes:
    """Download the page at ``path`` below ``output/`` from NEMA's ``current/``.

    What the downloader prints, such as that it will retry, goes to standard
    error, so that standard output carries only the report.
    """
    url = _SOURCE_URLS[0].format(edition="current", path=path)
    with (
        tempfile.TemporaryDirectory() as work_dir,
        contextlib.redirect_stdout(sys.stderr),
    ):
        destination = pathlib.Path(work_dir) / "page.html"
        download_with_progress(url, destination)
        return destination.read_bytes()


def _reader(source_dir: pathlib.Path) -> Fetch:
    """Return a fetcher that reads each page from ``source_dir``."""

    def read(path: str) -> bytes:
        return (source_dir / path).read_bytes()

    return read


def report_lines(result: EditionCheck) -> list[str]:
    """Return the plain-text report of ``result``, one line per entry."""
    editions = sorted({edition or "none" for edition in result.editions.values()})
    lines = [
        f"Pinned edition: {result.pinned_edition}",
        f"Edition the current pages name: {', '.join(editions) or 'none'}",
    ]
    sections = (
        ("Pages that differ from the pin", result.changed_pages),
        (
            "Pages that could not be fetched",
            [f"{path} ({error})" for path, error in result.unfetched_pages.items()],
        ),
        ("Tables that would change", result.changed_tables),
        (
            "Tables that could not be generated",
            [
                f"{name} from {', '.join(failure.pages)} ({failure.error})"
                for name, failure in result.failed_tables.items()
            ],
        ),
    )
    for heading, entries in sections:
        if entries:
            lines.append(f"{heading}:")
            lines.extend(f"  {entry}" for entry in entries)
    lines.append(f"Result: {result.status}")
    return lines


def run(
    pin: Pin,
    tables_dir: pathlib.Path,
    source_dir: pathlib.Path | None = None,
    json_path: pathlib.Path | None = None,
) -> int:
    """Check the current pages, print the report, and return the exit status.

    Parameters
    ----------
    pin : Pin
        The pin whose pages are checked.
    tables_dir : pathlib.Path
        The committed tables.
    source_dir : pathlib.Path, optional
        Read the pages from this directory, laid out as ``output/``, instead
        of downloading them from NEMA's ``current/``.
    json_path : pathlib.Path, optional
        Also write the result here as JSON, with its ``status``.

    Returns
    -------
    int
        0 when no table would change; 1 when a table would change; 3 when a
        page could not be fetched or a table could not be generated, whether
        or not another table would change.
    """
    fetch = download_current if source_dir is None else _reader(source_dir)
    result = check_current(pin, tables_dir, fetch)
    print("\n".join(report_lines(result)))
    if json_path is not None:
        document = {"status": result.status, **dataclasses.asdict(result)}
        json_path.write_text(json.dumps(document, indent=1) + "\n", encoding="utf-8")
    return EXIT_STATUS[result.status]


def edition_check_cli(args) -> None:
    """Run ``pymedphys dev deid-tables --check-current``."""
    status = run(
        generate.PIN,
        pathlib.Path(args.output_dir),
        source_dir=pathlib.Path(args.source_dir) if args.source_dir else None,
        json_path=pathlib.Path(args.json) if args.json else None,
    )
    if status:
        raise SystemExit(status)
