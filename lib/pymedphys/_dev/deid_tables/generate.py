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

"""Generate the de-identification rule tables from the pinned edition.

``pymedphys dev deid-tables`` runs :func:`generate`. Every source file is
checked against the SHA-256 digest pinned here before it is parsed, and each
generated file records the edition, the source digests, a digest of its rows,
and the acknowledgement of its part, such as "DICOM PS3.15 <edition>, © NEMA"
(decision D-001 of the de-identification design).
"""

from __future__ import annotations

import dataclasses
import json
import os
import pathlib
import sys
import tempfile
import urllib.error
from collections.abc import Callable, Mapping

from pymedphys._data.download import download_with_progress
from pymedphys._dicom.deidentify.standard import SCHEMA, STANDARD_DIR, content_sha256
from pymedphys._dicom.deidentify.uid_registry import UID_TABLES

from . import annex_e, chtml, ps3_6
from .sources import SourceDigestError, read_verified_source

# NEMA serves the current edition only under "current". Superseded editions
# are served from their own directory, apparently unchanged (the archived 2026c
# pages keep their original modification dates). Either location is accepted,
# provided the file matches its pinned digest.
_SOURCE_URLS = (
    "https://dicom.nema.org/medical/dicom/{edition}/output/chtml/{path}",
    "https://dicom.nema.org/medical/dicom/current/output/chtml/{path}",
)

DEFAULT_OUTPUT_DIR = STANDARD_DIR


@dataclasses.dataclass(frozen=True)
class PinnedSource:
    """A page of the chtml publication and its SHA-256 digest.

    Attributes
    ----------
    path : str
        The page's path below ``output/chtml/``, such as
        ``"part15/chapter_E.html"``. A local source directory uses the same
        layout.
    sha256 : str
        The digest of the page as NEMA publishes it.
    """

    path: str
    sha256: str


@dataclasses.dataclass(frozen=True)
class Pin:
    """The edition the tables are generated from, and its source pages."""

    edition: str
    sources: tuple[PinnedSource, ...]


# To move to a new edition, update the edition and every digest, regenerate,
# and review the changes to the generated tables.
PIN = Pin(
    edition="2026d",
    sources=(
        PinnedSource(
            "part15/chapter_E.html",
            "cb214710fce798ed3688b4cb1d6b2d62ebd254e6946aa3efb3fc14038a41d58d",
        ),
        PinnedSource(
            "part15/sect_E.3.10.html",
            "101ac4aedd9d45fba8adaa35cab22820d6c0cbda82cdf51d7456f4bf3dafe3a0",
        ),
        PinnedSource(
            "part06/chapter_6.html",
            "7f3518a7edfccf99f5ff90e3efc40ac96e19f34efb7a803ce14962f460a0d2b1",
        ),
        PinnedSource(
            "part06/chapter_A.html",
            "778ad3e471c81885b828d814e71b9395fd06a5b64abfe43728e903173a461eff",
        ),
    ),
)


def _download_verified(
    source: PinnedSource, edition: str, work_dir: pathlib.Path
) -> bytes:
    """Download ``source`` from the first location that matches its digest."""
    attempts: list[str] = []
    for template in _SOURCE_URLS:
        url = template.format(edition=edition, path=source.path)
        destination = work_dir / f"{len(attempts)}.html"
        try:
            download_with_progress(url, destination)
        except urllib.error.HTTPError as error:
            if error.code != 404:
                raise
            attempts.append(f"{url}: not found")
            continue
        try:
            return read_verified_source(destination, source.sha256)
        except SourceDigestError as error:
            attempts.append(f"{url}: {error}")
    raise SourceDigestError(
        f"no download of {source.path} matches the pinned digest for {edition}: "
        + "; ".join(attempts)
    )


def _read_sources(pin: Pin, source_dir: pathlib.Path | None) -> dict[str, bytes]:
    if source_dir is not None:
        return {
            source.path: read_verified_source(source_dir / source.path, source.sha256)
            for source in pin.sources
        }
    with tempfile.TemporaryDirectory() as work_dir:
        return {
            source.path: _download_verified(source, pin.edition, pathlib.Path(work_dir))
            for source in pin.sources
        }


_CHAPTER_E = "part15/chapter_E.html"
_SECTION_E3_10 = "part15/sect_E.3.10.html"
_CHAPTER_6 = "part06/chapter_6.html"
_CHAPTER_A = "part06/chapter_A.html"


def _select(pages: Mapping[str, bytes], source: str, label: str) -> chtml.HtmlTable:
    return chtml.select_table(
        chtml.extract_tables(pages[source].decode("utf-8")), label
    )


def _document(
    pin: Pin, source: str, label: str, rows: list[dict[str, object]]
) -> dict[str, object]:
    """Return a table's document, recording only the page it came from."""
    digests = {pinned.path: pinned.sha256 for pinned in pin.sources}
    # The page's directory names the part, as in "part06/chapter_6.html".
    part = f"PS3.{int(source.split('/')[0].removeprefix('part'))}"
    return {
        "schema": SCHEMA,
        "table": f"{part} {label}",
        "edition": pin.edition,
        "acknowledgement": f"DICOM {part} {pin.edition}, © NEMA",
        "sources": [{"path": source, "sha256": digests[source]}],
        "content_sha256": content_sha256(rows),
        "rows": rows,
    }


