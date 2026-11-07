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

# pylint: disable = too-many-lines

"""Tests of the MIDI-B downloader and its images' ZIP file (D-018).

Nothing here touches the network: every URL is served from memory, and every
manifest, archive, and file is made up for the tests.
"""

import hashlib
import io
import json
import os
import re
import urllib.error
import urllib.parse
import warnings
import zipfile

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import midi_download, midi_images
from pymedphys._dicom.deidentify.midi_download import DownloadError

MANIFEST_URL = "https://example.org/manifest.tcia"
KEY_URL = "https://example.org/answer-key.db"
IMAGES_URL = "https://example.org/images.zip"
SERIES = ("2.25.9001", "2.25.9002")
KEY = b"SQLite format 3\x00 synthetic answer key"


def _dicom(text: str) -> bytes:
    return b"\x00" * 128 + b"DICM" + text.encode("ascii")


def _archive(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zipped:
        for name, data in members.items():
            # A fixed date, so that the bytes, and the test IDs that hold
            # them, are the same in every pytest-xdist worker.
            zipped.writestr(
                zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0)), data
            )
    return buffer.getvalue()


def _manifest(series=SERIES) -> bytes:
    lines = [
        "downloadServerUrl=https://example.org/servlet",
        "manifestVersion=3.0",
        "ListOfSeriesToDownload=",
        *series,
    ]
    return ("\n".join(lines) + "\n").encode("ascii")


# File names inside the archives here hold UIDs, which NBIA's could, to show
# that none reaches a path or the record.
ARCHIVES = {
    SERIES[0]: _archive(
        {
            "2.25.9001.1.dcm": _dicom("first"),
            "2.25.9001.2.dcm": _dicom("second"),
            "LICENSE": b"not DICOM",
        }
    ),
    SERIES[1]: _archive({"2.25.9002.1.dcm": _dicom("third")}),
}
FILES = (_dicom("first"), _dicom("second"), _dicom("third"))


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _content() -> str:
    return midi_download.content_digest([_sha256(data) for data in FILES])


def _subset(**changes) -> midi_download.Subset:
    pins = {
        "key": "validation",
        "collection": "SYNTHETIC-COLLECTION",
        "name": "Synthetic collection",
        "manifest_url": MANIFEST_URL,
        "manifest_sha256": _sha256(_manifest()),
        "series": len(SERIES),
        "instances": len(FILES),
        "content_sha256": _content(),
        "images_url": "",
        "images_sha256": "",
        "answer_key_url": KEY_URL,
        "answer_key_sha256": _sha256(KEY),
    }
    pins.update(changes)
    return midi_download.Subset(**pins)


class Server:
    """Serves the made-up manifest, archives, answer key, and, if given, the
    images' ZIP file from memory."""

    def __init__(self, manifest=None, archives=None, failures=0, images=None):
        self.manifest = _manifest() if manifest is None else manifest
        self.archives = ARCHIVES if archives is None else archives
        self.failures = failures
        self.images = images
        self.requests: list[str] = []

    def __call__(self, url: str):
        self.requests.append(url)
        if self.failures:
            self.failures -= 1
            raise urllib.error.URLError(f"no route to {url}")
        if url == MANIFEST_URL:
            return io.BytesIO(self.manifest)
        if url == KEY_URL:
            return io.BytesIO(KEY)
        if url == IMAGES_URL:
            if self.images is None:
                raise urllib.error.HTTPError(url, 404, "not found", {}, None)
            return io.BytesIO(self.images)
        base, _, query = url.partition("?")
        assert base == midi_download.NBIA_IMAGES
        (uid,) = urllib.parse.parse_qs(query)["SeriesInstanceUID"]
        return io.BytesIO(self.archives[uid])


@pytest.fixture(name="no_sleep")
def _no_sleep(monkeypatch):
    waits = []
    monkeypatch.setattr(midi_download.time, "sleep", waits.append)
    return waits


def _all_text(directory) -> str:
    paths = sorted(directory.rglob("*"))
    return (
        "\n".join(str(path) for path in paths)
        + (directory / "download.json").read_text()
    )


def test_the_packaged_pins_name_both_subsets():
    subsets = midi_download.load_subsets()
    assert set(subsets) == {"validation", "test"}
    assert subsets["validation"].collection == "MIDI-B-Synthetic-Validation"
    assert (subsets["validation"].series, subsets["validation"].instances) == (
        280,
        23921,
    )
    assert subsets["test"].collection == "MIDI-B-Synthetic-Test"
    assert (subsets["test"].series, subsets["test"].instances) == (428, 29660)
    for subset in subsets.values():
        assert subset.manifest_url.startswith("https://www.cancerimagingarchive.net/")


def _pins(**changes) -> str:
    """A subset's entry in midi_data.toml, every pin empty unless changed."""
    pins = {
        "collection": "X",
        "name": "X",
        "manifest_url": "https://x",
        "manifest_sha256": "",
        "series": 1,
        "instances": 1,
        "content_sha256": "",
        "images_url": "",
        "images_sha256": "",
        "answer_key_url": "",
        "answer_key_sha256": "",
    }
    pins.update(changes)
    return "\n".join(
        f"{key} = {json.dumps(value)}"
        for key, value in pins.items()
        if value is not None
    )


