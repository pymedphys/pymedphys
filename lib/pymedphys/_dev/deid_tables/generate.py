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
and the acknowledgement of its part, such as "DICOM PS3.15 <edition>, © NEMA".
"""

from __future__ import annotations

import dataclasses
import functools
import json
import os
import pathlib
import re
import sys
import tempfile
import urllib.error
from collections.abc import Callable, Mapping

from pymedphys._data.download import download_with_progress
from pymedphys._dicom.deidentify.codes import CODE_TABLES
from pymedphys._dicom.deidentify.iods import IOD_MODULES_TABLE, MODULE_ATTRIBUTES_TABLE
from pymedphys._dicom.deidentify.sop_classes import STORAGE_SOP_CLASS_TABLE
from pymedphys._dicom.deidentify.standard import SCHEMA, STANDARD_DIR, content_sha256
from pymedphys._dicom.deidentify.uid_registry import UID_TABLES

from . import annex_e, chtml, ps3_3, ps3_4, ps3_6, ps3_16
from .sources import SourceDigestError, read_verified_source

# NEMA serves the current edition only under "current". Superseded editions
# are served from their own directory, apparently unchanged (the archived 2026c
# pages keep their original modification dates). Either location is accepted,
# provided the file matches its pinned digest.
_SOURCE_URLS = (
    "https://dicom.nema.org/medical/dicom/{edition}/output/{path}",
    "https://dicom.nema.org/medical/dicom/current/output/{path}",
)

DEFAULT_OUTPUT_DIR = STANDARD_DIR


@dataclasses.dataclass(frozen=True)
class PinnedSource:
    """A page of the published standard and its SHA-256 digest.

    Attributes
    ----------
    path : str
        The page's path below ``output/``: below ``chtml/`` for a page of one
        section, such as ``"chtml/part15/chapter_E.html"``, or below
        ``html/`` for a whole part on one page, such as
        ``"html/part03.html"``. A local source directory uses the same
        layout.
    sha256 : str
        The digest of the page as NEMA publishes it.
    """

    path: str
    sha256: str


@dataclasses.dataclass(frozen=True)
class Pin:
    """The edition the tables are generated from, and what is read from it.

    Attributes
    ----------
    edition : str
        The edition, such as ``"2026d"``.
    sources : tuple of PinnedSource
        Its source pages.
    functional_group_iods : tuple of (str, str)
        The label and IOD name of each "IOD Modules" table of PS3.3 Annex A
        whose Types are not generated, because its modules include Functional
        Group Macros, such as ``("Table A.38-1", "Enhanced CT Image")``. The
        Types of every other IOD in Annex A are generated. Labels can change
        between editions, so generation checks each name.
    corrections : tuple of Correction
        Corrections to errors in the edition's PS3.3 tables. Generation fails
        if one no longer applies.
    """

    edition: str
    sources: tuple[PinnedSource, ...]
    functional_group_iods: tuple[tuple[str, str], ...]
    corrections: tuple[ps3_3.Correction, ...]


# To move to a new edition, update the edition and every digest, regenerate,
# and review the changes to the generated tables.
PIN = Pin(
    edition="2026d",
    sources=(
        PinnedSource(
            "chtml/part15/chapter_E.html",
            "cb214710fce798ed3688b4cb1d6b2d62ebd254e6946aa3efb3fc14038a41d58d",
        ),
        PinnedSource(
            "chtml/part15/sect_E.3.10.html",
            "101ac4aedd9d45fba8adaa35cab22820d6c0cbda82cdf51d7456f4bf3dafe3a0",
        ),
        PinnedSource(
            "chtml/part06/chapter_6.html",
            "7f3518a7edfccf99f5ff90e3efc40ac96e19f34efb7a803ce14962f460a0d2b1",
        ),
        PinnedSource(
            "chtml/part06/chapter_A.html",
            "778ad3e471c81885b828d814e71b9395fd06a5b64abfe43728e903173a461eff",
        ),
        PinnedSource(
            "chtml/part16/chapter_8.html",
            "14b5472ced78b0271643725b54a259ab943aafd20dc3d0ba43e6f2e7698c3471",
        ),
        PinnedSource(
            "chtml/part16/sect_CID_7050.html",
            "075a339ca7a36cd5cee07ccb66a1b03fc4e3f2fb4f527f57ea68a7111971e834",
        ),
        PinnedSource(
            "chtml/part16/sect_CID_7005.html",
            "15d1ca542b46cda0a5525f59ea8417f3d253e0259037ac5f567ccf31972f28b0",
        ),
        PinnedSource(
            "chtml/part04/sect_B.5.html",
            "a2e6f76967f3bab769299715c01f59757cede79cb9314b5bad60bb72a11e8846",
        ),
        # PS3.3 on one page: its module and macro tables span dozens of chtml
        # pages.
        PinnedSource(
            "html/part03.html",
            "6756c17c08913360c729b666277fb6eed6fda5d1d5b9fde427bbf27c6c1feec6",
        ),
    ),
    # A module of each of these IODs, such as the Multi-frame Functional
    # Groups Module, includes the Functional Group Macros that the IOD lists
    # in a table of its own, which is not yet generated.
    functional_group_iods=(
        ("Table A.8-3", "Multi-frame Grayscale Byte Secondary Capture Image"),
        ("Table A.8-4", "Multi-frame Grayscale Word Secondary Capture Image"),
        ("Table A.8-5", "Multi-frame True Color Secondary Capture Image"),
        ("Table A.32.8-1", "VL Whole Slide Microscopy Image"),
        ("Table A.32.9-1", "Real-Time Video Endoscopic Image"),
        ("Table A.32.10-1", "Real-Time Video Photographic Image"),
        ("Table A.34.11-1", "Real-Time Audio Waveform"),
        ("Table A.36-1", "Enhanced MR Image"),
        ("Table A.36-3", "MR Spectroscopy"),
        ("Table A.36-5", "Enhanced MR Color Image"),
        ("Table A.38-1", "Enhanced CT Image"),
        ("Table A.47-1", "Enhanced XA Image"),
        ("Table A.48-1", "Enhanced XRF Image"),
        ("Table A.51-1", "Segmentation"),
        ("Table A.52.3-1", "Ophthalmic Tomography Image"),
        ("Table A.53-1", "X-Ray 3D Angiographic Image"),
        ("Table A.54-1", "X-Ray 3D Craniofacial Image"),
        ("Table A.55-1", "Breast Tomosynthesis Image"),
        ("Table A.56-1", "Enhanced PET Image"),
        ("Table A.59-1", "Enhanced US Volume"),
        ("Table A.66.3-1", "Intravascular Optical Coherence Tomography Image"),
        ("Table A.70-1", "Legacy Converted Enhanced CT Image"),
        ("Table A.71-1", "Legacy Converted Enhanced MR Image"),
        ("Table A.72-1", "Legacy Converted Enhanced PET Image"),
        ("Table A.74-1", "Breast Projection X-Ray Image"),
        ("Table A.75-1", "Parametric Map"),
        (
            "Table A.84-1",
            "Ophthalmic Optical Coherence Tomography B-scan Volume Analysis",
        ),
        ("Table A.86.1.15-1", "Enhanced RT Image"),
        ("Table A.86.1.16-1", "Enhanced Continuous RT Image"),
        ("Table A.89.3-1", "Photoacoustic Image"),
        ("Table A.90.1.3-1", "Confocal Microscopy Image"),
        ("Table A.90.2.3-1", "Confocal Microscopy Tiled Pyramidal Image"),
        ("Table A.91-1", "Height Map Segmentation"),
    ),
    corrections=(
        # A usage code separated from its condition by an en dash, or by
        # nothing, rather than " - ".
        ps3_3.Correction("Table A.29.3-1", "C – ", "C - "),
        ps3_3.Correction("Table A.50-1", "C – ", "C - "),
        ps3_3.Correction("Table A.80.2.3-1", "C Required", "C - Required"),
        # The Implant Template Group Module's table is in C.29.3.1, below the
        # section the IOD cites; the Enhanced Contrast/Bolus Module is C.7.6.4b,
        # not the Contrast/Bolus Module's C.7.6.4.
        ps3_3.Correction("Table A.63-1", "C.29.3", "C.29.3.1"),
        ps3_3.Correction("Table A.66.3-1", "C.7.6.4", "C.7.6.4b"),
        # Module tables whose titles differ from "<module> Module Attributes".
        ps3_3.Correction("Table C.8-13", "Multi-Gated", "Multi-gated"),
        ps3_3.Correction("Table C.8-62", "Multi-Gated", "Multi-gated"),
        ps3_3.Correction("Table C.8.19.2-1", "Module Table", "Module Attributes"),
        ps3_3.Correction(
            "Table C.39.1-1", "Relationship Module", "Relationship Module Attributes"
        ),
        # A name column headed "Attribute name", and an Include row with a
        # space after its ">" characters.
        ps3_3.Correction("Table C.11.5-1", "Attribute name", "Attribute Name"),
        ps3_3.Correction("Table C.11.25-1", ">> Include", ">>Include"),
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


_CHAPTER_E = "chtml/part15/chapter_E.html"
_SECTION_E3_10 = "chtml/part15/sect_E.3.10.html"
_CHAPTER_6 = "chtml/part06/chapter_6.html"
_CHAPTER_A = "chtml/part06/chapter_A.html"
# The page that publishes each PS3.16 table.
_CODE_TABLE_PAGES = {
    "Table 8-1": "chtml/part16/chapter_8.html",
    "Table 8-2": "chtml/part16/chapter_8.html",
    "Table CID 7050": "chtml/part16/sect_CID_7050.html",
    "Table CID 7005": "chtml/part16/sect_CID_7005.html",
}
_SECTION_B_5 = "chtml/part04/sect_B.5.html"
_PS3_3 = "html/part03.html"
_PART = re.compile(r"part([0-9]{2})")


@functools.lru_cache(maxsize=8)
def _tables(page: bytes, expand_spans: bool) -> tuple[chtml.HtmlTable, ...]:
    """Return a page's tables, extracting them once for every table they serve."""
    return tuple(chtml.extract_tables(page.decode("utf-8"), expand_spans=expand_spans))


