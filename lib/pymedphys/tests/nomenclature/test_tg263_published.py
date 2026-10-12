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

"""Downloading the published TG-263 spreadsheet, pinned by its SHA-256.

Only the slow test reaches the network, to check the pins against AAPM's
file. Every other test downloads the invented spreadsheet in ``data/``
through a stand-in for the downloader, against an invented edition.
"""

import dataclasses
import hashlib
import pathlib
import re
import shutil

from pymedphys._imports import pytest

from pymedphys._nomenclature import tg263, tg263_published

SPREADSHEET = pathlib.Path(__file__).parent / "data" / "tg263_invented.xls"
URL = "https://example.invalid/reports/TG263_Invented_20260101.xls"


def _invented_edition():
    nomenclature = tg263.read_spreadsheet(SPREADSHEET)
    return tg263_published.Edition(
        sheet=nomenclature.source.sheet,
        url=URL,
        sha256=hashlib.sha256(SPREADSHEET.read_bytes()).hexdigest(),
        content_sha256=tg263.content_sha256(
            [dataclasses.asdict(s) for s in nomenclature.structures]
        ),
    )


EDITION = _invented_edition()


class _Downloader:
    """Records each download and writes ``content`` where it is asked to."""

    def __init__(self, content=None):
        self.content = SPREADSHEET.read_bytes() if content is None else content
        self.urls = []

    def __call__(self, url, filepath):
        self.urls.append(url)
        pathlib.Path(filepath).write_bytes(self.content)


def _cached_files(data_dir):
    """Every file in the cache directory but the download lock."""
    return [
        path
        for path in (data_dir / "tg263").iterdir()
        if not path.name.endswith(".pymedphys-download-lock")
    ]


@pytest.fixture(name="data_dir")
def _data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("PYMEDPHYS_DATA_DIR", str(tmp_path))
    return tmp_path


def test_the_published_edition_is_pinned():
    edition = tg263_published.PUBLISHED
    assert edition.sheet == "TG263 v20170815"
    assert edition.url == (
        "https://www.aapm.org/pubs/reports/RPT_263_Supplemental/"
        "TG263_Nomenclature_Worksheet_20170815.xls"
    )
    assert edition.file == "TG263_Nomenclature_Worksheet_20170815.xls"
    assert edition.sha256 == (
        "5ff0b9e2ebf578793f6fa8f59c2357b3feb61fdc0f87171e9103a0495d93d150"
    )
    assert edition.content_sha256 == (
        "0a0eaeacf147bdf654e0090b3e12b005d76985e6adc95441d7563365ac6e7ffc"
    )
    assert tg263_published.PAGE_URL == (
        "https://www.aapm.org/pubs/reports/RPT_263_Supplemental/"
    )


@pytest.mark.slow
def test_the_published_edition_matches_its_pins():
    # Downloads AAPM's file, so that a change to the converter that would
    # change the entries digest, and so stop every download being accepted,
    # fails here.
    nomenclature = tg263_published.load()
    assert nomenclature.source.sheet == "TG263 v20170815"
    assert len(nomenclature.structures) == 717


@pytest.mark.parametrize("field", ["sha256", "content_sha256"])
def test_an_edition_needs_lowercase_hex_digests(field):
    with pytest.raises(ValueError, match=field):
        dataclasses.replace(EDITION, **{field: EDITION.sha256.upper()})


def test_an_edition_needs_an_https_url_naming_a_file():
    for url in ("http://example.invalid/a.xls", "https://example.invalid/"):
        with pytest.raises(ValueError, match="url"):
            dataclasses.replace(EDITION, url=url)


def test_the_spreadsheet_is_downloaded_once_and_cached(data_dir):
    download = _Downloader()

    first = tg263_published.spreadsheet_path(EDITION, download=download)
    second = tg263_published.spreadsheet_path(EDITION, download=download)

    assert first == second == data_dir / "tg263" / "TG263_Invented_20260101.xls"
    assert first.read_bytes() == SPREADSHEET.read_bytes()
    assert download.urls == [URL]