def test_complete_pins_load():
    subset = midi_download.load_subsets(f"[subset]\n{_pins()}\n")["subset"]
    assert (subset.key, subset.images_url, subset.images_sha256) == ("subset", "", "")


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"images_url": None}, "incomplete"),
        ({"manifest_url": "http://x"}, "not HTTPS"),
        ({"images_url": "http://x", "images_sha256": "a" * 64}, "not HTTPS"),
        ({"manifest_sha256": "ABC"}, "malformed"),
        ({"images_sha256": "a" * 63}, "malformed"),
        ({"images_url": "https://x"}, "has no SHA-256"),
        ({"answer_key_url": "https://x"}, "has no SHA-256"),
        ({"collection": "../X"}, "not a plain name"),
        ({"collection": "X Y"}, "not a plain name"),
    ],
)
def test_malformed_pins_are_refused(changes, message):
    with pytest.raises(DownloadError, match=message):
        midi_download.load_subsets(f"[subset]\n{_pins(**changes)}\n")


def test_a_manifest_lists_its_series_in_order():
    assert midi_download.parse_manifest(_manifest().decode()) == SERIES


@pytest.mark.parametrize(
    "text, message",
    [
        ("manifestVersion=3.0\n", "no list of series"),
        ("ListOfSeriesToDownload=\n\n", "lists no series"),
        ("ListOfSeriesToDownload=\n2.25.1\nnot a uid\n", "not a UID"),
        ("ListOfSeriesToDownload=\n2.25.1\n2.25.1\n", "twice"),
    ],
)
def test_malformed_manifests_are_refused(text, message):
    with pytest.raises(DownloadError, match=message):
        midi_download.parse_manifest(text)


def test_a_download_writes_files_by_position_and_records_no_value(tmp_path):
    destination = tmp_path / "midi"
    record = midi_download.download(_subset(), destination, opener=Server(), workers=2)

    files = sorted(
        path.relative_to(destination / "images").as_posix()
        for path in (destination / "images").rglob("*.dcm")
    )
    assert files == ["0001/00001.dcm", "0001/00002.dcm", "0002/00001.dcm"]
    assert (destination / "images" / "0001" / "00002.dcm").read_bytes() == FILES[1]
    assert (destination / "answer-key.db").read_bytes() == KEY
    assert record == json.loads((destination / "download.json").read_text())
    assert record["files"] == 3
    assert record["series"] == 2
    assert record["images"] == {"source": "tcia"}
    assert record["skipped_members_not_dicom"] == 1
    assert record["bytes"] == sum(len(data) for data in FILES)
    assert record["content"] == {"sha256": _content(), "pin": "matched"}
    assert record["manifest"]["pin"] == "matched"
    assert record["answer_key"] == {
        "source": "pinned",
        "sha256": _sha256(KEY),
        "pin": "matched",
        "database_sha256": _sha256(KEY),
    }
    # Only the images, the answer key, and the record remain.
    assert sorted(path.name for path in destination.iterdir()) == [
        "answer-key.db",
        "download.json",
        "images",
    ]
    assert "2.25.900" not in _all_text(destination)


def test_unpinned_digests_are_recorded_as_not_pinned(tmp_path):
    subset = _subset(
        manifest_sha256="", content_sha256="", answer_key_url="", answer_key_sha256=""
    )
    record = midi_download.download(subset, tmp_path / "midi", opener=Server())
    assert record["manifest"]["pin"] == "not pinned"
    assert record["content"] == {"sha256": _content(), "pin": "not pinned"}
    assert record["answer_key"] is None
    assert not (tmp_path / "midi" / "answer-key.db").exists()


@pytest.mark.parametrize(
    "changes, server, message",
    [
        ({"manifest_sha256": "0" * 64}, {}, "manifest's SHA-256"),
        ({"content_sha256": "0" * 64}, {}, "image set's SHA-256"),
        ({"answer_key_sha256": "0" * 64}, {}, "answer key's SHA-256"),
        ({"series": 3}, {}, "lists 2 series, not the expected 3"),
        ({"instances": 4}, {}, "3 DICOM files, not the expected 4"),
        (
            {"manifest_sha256": ""},
            {"archives": {SERIES[0]: b"not a zip", SERIES[1]: ARCHIVES[SERIES[1]]}},
            "not a readable ZIP",
        ),
        (
            {"manifest_sha256": ""},
            {
                "archives": {
                    SERIES[0]: _archive({"x": b"text"}),
                    SERIES[1]: ARCHIVES[SERIES[1]],
                }
            },
            "holds no DICOM file",
        ),
    ],
)
@pytest.mark.usefixtures("no_sleep")
def test_mismatches_are_refused_without_quoting_a_uid(
    tmp_path, changes, server, message
):
    with pytest.raises(DownloadError, match=message) as raised:
        midi_download.download(
            _subset(**changes), tmp_path / "midi", opener=Server(**server)
        )
    assert "2.25.900" not in str(raised.value)


def test_a_failed_fetch_is_retried(tmp_path, no_sleep):
    server = Server(failures=midi_download.ATTEMPTS - 1)
    midi_download.download(_subset(), tmp_path / "midi", opener=server, workers=1)
    assert no_sleep == list(midi_download.WAITS)


def test_each_retry_is_reported_with_its_time_and_no_url(tmp_path, no_sleep):
    class Flaky(Server):
        series_failed = False

        def __call__(self, url):
            if SERIES[1] in url and not self.series_failed:
                self.series_failed = True
                raise urllib.error.HTTPError(url, 503, "busy", {}, None)
            return super().__call__(url)

    lines: list[str] = []
    midi_download.download(
        _subset(answer_key_url="", answer_key_sha256=""),
        tmp_path / "midi",
        opener=Flaky(failures=1),
        workers=1,
        progress=lines.append,
    )
    stamp = r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ"
    assert [re.sub(stamp, "<time>", line) for line in lines if "failed" in line] == [
        "Fetching the manifest: attempt 1 of 6 failed at <time> (URLError); "
        "trying again in 10 s",
        "Fetching the series 2 of 2: attempt 1 of 6 failed at <time> "
        "(HTTPError 503); trying again in 10 s",
    ]
    assert len(no_sleep) == 2
    assert not any("example" in line or "2.25.900" in line for line in lines)


