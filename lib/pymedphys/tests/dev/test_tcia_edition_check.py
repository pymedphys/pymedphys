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

"""``pymedphys dev tcia-check``: is the shipped dictionary still TCIA's?

No test here reaches the network. The page and the file are invented, and
are served by a stand-in for the downloader.
"""

import hashlib
import http.client
import json
import urllib.error

from pymedphys._imports import pytest

from pymedphys._dev import tcia_edition_check as check
from pymedphys._dicom.deidentify import tcia_private_tags
from pymedphys.cli import define_parser

PAGE_URL = "https://example.invalid/de-identification/"
FILES_URL = "https://files.example.invalid/attachments/"
DICTIONARY = b"element_sig_pattern,tag_name,vr,private_disposition\r\n"
PIN = tcia_private_tags.Pin(
    file_name="TCIAPrivateTagKB-01-01-2026-formatted.csv",
    url=FILES_URL + "TCIAPrivateTagKB-01-01-2026-formatted.csv?version=1",
    page_url=PAGE_URL,
    sha256=hashlib.sha256(DICTIONARY).hexdigest(),
    size=len(DICTIONARY),
    retrieved="2026-01-02",
)
LICENCE = '<a href="https://creativecommons.org/licenses/by/3.0/">Site Licence</a>'


def _page(*hrefs, licence=LICENCE):
    links = "".join(f'<li><a href="{href}">Dictionary</a></li>' for href in hrefs)
    return (
        "<html><head><title>De-identification</title></head><body>"
        '<a href="/about/">About</a>'
        '<a href="https://files.example.invalid/attachments/Overview.pdf">PDF</a>'
        f"<ul>{links}</ul><footer>{licence}</footer></body></html>"
    ).encode("utf-8")


PAGE = _page(PIN.url)


def _fetcher(page=PAGE, dictionary=DICTIONARY, errors=None):
    errors = errors or {}
    served = {PAGE_URL: page, PIN.url: dictionary}

    def fetch(url):
        if url in errors:
            raise errors[url]
        return served[url]

    return fetch


def _check(shipped=DICTIONARY, reviewed=(), **kwargs):
    return check.check_current(PIN, _fetcher(**kwargs), shipped, reviewed)


def test_the_pinned_edition_alone_under_its_licence_is_unchanged():
    result = _check()

    assert result.status == "unchanged"
    assert result.linked == (PIN.url,)
    assert result.licence_linked
    assert (result.current_sha256, result.current_size) == (PIN.sha256, PIN.size)
    assert check.report_lines(result) == [
        f"Pinned file: {PIN.url}",
        f"Editions linked from {PAGE_URL}:",
        f"  {PIN.url}",
        "Result: unchanged",
    ]


def test_an_edition_that_has_not_been_reviewed_is_a_change():
    newer = FILES_URL + "TCIAPrivateTagKB-07-01-2026-formatted.csv"

    result = _check(page=_page(PIN.url, newer))

    assert result.status == "changed"
    assert check.report_lines(result)[-3:] == [
        "Editions not yet reviewed:",
        f"  {newer}",
        "Result: changed",
    ]


def test_a_reviewed_edition_is_not_a_change():
    older = FILES_URL + "TCIAPrivateTagKB-02-01-2024-formatted.csv"

    result = _check(
        page=_page(older, PIN.url), reviewed=[older.upper()[:8] + older[8:]]
    )

    assert result.status == "unchanged"
    assert result.reviewed == (older,)


def test_a_page_that_no_longer_links_the_pinned_file_is_a_change():
    newer = FILES_URL + "TCIAPrivateTagKB-07-01-2026-formatted.csv"

    result = _check(page=_page(newer))

    assert result.status == "changed"
    assert "The page no longer links to the pinned file." in check.report_lines(result)


def test_a_page_that_no_longer_links_the_licence_is_a_change():
    result = _check(page=_page(PIN.url, licence="<p>All rights reserved.</p>"))

    assert result.status == "changed"
    assert not result.licence_linked
    assert f"The page no longer links to {check.LICENCE_URL}." in check.report_lines(
        result
    )


@pytest.mark.parametrize(
    "dictionary", [DICTIONARY + b"(0019,X,01),Y,DS,k", DICTIONARY[:-2]]
)
def test_a_pinned_file_whose_bytes_change_is_a_change(dictionary):
    result = _check(dictionary=dictionary)

    assert result.status == "changed"
    assert result.current_sha256 == hashlib.sha256(dictionary).hexdigest()
    assert (
        f"The pinned file is now {len(dictionary)} bytes with SHA-256 "
        f"{result.current_sha256}, not {PIN.size} bytes with {PIN.sha256}."
        in check.report_lines(result)
    )


def test_a_shipped_copy_that_differs_from_the_pin_is_a_change():
    result = _check(shipped=DICTIONARY + b"\r\n")

    assert result.status == "changed"
    assert not result.shipped_matches
    assert (
        "The shipped copy does not have the pinned length and SHA-256."
        in check.report_lines(result)
    )


def test_links_that_are_not_editions_are_not_listed():
    page = _page(PIN.url, "Overview.pdf", "/other/Dictionary.csv", "Next/")
    assert _check(page=page).linked == (PIN.url,)