def _table_e1_1(pin: Pin, pages: Mapping[str, bytes]) -> dict[str, object]:
    attributes = annex_e.parse_table_e1_1(
        _select(pages, _CHAPTER_E, annex_e.TABLE_E1_1)
    )
    rows: list[dict[str, object]] = [
        {
            "name": attribute.name,
            "tag": attribute.tag,
            "retired": attribute.retired,
            "in_standard_iod": attribute.in_standard_iod,
            "basic_profile": attribute.basic_profile,
            "options": dict(attribute.options),
        }
        for attribute in attributes
    ]
    return _document(pin, _CHAPTER_E, annex_e.TABLE_E1_1, rows)


def _table_e1_1a(pin: Pin, pages: Mapping[str, bytes]) -> dict[str, object]:
    codes = annex_e.parse_table_e1_1a(_select(pages, _CHAPTER_E, annex_e.TABLE_E1_1A))
    rows: list[dict[str, object]] = [
        {"code": action.code, "description": action.description} for action in codes
    ]
    return _document(pin, _CHAPTER_E, annex_e.TABLE_E1_1A, rows)


def _table_e3_10_1(pin: Pin, pages: Mapping[str, bytes]) -> dict[str, object]:
    attributes = annex_e.parse_table_e3_10_1(
        _select(pages, _SECTION_E3_10, annex_e.TABLE_E3_10_1)
    )
    rows: list[dict[str, object]] = [
        {
            "tag": attribute.tag,
            "private_creator": attribute.private_creator,
            "vr": attribute.vr,
            "vm": attribute.vm,
            "meaning": attribute.meaning,
        }
        for attribute in attributes
    ]
    return _document(pin, _SECTION_E3_10, annex_e.TABLE_E3_10_1, rows)


def _data_dictionary(pin: Pin, pages: Mapping[str, bytes]) -> dict[str, object]:
    attributes = ps3_6.parse_table_6_1(_select(pages, _CHAPTER_6, ps3_6.TABLE_6_1))
    rows: list[dict[str, object]] = [
        {
            "tag": attribute.tag,
            "name": attribute.name,
            "keyword": attribute.keyword,
            "vr": attribute.vr,
            "vm": attribute.vm,
            "status": attribute.status,
        }
        for attribute in attributes
    ]
    return _document(pin, _CHAPTER_6, ps3_6.TABLE_6_1, rows)


def _uid_table(label: str) -> Callable[[Pin, Mapping[str, bytes]], dict[str, object]]:
    """Return the function that builds the document for an Annex A table."""

    def build(pin: Pin, pages: Mapping[str, bytes]) -> dict[str, object]:
        rows = ps3_6.parse_uid_table(label, _select(pages, _CHAPTER_A, label))
        return _document(
            pin, _CHAPTER_A, label, [dataclasses.asdict(row) for row in rows]
        )

    return build


# Each generated file and the function that builds its document.
_OUTPUTS: dict[str, Callable[[Pin, Mapping[str, bytes]], dict[str, object]]] = {
    "e1_1.json": _table_e1_1,
    "e1_1a.json": _table_e1_1a,
    "e3_10_1.json": _table_e3_10_1,
    "data_dictionary.json": _data_dictionary,
    **{spec.file: _uid_table(label) for label, spec in UID_TABLES.items()},
}


def _render(document: Mapping[str, object]) -> str:
    return json.dumps(document, indent=1, ensure_ascii=False) + "\n"


def _write_atomically(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".part"
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as file:
            file.write(text)
        os.replace(temporary, path)
    except BaseException:
        pathlib.Path(temporary).unlink(missing_ok=True)
        raise


def generate(
    pin: Pin,
    output_dir: pathlib.Path,
    source_dir: pathlib.Path | None = None,
    check: bool = False,
) -> int:
    """Generate the rule tables, or check that the written ones are current.

    Parameters
    ----------
    pin : Pin
        The edition and the digests of its source pages.
    output_dir : pathlib.Path
        Where the generated tables are written or checked.
    source_dir : pathlib.Path, optional
        A directory holding the source pages at their ``output/chtml/``
        paths. If omitted, the pages are downloaded from NEMA.
    check : bool, optional
        Compare the generated tables with those in ``output_dir`` instead of
        writing them.

    Returns
    -------
    int
        0 on success; 1 if ``check`` found a table missing or different, in
        which case the differences are listed on standard error.

    Raises
    ------
    SourceDigestError
        If a source page does not match its pinned digest. Nothing is written.
    TableFormatError
        If a table does not have the expected structure or values. Nothing is
        written.
    """
    pages = _read_sources(pin, source_dir)
    rendered = {name: _render(build(pin, pages)) for name, build in _OUTPUTS.items()}

    if check:
        problems = []
        for name, text in rendered.items():
            path = output_dir / name
            if not path.exists():
                problems.append(f"{name} is missing")
            elif path.read_text(encoding="utf-8") != text:
                problems.append(
                    f"{name} differs from the tables generated from {pin.edition}"
                )
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1 if problems else 0

    for name, text in rendered.items():
        _write_atomically(output_dir / name, text)
    return 0


def deid_tables_cli(args) -> None:
    """Run ``pymedphys dev deid-tables``."""
    status = generate(
        PIN,
        pathlib.Path(args.output_dir),
        source_dir=pathlib.Path(args.source_dir) if args.source_dir else None,
        check=args.check,
    )
    if status:
        raise SystemExit(status)