def test_a_fetch_that_keeps_failing_names_no_url(tmp_path, no_sleep):
    with pytest.raises(DownloadError) as raised:
        midi_download.download(
            _subset(answer_key_url="", answer_key_sha256=""),
            tmp_path / "midi",
            opener=Server(failures=99),
            workers=1,
        )
    assert str(raised.value) == (
        "the manifest could not be fetched after 6 attempts (URLError)"
    )
    assert len(no_sleep) == midi_download.ATTEMPTS - 1


@pytest.mark.usefixtures("no_sleep")
def test_a_series_that_keeps_failing_names_only_its_position(tmp_path):
    class Failing(Server):
        def __call__(self, url):
            if SERIES[1] in url:
                raise urllib.error.HTTPError(url, 500, "error", {}, None)
            return super().__call__(url)

    with pytest.raises(DownloadError) as raised:
        midi_download.download(
            _subset(), tmp_path / "midi", opener=Failing(), workers=1
        )
    assert str(raised.value) == (
        "the series 2 of 2 could not be fetched after 6 attempts (HTTPError 500)"
    )


def _corrupt_second_member() -> bytes:
    """The first series' archive, its second DICOM member failing its CRC."""
    data = _archive(
        {"2.25.9001.1.dcm": _dicom("first"), "2.25.9001.2.dcm": _dicom("second")}
    )
    at = data.index(b"DICMsecond") + len(b"DICMsec")
    return data[:at] + b"0" + data[at + 1 :]


@pytest.mark.parametrize(
    "broken, failure",
    [
        (_archive({"LICENSE": b"not DICOM"}), "its archive holds no DICOM file"),
        (b"not a zip", "its archive is not a readable ZIP file: BadZipFile"),
        (
            _corrupt_second_member(),
            "its archive is not a readable ZIP file: BadZipFile",
        ),
    ],
)
def test_an_unusable_archive_is_fetched_again(tmp_path, no_sleep, broken, failure):
    class OnceBroken(Server):
        served_broken = False

        def __call__(self, url):
            if SERIES[0] in url and not self.served_broken:
                self.served_broken = True
                self.requests.append(url)
                return io.BytesIO(broken)
            return super().__call__(url)

    lines: list[str] = []
    record = midi_download.download(
        _subset(),
        tmp_path / "midi",
        opener=OnceBroken(),
        workers=1,
        progress=lines.append,
    )
    stamp = r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ"
    assert [re.sub(stamp, "<time>", line) for line in lines if "failed" in line] == [
        f"Fetching the series 1 of 2: attempt 1 of 6 failed at <time> ({failure}); "
        "trying again in 10 s"
    ]
    assert no_sleep == [midi_download.WAITS[0]]
    assert record["content"] == {"sha256": _content(), "pin": "matched"}
    first = tmp_path / "midi" / "images" / "0001"
    assert sorted(path.name for path in first.iterdir()) == ["00001.dcm", "00002.dcm"]
    assert [path.read_bytes() for path in sorted(first.iterdir())] == list(FILES[:2])
    assert not any("2.25.900" in line for line in lines)


def test_an_existing_destination_is_refused(tmp_path):
    with pytest.raises(DownloadError, match="must not exist"):
        midi_download.download(_subset(), tmp_path, opener=Server())


def test_a_given_answer_key_needs_its_digest(tmp_path):
    with pytest.raises(DownloadError, match="needs its SHA-256"):
        midi_download.download(
            _subset(), tmp_path / "midi", opener=Server(), answer_key_url=KEY_URL
        )


def test_a_given_answer_key_replaces_the_pinned_one(tmp_path):
    record = midi_download.download(
        _subset(answer_key_url="", answer_key_sha256=""),
        tmp_path / "midi",
        opener=Server(),
        answer_key_url=KEY_URL,
        answer_key_sha256=_sha256(KEY),
    )
    assert record["answer_key"]["source"] == "given"


def test_the_command_prints_the_record(tmp_path, monkeypatch, capsys):
    original = midi_download.download

    def download(*args, **kwargs):
        return original(*args, **{**kwargs, "opener": Server()})

    monkeypatch.setattr(midi_download, "download", download)
    assert (
        midi_download.main(
            ["--subset", "validation", "--dest", str(tmp_path / "midi")],
            subsets={"validation": _subset()},
        )
        == 0
    )
    printed = capsys.readouterr()
    assert json.loads(printed.out)["files"] == 3
    assert "of 2 series" in printed.err


def test_a_user_agent_note_is_a_checked_comment():
    assert midi_download.user_agent() == "pymedphys-midi-download"
    assert midi_download.user_agent("runner 2001:db8::1; run 7/2; test basic") == (
        "pymedphys-midi-download (runner 2001:db8::1; run 7/2; test basic)"
    )
    for note in ("", "a)b", "(a", "a\\b", "a\r\nX-Injected: 1", "a" * 201):
        with pytest.raises(DownloadError, match="user agent note"):
            midi_download.user_agent(note)


