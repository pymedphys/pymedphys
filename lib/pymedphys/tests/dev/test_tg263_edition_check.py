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

"""``pymedphys dev tg263-check``: has AAPM published a new TG-263 edition?

No test here reaches the network. The page and the spreadsheet are invented,
and are served by a stand-in for the downloader.
"""

import hashlib
import http.client
import json
import urllib.error

from pymedphys._imports import pytest

from pymedphys._dev import tg263_edition_check as check
from pymedphys._nomenclature import tg263_published
from pymedphys.cli import define_parser

PAGE_URL = "https://example.invalid/reports/TG263/"
SPREADSHEET = b"the invented spreadsheet"
EDITION = tg263_published.Edition(
    sheet="TG263 v20260101",
    url=PAGE_URL + "TG263_Invented_20260101.xls",
    sha256=hashlib.sha256(SPREADSHEET).hexdigest(),
    content_sha256="0" * 64,
)


def _page(*hrefs):
    links = "".join(f'<li><a href="{href}">Spreadsheet</a></li>' for href in hrefs)
    return (
        "<html><head><title>Nomenclature</title></head><body>"
        '<a href="/pubs/default.asp">Publications</a>'
        '<a href="TG263_Report.pdf">Report</a>'
        f"<ul>{links}</ul></body></html>"
    ).encode("utf-8")


PAGE = _page("TG263_Invented_20260101.xls")


def _fetcher(page=PAGE, spreadsheet=SPREADSHEET, errors=None):
    errors = errors or {}
    served = {PAGE_URL: page, EDITION.url: spreadsheet}

    def fetch(url):
        if url in errors:
            raise errors[url]
        return served[url]

    return fetch


def _check(**kwargs):
    return check.check_current(EDITION, PAGE_URL, _fetcher(**kwargs))


def test_the_pinned_edition_alone_is_unchanged():
    result = _check()

    assert result.status == "unchanged"
    assert result.linked == (EDITION.url,)
    assert result.current_sha256 == EDITION.sha256
    assert check.report_lines(result) == [
        f"Pinned edition: {EDITION.sheet}, {EDITION.url}",
        f"Spreadsheets linked from {PAGE_URL}:",
        f"  {EDITION.url}",
        "Result: unchanged",
    ]


def test_a_spreadsheet_other_than_the_pinned_one_is_a_change():
    page = _page("TG263_Invented_20260101.xls", "TG263_Invented_20270101.xlsx")

    result = _check(page=page)

    assert result.status == "changed"
    assert check.report_lines(result)[-3:] == [
        "Spreadsheets other than the pinned one:",
        f"  {PAGE_URL}TG263_Invented_20270101.xlsx",
        "Result: changed",
    ]


def test_a_page_that_no_longer_links_the_pinned_spreadsheet_is_a_change():
    result = _check(page=_page("TG263_Invented_20270101.xls"))

    assert result.status == "changed"
    assert "The page no longer links to the pinned spreadsheet." in (
        check.report_lines(result)
    )


def test_a_pinned_file_whose_bytes_change_is_a_change():
    result = _check(spreadsheet=b"a corrected spreadsheet")

    assert result.status == "changed"
    assert (
        result.current_sha256 == hashlib.sha256(b"a corrected spreadsheet").hexdigest()
    )
    assert (
        f"The pinned spreadsheet's SHA-256 is now {result.current_sha256}, "
        f"not {EDITION.sha256}." in check.report_lines(result)
    )


@pytest.mark.parametrize(
    "href",
    [
        "TG263_Invented_20260101.xls",
        "./TG263_Invented_20260101.xls",
        "/reports/TG263/TG263_Invented_20260101.xls",
        "https://example.invalid/reports/TG263/TG263_Invented_20260101.xls",
        "TG263_Invented_20260101.xls#sheet",
    ],
)
def test_links_are_resolved_against_the_page(href):
    assert _check(page=_page(href)).linked == (EDITION.url,)


@pytest.mark.parametrize(
    "href", ["Worksheet.XLS", "Worksheet.xlsx", "Worksheet.xls?download=1"]
)
def test_spreadsheet_links_are_recognised_by_their_extension(href):
    result = _check(page=_page("TG263_Invented_20260101.xls", href))
    assert len(result.linked) == 2


def test_each_link_is_listed_once_and_sorted():
    names = ["2029", "2026", "2028", "2027", "2029", "2025"]
    page = _page(*(f"TG263_Invented_{name}0101.xls" for name in names))
    assert _check(page=page).linked == tuple(
        f"{PAGE_URL}TG263_Invented_{name}0101.xls"
        for name in ["2025", "2026", "2027", "2028", "2029"]
    )