@pytest.mark.parametrize(
    "href",
    [
        "http://FILES.example.invalid/attachments/"
        "TCIAPrivateTagKB-01-01-2026-formatted.csv?version=1",
        PIN.url + "#download",
    ],
)
def test_the_pinned_link_matches_whatever_its_scheme_host_case_or_fragment(href):
    result = _check(page=_page(href))
    assert result.linked == (PIN.url,)
    assert result.status == "unchanged"


def test_an_edition_is_recognised_by_its_name_in_any_case():
    lower = FILES_URL + "tciaprivatetagkb-2027.zip"
    assert _check(page=_page(PIN.url, lower)).unreviewed == (lower,)


def test_a_page_without_an_edition_fails():
    # TCIA moved or rebuilt the page, so the check can no longer see editions.
    result = _check(page=_page())

    assert result.status == "failed"
    assert "The page links to no edition of the dictionary." in (
        check.report_lines(result)
    )


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


def test_a_pinned_file_that_cannot_be_fetched_fails_even_with_a_new_edition():
    newer = FILES_URL + "TCIAPrivateTagKB-07-01-2026-formatted.csv"
    error = urllib.error.HTTPError(PIN.url, 503, "Unavailable", None, None)

    result = _check(page=_page(PIN.url, newer), errors={PIN.url: error})

    assert result.status == "failed"
    assert result.current_sha256 is None
    lines = check.report_lines(result)
    assert f"Could not fetch {PIN.url} (HTTP 503)." in lines
    assert f"  {newer}" in lines


@pytest.mark.parametrize("code", [404, 410])
def test_a_pinned_file_that_is_gone_is_a_change(code):
    error = urllib.error.HTTPError(PIN.url, code, "Gone", None, None)

    result = _check(errors={PIN.url: error})

    assert result.status == "changed"
    assert f"The pinned file is gone (HTTP {code})." in check.report_lines(result)


def test_the_report_never_quotes_the_page():
    page = _page(PIN.url).replace(b"De-identification", b"Quoted page text")
    report = "\n".join(check.report_lines(_check(page=page, dictionary=b"changed")))
    assert "Quoted page text" not in report


def test_report_urls_carry_no_control_characters():
    page = _page(PIN.url, FILES_URL + "TCIAPrivateTagKB\x1b[31m-2027.csv")
    report = "\n".join(check.report_lines(_check(page=page)))
    assert "\x1b" not in report
    assert "TCIAPrivateTagKB[31m-2027.csv" in report


def test_a_long_list_of_editions_is_cut_short():
    page = _page(*(f"TCIAPrivateTagKB-{number:03}.csv" for number in range(60)))
    lines = check.report_lines(_check(page=page))
    assert "  and 10 more" in lines


def test_run_writes_json_and_returns_the_exit_status(tmp_path, capsys):
    json_path = tmp_path / "check.json"

    status = check.run(
        PIN, DICTIONARY, json_path=json_path, fetch=_fetcher(dictionary=b"changed")
    )

    assert status == 1
    document = json.loads(json_path.read_text(encoding="utf-8"))
    assert document["status"] == "changed"
    assert document["linked"] == [PIN.url]
    assert capsys.readouterr().out.endswith("Result: changed\n")


@pytest.mark.parametrize(
    "kwargs, status",
    [
        ({}, 0),
        ({"dictionary": b"changed"}, 1),
        ({"errors": {PAGE_URL: TimeoutError()}}, 3),
    ],
)
def test_exit_statuses(kwargs, status):
    assert check.run(PIN, DICTIONARY, fetch=_fetcher(**kwargs)) == status


def test_the_command_checks_the_pinned_file_and_the_shipped_copy(monkeypatch, tmp_path):
    fetched = []

    def fetch(url):
        fetched.append(url)
        return {PAGE_URL: PAGE, PIN.url: DICTIONARY}[url]

    (tmp_path / PIN.file_name).write_bytes(DICTIONARY)
    monkeypatch.setattr(check, "download", fetch)
    monkeypatch.setattr(tcia_private_tags, "PIN", PIN)
    monkeypatch.setattr(tcia_private_tags, "TCIA_DIR", tmp_path)
    json_path = tmp_path / "check.json"

    args = define_parser().parse_args(["dev", "tcia-check", "--json", str(json_path)])
    args.func(args)

    assert fetched == [PAGE_URL, PIN.url]
    assert json.loads(json_path.read_text(encoding="utf-8"))["status"] == "unchanged"


def test_the_command_exits_with_the_status(monkeypatch, tmp_path):
    (tmp_path / PIN.file_name).write_bytes(b"an altered copy")
    monkeypatch.setattr(check, "download", _fetcher())
    monkeypatch.setattr(tcia_private_tags, "PIN", PIN)
    monkeypatch.setattr(tcia_private_tags, "TCIA_DIR", tmp_path)

    args = define_parser().parse_args(["dev", "tcia-check"])
    with pytest.raises(SystemExit) as exit_info:
        args.func(args)

    assert exit_info.value.code == 1


def test_no_other_edition_has_been_reviewed():
    assert check.REVIEWED == frozenset()