def test_the_command_sends_its_note_in_each_request(tmp_path, monkeypatch):
    server = Server()
    agents = []

    def urlopen(request, timeout):
        assert timeout == midi_download.TIMEOUT_SECONDS
        agents.append(request.get_header("User-agent"))
        return server(request.full_url)

    monkeypatch.setattr(midi_download.urllib.request, "urlopen", urlopen)
    note = "runner 192.0.2.1; run 7/1; validation basic"
    assert (
        midi_download.main(
            [
                "--subset",
                "validation",
                "--dest",
                str(tmp_path / "midi"),
                "--user-agent-note",
                note,
            ],
            subsets={"validation": _subset()},
        )
        == 0
    )
    # The answer key, the manifest, and both series.
    assert len(agents) == len(server.requests) == 4
    assert set(agents) == {f"pymedphys-midi-download ({note})"}


def test_the_command_refuses_a_note_that_is_not_a_comment(tmp_path):
    with pytest.raises(SystemExit, match="user agent note"):
        midi_download.main(
            [
                "--subset",
                "validation",
                "--dest",
                str(tmp_path / "midi"),
                "--user-agent-note",
                "a) b",
            ],
            subsets={"validation": _subset()},
        )
    assert not (tmp_path / "midi").exists()


def test_the_command_refuses_without_a_traceback(tmp_path):
    with pytest.raises(SystemExit, match="must not exist"):
        midi_download.main(
            ["--subset", "validation", "--dest", str(tmp_path)],
            subsets={"validation": _subset()},
        )


def test_a_copy_however_fetched_verifies_against_the_pins(tmp_path):
    # Folder names and file names as another tool might write them, with a
    # non-DICOM file among them.
    for index, data in enumerate(FILES):
        folder = tmp_path / "copy" / f"collection-{index % 2}" / "series"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"1-{index:03d}.dcm").write_bytes(data)
    (tmp_path / "copy" / "LICENSE").write_text("not DICOM")
    record = midi_download.verify(_subset(), tmp_path / "copy")
    assert record["files"] == record["expected_files"] == 3
    assert record["skipped_files_not_dicom"] == 1
    assert record["content"] == {"sha256": _content(), "pin": "matched"}
    assert "collection-" not in json.dumps(record)


def test_a_copy_that_differs_is_reported(tmp_path, capsys):
    (tmp_path / "copy").mkdir()
    (tmp_path / "copy" / "a.dcm").write_bytes(FILES[0])
    subsets = {"validation": _subset()}
    status = midi_download.main(
        ["--subset", "validation", "--verify", str(tmp_path / "copy")],
        subsets=subsets,
    )
    record = json.loads(capsys.readouterr().out)
    assert status == 1
    assert record["files"] == 1
    assert record["content"]["pin"] == "differs"


def test_a_complete_copy_verifies_from_the_command(tmp_path, capsys):
    midi_download.download(_subset(), tmp_path / "midi", opener=Server())
    status = midi_download.main(
        ["--subset", "validation", "--verify", str(tmp_path / "midi" / "images")],
        subsets={"validation": _subset()},
    )
    assert status == 0
    assert json.loads(capsys.readouterr().out)["content"]["pin"] == "matched"


def test_verifying_needs_a_directory(tmp_path):
    with pytest.raises(SystemExit, match="not a directory"):
        midi_download.main(
            ["--subset", "validation", "--verify", str(tmp_path / "missing")],
            subsets={"validation": _subset()},
        )


def test_a_local_answer_key_is_checked_against_the_pin(tmp_path):
    key = tmp_path / "from-tcia.db"
    key.write_bytes(KEY)
    record = midi_download.download(
        _subset(answer_key_url=""),
        tmp_path / "midi",
        opener=Server(),
        answer_key_file=key,
    )
    assert record["answer_key"] == {
        "source": "file",
        "sha256": _sha256(KEY),
        "pin": "matched",
        "database_sha256": _sha256(KEY),
    }
    assert (tmp_path / "midi" / "answer-key.db").read_bytes() == KEY


def test_a_local_answer_key_that_differs_is_refused(tmp_path):
    key = tmp_path / "other.db"
    key.write_bytes(b"another key")
    with pytest.raises(DownloadError, match="answer key's SHA-256"):
        midi_download.download(
            _subset(), tmp_path / "midi", opener=Server(), answer_key_file=key
        )


def test_an_answer_key_by_url_and_by_file_is_refused(tmp_path):
    key = tmp_path / "key.db"
    key.write_bytes(KEY)
    with pytest.raises(DownloadError, match="not both"):
        midi_download.download(
            _subset(),
            tmp_path / "midi",
            opener=Server(),
            answer_key_url=KEY_URL,
            answer_key_sha256=_sha256(KEY),
            answer_key_file=key,
        )


@pytest.mark.parametrize(
    "data, status, pin", [(KEY, 0, "matched"), (b"x", 1, "differs")]
)
def test_verifying_checks_a_local_answer_key(tmp_path, capsys, data, status, pin):
    midi_download.download(_subset(), tmp_path / "midi", opener=Server())
    key = tmp_path / "key.db"
    key.write_bytes(data)
    returned = midi_download.main(
        [
            "--subset",
            "validation",
            "--verify",
            str(tmp_path / "midi" / "images"),
            "--answer-key-file",
            str(key),
        ],
        subsets={"validation": _subset()},
    )
    assert returned == status
    assert json.loads(capsys.readouterr().out)["answer_key"]["pin"] == pin