def test_an_href_on_any_element_is_read_and_an_empty_one_ignored():
    page = PAGE.replace(b"</body>", b'<a href>Empty</a><link href="Other.xls"></body>')
    assert _check(page=page).linked == (PAGE_URL + "Other.xls", EDITION.url)


def test_a_page_without_spreadsheet_links_fails():
    # AAPM moved or rebuilt the page, so the check can no longer see editions.
    result = _check(page=_page())

    assert result.status == "failed"
    assert "The page links to no spreadsheet." in check.report_lines(result)


@pytest.mark.parametrize(
    "error, reported",
    [
        (urllib.error.HTTPError(PAGE_URL, 404, "Not Found", None, None), "HTTP 404"),
        (urllib.error.URLError("no route"), "URLError"),
        (TimeoutError(), "TimeoutError"),
        (http.client.IncompleteRead(b""), "IncompleteRead"),
    ],
)
def test_a_page_that_cannot_be_fetched_fails(error, reported):
    result = _check(errors={PAGE_URL: error})

    assert result.status == "failed"
    assert result.page_error == reported
    assert f"Could not fetch {PAGE_URL} ({reported})." in check.report_lines(result)


def test_a_pinned_file_that_cannot_be_fetched_fails_even_with_a_new_link():
    page = _page("TG263_Invented_20260101.xls", "TG263_Invented_20270101.xls")
    error = urllib.error.HTTPError(EDITION.url, 503, "Unavailable", None, None)

    result = _check(page=page, errors={EDITION.url: error})

    assert result.status == "failed"
    assert result.current_sha256 is None
    assert f"Could not fetch {EDITION.url} (HTTP 503)." in check.report_lines(result)
    assert f"  {PAGE_URL}TG263_Invented_20270101.xls" in check.report_lines(result)


def test_the_report_never_quotes_the_page():
    page = _page("TG263_Invented_20260101.xls").replace(
        b"Nomenclature", b"Quoted page text"
    )
    result = _check(page=page, spreadsheet=b"changed")
    report = "\n".join(check.report_lines(result))
    assert "Quoted page text" not in report


def test_run_writes_json_and_returns_the_exit_status(tmp_path, capsys):
    json_path = tmp_path / "check.json"

    status = check.run(
        EDITION,
        PAGE_URL,
        json_path=json_path,
        fetch=_fetcher(page=_page("TG263_Invented_20270101.xls")),
    )

    assert status == 1
    document = json.loads(json_path.read_text(encoding="utf-8"))
    assert document["status"] == "changed"
    assert document["linked"] == [PAGE_URL + "TG263_Invented_20270101.xls"]
    assert capsys.readouterr().out.endswith("Result: changed\n")


@pytest.mark.parametrize(
    "kwargs, status",
    [
        ({}, 0),
        ({"spreadsheet": b"changed"}, 1),
        ({"errors": {PAGE_URL: TimeoutError()}}, 3),
    ],
)
def test_exit_statuses(kwargs, status):
    assert check.run(EDITION, PAGE_URL, fetch=_fetcher(**kwargs)) == status


def test_the_command_checks_the_published_edition(monkeypatch, tmp_path):
    fetched = []

    def fetch(url):
        fetched.append(url)
        return {PAGE_URL: PAGE, EDITION.url: SPREADSHEET}[url]

    monkeypatch.setattr(check, "download", fetch)
    monkeypatch.setattr(tg263_published, "PUBLISHED", EDITION)
    monkeypatch.setattr(tg263_published, "PAGE_URL", PAGE_URL)
    json_path = tmp_path / "check.json"

    args = define_parser().parse_args(["dev", "tg263-check", "--json", str(json_path)])
    args.func(args)

    assert fetched == [PAGE_URL, EDITION.url]
    assert json.loads(json_path.read_text(encoding="utf-8"))["status"] == "unchanged"


def test_the_command_exits_with_the_status(monkeypatch):
    monkeypatch.setattr(check, "download", _fetcher(spreadsheet=b"changed"))
    monkeypatch.setattr(tg263_published, "PUBLISHED", EDITION)
    monkeypatch.setattr(tg263_published, "PAGE_URL", PAGE_URL)

    args = define_parser().parse_args(["dev", "tg263-check"])
    with pytest.raises(SystemExit) as exit_info:
        args.func(args)

    assert exit_info.value.code == 1