def test_a_cached_copy_that_does_not_match_the_pin_is_downloaded_again(data_dir):
    cached = data_dir / "tg263" / "TG263_Invented_20260101.xls"
    cached.parent.mkdir()
    cached.write_bytes(b"truncated")
    download = _Downloader()

    path = tg263_published.spreadsheet_path(EDITION, download=download)

    assert path.read_bytes() == SPREADSHEET.read_bytes()
    assert download.urls == [URL]


def test_a_failed_download_leaves_no_file_behind(data_dir):
    def broken(_url, filepath):
        pathlib.Path(filepath).write_bytes(b"partial")
        raise OSError("connection reset")

    with pytest.raises(OSError, match="connection reset"):
        tg263_published.spreadsheet_path(EDITION, download=broken)

    assert not _cached_files(data_dir)


def test_a_download_that_does_not_match_the_pin_is_refused_and_removed(data_dir):
    download = _Downloader(content=b"not the published file")
    expected = re.escape(f"does not have the pinned SHA-256 {EDITION.sha256}")

    with pytest.raises(tg263.TG263Error, match=expected) as error:
        tg263_published.spreadsheet_path(EDITION, download=download)

    assert URL in str(error.value)
    assert not _cached_files(data_dir)


def test_load_returns_the_pinned_edition(data_dir):
    nomenclature = tg263_published.load(EDITION, download=_Downloader())
    assert nomenclature == tg263.read_spreadsheet(
        data_dir / "tg263" / "TG263_Invented_20260101.xls"
    )


@pytest.mark.parametrize(
    "change, message",
    [
        ({"sheet": "TG263 vOther"}, "worksheet"),
        ({"content_sha256": "0" * 64}, "entries"),
    ],
)
@pytest.mark.usefixtures("data_dir")
def test_load_refuses_a_spreadsheet_whose_contents_differ_from_the_pin(change, message):
    # The file's digest matches, so these guard against a pin recorded wrongly.
    edition = dataclasses.replace(EDITION, **change)
    with pytest.raises(tg263.TG263Error, match=message):
        tg263_published.load(edition, download=_Downloader())


@pytest.mark.usefixtures("data_dir")
def test_the_default_is_the_published_edition(monkeypatch):
    # Stand the invented edition in for the published one, so nothing is
    # downloaded from AAPM.
    monkeypatch.setattr(tg263_published, "PUBLISHED", EDITION)
    download = _Downloader()

    nomenclature = tg263_published.load(download=download)

    assert nomenclature.structures == tg263.read_spreadsheet(SPREADSHEET).structures
    assert download.urls == [URL]


@pytest.mark.usefixtures("data_dir")
def test_a_local_copy_is_used_without_downloading(tmp_path):
    local = tmp_path / "copy" / EDITION.file
    local.parent.mkdir()
    shutil.copyfile(SPREADSHEET, local)
    download = _Downloader()

    nomenclature = tg263_published.load(EDITION, spreadsheet=local, download=download)

    assert nomenclature == tg263.read_spreadsheet(local)
    assert not download.urls


def test_a_local_copy_that_is_not_the_pinned_edition_is_refused(tmp_path):
    local = tmp_path / "TG263_Invented_20260101.xls"
    local.write_bytes(b"edited")
    with pytest.raises(tg263.TG263Error, match="pinned SHA-256"):
        tg263_published.load(EDITION, spreadsheet=local, download=_Downloader())


@pytest.mark.usefixtures("data_dir")
def test_the_bytes_that_were_read_are_the_ones_checked(monkeypatch):
    # The file is replaced between the SHA-256 check and the read.
    real_read = tg263.read_spreadsheet

    def read_replaced(path):
        nomenclature = real_read(path)
        source = dataclasses.replace(nomenclature.source, sha256="1" * 64)
        return dataclasses.replace(nomenclature, source=source)

    monkeypatch.setattr(tg263, "read_spreadsheet", read_replaced)
    with pytest.raises(tg263.TG263Error, match="changed while it was read"):
        tg263_published.load(EDITION, download=_Downloader())