def test_a_zipped_answer_key_is_checked_as_zipped_and_unpacked(tmp_path):
    # As TCIA publishes it: one database in a ZIP file, beside other files.
    zipped = _archive({"key/README.txt": b"notes", "key/answer.db": KEY})
    key = tmp_path / "MIDI-B-Answer-Key-Validation.zip"
    key.write_bytes(zipped)
    record = midi_download.download(
        _subset(answer_key_url="", answer_key_sha256=_sha256(zipped)),
        tmp_path / "midi",
        opener=Server(),
        answer_key_file=key,
    )
    assert record["answer_key"] == {
        "source": "file",
        "sha256": _sha256(zipped),
        "pin": "matched",
        "database_sha256": _sha256(KEY),
    }
    assert (tmp_path / "midi" / "answer-key.db").read_bytes() == KEY
    assert "answer.db" not in _all_text(tmp_path / "midi")


@pytest.mark.parametrize(
    "data, message",
    [
        (b"neither", "neither an SQLite database nor a ZIP"),
        (_archive({"a.txt": b"text"}), "holds 0 SQLite databases, not one"),
        (_archive({"a.db": KEY, "b.db": KEY}), "holds 2 SQLite databases, not one"),
    ],
)
def test_an_answer_key_without_one_database_is_refused(tmp_path, data, message):
    key = tmp_path / "key"
    key.write_bytes(data)
    with pytest.raises(DownloadError, match=message):
        midi_download.download(
            _subset(answer_key_url="", answer_key_sha256=""),
            tmp_path / "midi",
            opener=Server(),
            answer_key_file=key,
        )


def test_a_wrong_answer_key_fails_before_the_images_download(tmp_path):
    server = Server()
    with pytest.raises(DownloadError, match="answer key's SHA-256"):
        midi_download.download(
            _subset(answer_key_sha256="0" * 64), tmp_path / "midi", opener=server
        )
    assert server.requests == [KEY_URL]


ROOT = "SYNTHETIC-COLLECTION"
DATE = (1980, 1, 1, 0, 0, 0)


def _downloaded(directory):
    """The made-up subset, downloaded from the made-up TCIA."""
    midi_download.download(_subset(), directory, opener=Server())
    return directory


def _packed(tmp_path, **changes) -> bytes:
    """The made-up subset's images, as pack writes them."""
    archive = tmp_path / "packed" / "images.zip"
    archive.parent.mkdir()
    midi_download.pack(
        _subset(**changes), _downloaded(tmp_path / "packed" / "midi"), archive
    )
    return archive.read_bytes()


def _tree(directory) -> dict[str, bytes]:
    images = directory / "images"
    return {
        path.relative_to(images).as_posix(): path.read_bytes()
        for path in sorted(images.rglob("*"))
        if path.is_file()
    }


def test_pack_writes_a_readme_and_the_files_by_position(tmp_path):
    archive = tmp_path / "images.zip"
    record = midi_download.pack(_subset(), _downloaded(tmp_path / "midi"), archive)

    with zipfile.ZipFile(archive) as zipped:
        infos = zipped.infolist()
        assert [info.filename for info in infos] == [
            f"{ROOT}/README.txt",
            f"{ROOT}/images/0001/00001.dcm",
            f"{ROOT}/images/0001/00002.dcm",
            f"{ROOT}/images/0002/00001.dcm",
        ]
        assert [zipped.read(info) for info in infos[1:]] == list(FILES)
        # The same attributes for every member, whatever the platform.
        for info in infos:
            assert info.compress_type == zipfile.ZIP_STORED
            assert info.date_time == DATE
            assert info.create_system == 3
            assert info.external_attr == 0o100644 << 16
            assert info.extra == b""
        readme = zipped.read(infos[0]).decode("ascii")
    assert "the 3 DICOM files of the 2 series that TCIA's manifest" in readme
    assert "manifest.tcia" in readme
    assert "https://doi.org/10.7937/cf2p-aw56" in readme
    assert midi_images.LICENCE in readme
    assert midi_images.POLICY in readme
    assert _content() in readme
    assert all(len(line) <= 76 or " " not in line for line in readme.splitlines())

    assert record == {
        "format": midi_download.PACK_FORMAT,
        "subset": "validation",
        "collection": ROOT,
        "series": 2,
        "files": 3,
        "bytes": sum(len(data) for data in FILES),
        "content": {"sha256": _content(), "pin": "matched"},
        "zip": {
            "name": "images.zip",
            "bytes": archive.stat().st_size,
            "sha256": _sha256(archive.read_bytes()),
            "pin": "not pinned",
        },
        "python": record["python"],
    }
    assert "2.25.900" not in json.dumps(record) + readme


def test_packing_gives_the_same_bytes_every_time(tmp_path):
    first = _packed(tmp_path)
    # Another download of the same files, packed later, with other times.
    again = _downloaded(tmp_path / "again")
    for path in (again / "images").rglob("*.dcm"):
        os.utime(path, (1_900_000_000, 1_900_000_000))
    archive = tmp_path / "again.zip"
    midi_download.pack(_subset(), again, archive)
    assert archive.read_bytes() == first


@pytest.mark.parametrize(
    "pin, status, returned", [("", "not pinned", 0), ("0" * 64, "differs", 1)]
)
def test_the_command_packs_and_compares_with_the_pin(
    tmp_path, capsys, pin, status, returned
):
    downloaded = _downloaded(tmp_path / "midi")
    archive = tmp_path / "images.zip"
    assert (
        midi_download.main(
            ["--subset", "validation", "--pack", str(downloaded), "--to", str(archive)],
            subsets={"validation": _subset(images_sha256=pin)},
        )
        == returned
    )
    assert json.loads(capsys.readouterr().out)["zip"]["pin"] == status