def _select(pages: Mapping[str, bytes], source: str, label: str) -> chtml.HtmlTable:
    return chtml.select_table(_tables(pages[source], False), label)


def _document(
    pin: Pin, source: str, label: str, rows: list[dict[str, object]]
) -> dict[str, object]:
    """Return a table's document, recording only the page it came from."""
    digests = {pinned.path: pinned.sha256 for pinned in pin.sources}
    # The page's path names the part, as in "chtml/part06/chapter_6.html" or
    # "html/part03.html".
    match = _PART.search(source)
    if match is None:
        raise ValueError(f"{source} does not name a part of the standard")
    part = f"PS3.{int(match[1])}"
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


def _storage_sop_classes(pin: Pin, pages: Mapping[str, bytes]) -> dict[str, object]:
    sop_classes = ps3_4.parse_table_b_5_1(
        _select(pages, _SECTION_B_5, ps3_4.TABLE_B_5_1)
    )
    rows = [dataclasses.asdict(sop_class) for sop_class in sop_classes]
    return _document(pin, _SECTION_B_5, ps3_4.TABLE_B_5_1, rows)


def _ps3_3(
    pin: Pin, pages: Mapping[str, bytes]
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Return the IOD modules tables and the attribute tables they reach."""
    dictionary = {
        attribute.tag: attribute.vr
        for attribute in ps3_6.parse_table_6_1(
            _select(pages, _CHAPTER_6, ps3_6.TABLE_6_1)
        )
    }
    tables = ps3_3.correct(_tables(pages[_PS3_3], True), pin.corrections)
    return ps3_3.collect(tables, dictionary, pin.functional_group_iods)


def _iod_modules(pin: Pin, pages: Mapping[str, bytes]) -> dict[str, object]:
    return _document(
        pin, _PS3_3, IOD_MODULES_TABLE.removeprefix("PS3.3 "), _ps3_3(pin, pages)[0]
    )


def _module_attributes(pin: Pin, pages: Mapping[str, bytes]) -> dict[str, object]:
    return _document(
        pin,
        _PS3_3,
        MODULE_ATTRIBUTES_TABLE.removeprefix("PS3.3 "),
        _ps3_3(pin, pages)[1],
    )


def _registry_table(
    source: str, label: str, parse: Callable[[str, chtml.HtmlTable], tuple]
) -> Callable[[Pin, Mapping[str, bytes]], dict[str, object]]:
    """Return the function that builds the document for a registry table."""

    def build(pin: Pin, pages: Mapping[str, bytes]) -> dict[str, object]:
        rows = parse(label, _select(pages, source, label))
        return _document(pin, source, label, [dataclasses.asdict(row) for row in rows])

    return build


# Each generated file and the function that builds its document.
_OUTPUTS: dict[str, Callable[[Pin, Mapping[str, bytes]], dict[str, object]]] = {
    "e1_1.json": _table_e1_1,
    "e1_1a.json": _table_e1_1a,
    "e3_10_1.json": _table_e3_10_1,
    "data_dictionary.json": _data_dictionary,
    "iod_modules.json": _iod_modules,
    "module_attributes.json": _module_attributes,
    STORAGE_SOP_CLASS_TABLE.file: _storage_sop_classes,
    **{
        spec.file: _registry_table(_CHAPTER_A, label, ps3_6.parse_uid_table)
        for label, spec in UID_TABLES.items()
    },
    **{
        spec.file: _registry_table(
            _CODE_TABLE_PAGES[label], label, ps3_16.parse_code_table
        )
        for label, spec in CODE_TABLES.items()
    },
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
        A directory holding the source pages at their paths below
        ``output/``. If omitted, the pages are downloaded from NEMA.
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