def test_a_zip_that_matches_its_pin_is_reported(tmp_path):
    packed = _packed(tmp_path)
    archive = tmp_path / "images.zip"
    record = midi_download.pack(
        _subset(images_sha256=_sha256(packed)), tmp_path / "packed" / "midi", archive
    )
    assert record["zip"]["pin"] == "matched"


def _rename(old, new):
    old.rename(new)


@pytest.mark.parametrize(
    "change, message",
    [
        (lambda images: (images / "LICENSE").write_text("x"), "only the series"),
        (
            lambda images: (images / "0001" / "notes.txt").write_text("x"),
            "series folder 1 must hold only",
        ),
        (
            lambda images: _rename(images / "0002", images / "0003"),
            "only the series folders",
        ),
        (
            lambda images: _rename(
                images / "0001" / "00002.dcm", images / "0001" / "00003.dcm"
            ),
            "series folder 1 must hold only",
        ),
        (
            lambda images: (images / "0002" / "00001.dcm").write_bytes(b"not DICOM"),
            "not a DICOM file",
        ),
        (
            lambda images: (images / "0002" / "00001.dcm").write_bytes(
                _dicom("changed")
            ),
            "image set's SHA-256",
        ),
    ],
)
def test_pack_refuses_what_a_download_would_not_hold(tmp_path, change, message):
    downloaded = _downloaded(tmp_path / "midi")
    change(downloaded / "images")
    with pytest.raises(DownloadError, match=message) as raised:
        midi_download.pack(_subset(), downloaded, tmp_path / "images.zip")
    # Neither the ZIP file nor a partial one is left behind.
    assert sorted(path.name for path in tmp_path.iterdir()) == ["midi"]
    assert "2.25.900" not in str(raised.value)


def test_pack_refuses_counts_that_differ_from_the_pins(tmp_path):
    downloaded = _downloaded(tmp_path / "midi")
    with pytest.raises(DownloadError, match="2 series and 3 files, not the expected"):
        midi_download.pack(_subset(instances=4), downloaded, tmp_path / "images.zip")


def test_pack_needs_a_pinned_content_digest_and_a_new_zip(tmp_path):
    downloaded = _downloaded(tmp_path / "midi")
    with pytest.raises(DownloadError, match="content_sha256 is pinned"):
        midi_download.pack(
            _subset(content_sha256=""), downloaded, tmp_path / "images.zip"
        )
    (tmp_path / "images.zip").write_bytes(b"")
    with pytest.raises(DownloadError, match="must not exist"):
        midi_download.pack(_subset(), downloaded, tmp_path / "images.zip")


def test_the_command_needs_pack_and_to_together(tmp_path, capsys):
    for arguments in (["--pack", str(tmp_path)], ["--dest", "x", "--to", "y.zip"]):
        with pytest.raises(SystemExit):
            midi_download.main(
                ["--subset", "validation", *arguments],
                subsets={"validation": _subset()},
            )
        assert "--pack and --to go together" in capsys.readouterr().err


def test_the_pinned_copy_replaces_tcia(tmp_path):
    packed = _packed(tmp_path)
    server = Server(images=packed)
    destination = tmp_path / "midi"
    record = midi_download.download(
        _subset(images_url=IMAGES_URL, images_sha256=_sha256(packed)),
        destination,
        opener=server,
    )
    # Neither TCIA's manifest nor NBIA is asked for anything.
    assert server.requests == [KEY_URL, IMAGES_URL]
    assert _tree(destination) == _tree(tmp_path / "packed" / "midi")
    assert record["images"] == {
        "source": "pinned",
        "url": IMAGES_URL,
        "sha256": _sha256(packed),
        "pin": "matched",
    }
    assert record["manifest"] is None
    assert record["skipped_members_not_dicom"] is None
    assert (record["series"], record["files"]) == (2, 3)
    assert record["bytes"] == sum(len(data) for data in FILES)
    assert record["content"] == {"sha256": _content(), "pin": "matched"}
    assert sorted(path.name for path in destination.iterdir()) == [
        "answer-key.db",
        "download.json",
        "images",
    ]


def test_a_copy_that_cannot_be_fetched_falls_back_to_tcia(tmp_path, no_sleep):
    server = Server()  # Answers the images' URL with 404.
    lines: list[str] = []
    record = midi_download.download(
        _subset(images_url=IMAGES_URL, images_sha256="0" * 64),
        tmp_path / "midi",
        opener=server,
        progress=lines.append,
    )
    failure = (
        "the images' ZIP file could not be fetched after 6 attempts (HTTPError 404)"
    )
    assert record["images"] == {
        "source": "tcia",
        "fallback": {"from": IMAGES_URL, "failure": failure},
    }
    assert record["manifest"]["pin"] == "matched"
    assert record["content"] == {"sha256": _content(), "pin": "matched"}
    assert server.requests.count(IMAGES_URL) == midi_download.ATTEMPTS
    assert f"Taking the images from TCIA instead: {failure}" in lines
    assert len(no_sleep) == midi_download.ATTEMPTS - 1
    assert _tree(tmp_path / "midi") == {
        "0001/00001.dcm": FILES[0],
        "0001/00002.dcm": FILES[1],
        "0002/00001.dcm": FILES[2],
    }


def test_a_copy_that_differs_from_its_pin_stops_the_download(tmp_path):
    server = Server(images=_packed(tmp_path))
    with pytest.raises(DownloadError, match="images' ZIP file's SHA-256"):
        midi_download.download(
            _subset(images_url=IMAGES_URL, images_sha256="0" * 64),
            tmp_path / "midi",
            opener=server,
        )
    # It does not fall back to TCIA.
    assert server.requests == [KEY_URL, IMAGES_URL]


def test_images_from_tcia_skip_the_pinned_copy(tmp_path):
    packed = _packed(tmp_path)
    server = Server(images=packed)
    record = midi_download.download(
        _subset(images_url=IMAGES_URL, images_sha256=_sha256(packed)),
        tmp_path / "midi",
        opener=server,
        images_from="tcia",
    )
    assert IMAGES_URL not in server.requests
    assert record["images"] == {"source": "tcia"}


def test_without_tcia_the_pinned_copy_is_still_taken(tmp_path):
    packed = _packed(tmp_path)
    server = Server(images=packed)
    record = midi_download.download(
        _subset(images_url=IMAGES_URL, images_sha256=_sha256(packed)),
        tmp_path / "midi",
        opener=server,
        tcia=False,
    )
    assert server.requests == [KEY_URL, IMAGES_URL]
    assert record["images"]["source"] == "pinned"


def test_without_tcia_a_copy_that_cannot_be_fetched_stops_the_download(
    tmp_path, no_sleep
):
    server = Server()  # Answers the images' URL with 404.
    with pytest.raises(DownloadError) as raised:
        midi_download.download(
            _subset(images_url=IMAGES_URL, images_sha256="0" * 64),
            tmp_path / "midi",
            opener=server,
            tcia=False,
        )
    assert str(raised.value) == (
        "the images' ZIP file could not be fetched after 6 attempts (HTTPError 404), "
        "and this download may not take the images from TCIA"
    )
    # Neither TCIA's manifest nor NBIA is asked for anything.
    assert set(server.requests) == {KEY_URL, IMAGES_URL}
    assert len(no_sleep) == midi_download.ATTEMPTS - 1


@pytest.mark.parametrize(
    "subset, arguments",
    [
        (_subset(), {}),
        (_subset(), {"images_from": "tcia"}),
        (
            _subset(images_url=IMAGES_URL, images_sha256="0" * 64),
            {"images_from": "tcia"},
        ),
    ],
)
def test_without_tcia_images_that_only_tcia_could_give_are_refused_at_once(
    tmp_path, subset, arguments
):
    server = Server()
    with pytest.raises(DownloadError, match="the images would come from TCIA"):
        midi_download.download(
            subset, tmp_path / "midi", opener=server, tcia=False, **arguments
        )
    assert not server.requests
    assert not (tmp_path / "midi").exists()


def test_without_tcia_a_local_copy_of_the_images_is_still_taken(tmp_path):
    packed = _packed(tmp_path)
    copy = tmp_path / "copy.zip"
    copy.write_bytes(packed)
    record = midi_download.download(
        _subset(), tmp_path / "midi", opener=Server(), images_file=copy, tcia=False
    )
    assert record["images"]["source"] == "file"


@pytest.mark.parametrize("pinned", [True, False])
def test_a_local_copy_of_the_images_zip_is_unpacked(tmp_path, pinned):
    packed = _packed(tmp_path)
    copy = tmp_path / "from-zenodo.zip"
    copy.write_bytes(packed)
    server = Server()
    record = midi_download.download(
        _subset(images_sha256=_sha256(packed) if pinned else ""),
        tmp_path / "midi",
        opener=server,
        images_file=copy,
    )
    assert server.requests == [KEY_URL]
    assert record["images"] == {
        "source": "file",
        "sha256": _sha256(packed),
        "pin": "matched" if pinned else "not pinned",
    }
    assert record["content"] == {"sha256": _content(), "pin": "matched"}
    assert _tree(tmp_path / "midi") == _tree(tmp_path / "packed" / "midi")


@pytest.mark.parametrize(
    "arguments, message",
    [
        ({"images_from": "nbia"}, "the pinned copy or from TCIA"),
        ({"images_file": "missing.zip"}, "is not a file"),
        ({"images_file": __file__, "images_from": "tcia"}, "not both"),
    ],
)
def test_unusable_image_sources_are_refused(tmp_path, arguments, message):
    with pytest.raises(DownloadError, match=message):
        midi_download.download(
            _subset(), tmp_path / "midi", opener=Server(), **arguments
        )
    assert not (tmp_path / "midi").exists()


def _zip(members, compression=zipfile.ZIP_STORED) -> bytes:
    """A ZIP file of ``members``, a list of names and bytes, in order."""
    buffer = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # A duplicate name, on purpose.
        with zipfile.ZipFile(buffer, "w", compression) as zipped:
            for name, data in members:
                info = zipfile.ZipInfo(name, date_time=DATE)
                info.compress_type = compression
                zipped.writestr(info, data)
    return buffer.getvalue()


def _images(*names):
    return [(f"{ROOT}/images/{name}", _dicom(name)) for name in names]


@pytest.mark.parametrize(
    "data, message",
    [
        (b"not a ZIP file", r"not readable \(BadZipFile\)"),
        (_zip([(f"{ROOT}/README.txt", b"x")]), "does not number"),
        (_zip([("../evil.dcm", _dicom("x"))]), "holds a member that is not"),
        (
            _zip([(f"/{ROOT}/images/0001/00001.dcm", _dicom("x"))]),
            "member that is not",
        ),
        (_zip(_images("0001/../../evil.dcm")), "holds a member that is not"),
        (_zip([("OTHER/images/0001/00001.dcm", _dicom("x"))]), "member that is not"),
        (
            _zip([(f"{ROOT}/LICENSE", b"x"), *_images("0001/00001.dcm")]),
            "member that is not",
        ),
        (_zip(_images("0001/00001.dcm", "0001/00003.dcm")), "does not number"),
        (_zip(_images("0002/00001.dcm")), "does not number"),
        (_zip(_images("0001/00001.dcm", "0001/00001.dcm")), "each once"),
        (
            _zip(_images("0001/00001.dcm"), zipfile.ZIP_DEFLATED),
            "compressed member",
        ),
        (_zip([(f"{ROOT}/images/0001/00001.dcm", b"not DICOM")]), "not a DICOM"),
    ],
    ids=[
        "not a ZIP file",
        "README alone",
        "parent folder",
        "absolute path",
        "path through parents",
        "another folder",
        "another file",
        "file numbers with a gap",
        "series numbers with a gap",
        "a file twice",
        "compressed",
        "not DICOM",
    ],
)
def test_a_zip_that_pack_would_not_write_is_refused(tmp_path, data, message):
    copy = tmp_path / "copy.zip"
    copy.write_bytes(data)
    with pytest.raises(DownloadError, match=message) as raised:
        midi_download.download(
            _subset(), tmp_path / "midi", opener=Server(), images_file=copy
        )
    assert "evil" not in str(raised.value)
    # Nothing is written outside the destination's images folder.
    assert sorted(path.name for path in tmp_path.iterdir()) == ["copy.zip", "midi"]
    assert not (tmp_path / "midi" / "evil.dcm").exists()


def test_a_zip_of_another_subset_is_refused_before_unpacking(tmp_path):
    copy = tmp_path / "copy.zip"
    copy.write_bytes(_packed(tmp_path))
    with pytest.raises(DownloadError, match="member that is not"):
        midi_download.download(
            _subset(collection="ANOTHER-COLLECTION"),
            tmp_path / "midi",
            opener=Server(),
            images_file=copy,
        )
    assert not any((tmp_path / "midi" / "images").iterdir())


class Truncated(io.BytesIO):
    """A response that declares more bytes than it holds."""

    def __init__(self, data: bytes, declared: int):
        super().__init__(data)
        self.headers = {"Content-Length": str(declared)}


def test_a_transfer_that_ends_early_is_fetched_again(tmp_path, no_sleep):
    class EndsEarly(Server):
        served = False

        def __call__(self, url):
            if url == MANIFEST_URL and not self.served:
                self.served = True
                self.requests.append(url)
                return Truncated(self.manifest[:10], len(self.manifest))
            return super().__call__(url)

    lines: list[str] = []
    record = midi_download.download(
        _subset(), tmp_path / "midi", opener=EndsEarly(), progress=lines.append
    )
    stamp = r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ"
    assert [re.sub(stamp, "<time>", line) for line in lines if "failed" in line] == [
        "Fetching the manifest: attempt 1 of 6 failed at <time> (the transfer "
        f"ended after 10 of {len(_manifest())} bytes); trying again in 10 s"
    ]
    assert no_sleep == [midi_download.WAITS[0]]
    assert record["manifest"]["pin"] == "matched"


def test_a_long_fetch_reports_each_gibibyte(tmp_path, monkeypatch):
    packed = _packed(tmp_path)
    # A "gibibyte" of 1,000 bytes, read 300 bytes at a time.
    monkeypatch.setattr(midi_download, "GIB", 1000)
    monkeypatch.setattr(midi_download, "CHUNK", 300)
    lines: list[str] = []
    midi_download.download(
        _subset(images_url=IMAGES_URL, images_sha256=_sha256(packed)),
        tmp_path / "midi",
        opener=Server(images=packed),
        progress=lines.append,
    )
    assert len(packed) >= 2000
    assert [line for line in lines if "GiB" in line] == [
        f"{size} GiB of the images' ZIP file received"
        for size in range(1, len(packed) // 1000 + 1)
    ]


def test_the_command_takes_the_images_from_a_local_copy(tmp_path, capsys):
    packed = _packed(tmp_path)
    copy = tmp_path / "copy.zip"
    copy.write_bytes(packed)
    original = midi_download.download

    def download(*args, **kwargs):
        return original(*args, **{**kwargs, "opener": Server()})

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(midi_download, "download", download)
        status = midi_download.main(
            [
                "--subset",
                "validation",
                "--dest",
                str(tmp_path / "midi"),
                "--images-file",
                str(copy),
            ],
            subsets={"validation": _subset()},
        )
    assert status == 0
    assert json.loads(capsys.readouterr().out)["images"]["source"] == "file"


def test_the_command_can_refuse_tcia(tmp_path):
    calls = []

    def download(*_, **kwargs):
        calls.append(kwargs["tcia"])
        raise DownloadError(
            "the images would come from TCIA, which this download may not use"
        )

    for arguments, tcia in (([], True), (["--no-tcia"], False)):
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(midi_download, "download", download)
            with pytest.raises(SystemExit, match="may not use"):
                midi_download.main(
                    [
                        "--subset",
                        "validation",
                        "--dest",
                        str(tmp_path / "midi"),
                        *arguments,
                    ],
                    subsets={"validation": _subset()},
                )
        assert calls[-1] is tcia


@pytest.mark.parametrize(
    "arguments",
    [["--images-file", "x.zip"], ["--images-from", "tcia"], ["--no-tcia"]],
)
def test_image_sources_go_only_with_a_download(tmp_path, capsys, arguments):
    with pytest.raises(SystemExit):
        midi_download.main(
            ["--subset", "validation", "--verify", str(tmp_path), *arguments],
            subsets={"validation": _subset()},
        )
    assert "goes with --dest" in capsys.readouterr().err
