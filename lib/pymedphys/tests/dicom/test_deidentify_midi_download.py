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

"""Tests of the MIDI-B downloader (D-018).

Nothing here touches the network: every URL is served from memory, and every
manifest, archive, and file is made up for the tests.
"""

import hashlib
import io
import json
import urllib.error
import urllib.parse
import zipfile

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import midi_download
from pymedphys._dicom.deidentify.midi_download import DownloadError

MANIFEST_URL = "https://example.org/manifest.tcia"
KEY_URL = "https://example.org/answer-key.db"
SERIES = ("2.25.9001", "2.25.9002")
KEY = b"SQLite format 3\x00 synthetic answer key"


def _dicom(text: str) -> bytes:
    return b"\x00" * 128 + b"DICM" + text.encode("ascii")


def _archive(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zipped:
        for name, data in members.items():
            zipped.writestr(name, data)
    return buffer.getvalue()


def _manifest(series=SERIES) -> bytes:
    lines = [
        "downloadServerUrl=https://example.org/servlet",
        "manifestVersion=3.0",
        "ListOfSeriesToDownload=",
        *series,
    ]
    return ("\n".join(lines) + "\n").encode("ascii")


# File names inside the archives are UIDs, as NBIA's are; none may reach a
# path or the record.
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
        "answer_key_url": KEY_URL,
        "answer_key_sha256": _sha256(KEY),
    }
    pins.update(changes)
    return midi_download.Subset(**pins)


class Server:
    """Serves the made-up manifest, archives, and answer key from memory."""

    def __init__(self, manifest=None, archives=None, failures=0):
        self.manifest = _manifest() if manifest is None else manifest
        self.archives = ARCHIVES if archives is None else archives
        self.failures = failures
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


@pytest.mark.parametrize(
    "entry, message",
    [
        ('collection = "X"', "incomplete"),
        (
            'collection = "X"\nname = "X"\nmanifest_url = "http://x"\n'
            'manifest_sha256 = ""\nseries = 1\ninstances = 1\n'
            'content_sha256 = ""\nanswer_key_url = ""\nanswer_key_sha256 = ""',
            "not HTTPS",
        ),
        (
            'collection = "X"\nname = "X"\nmanifest_url = "https://x"\n'
            'manifest_sha256 = "ABC"\nseries = 1\ninstances = 1\n'
            'content_sha256 = ""\nanswer_key_url = ""\nanswer_key_sha256 = ""',
            "malformed",
        ),
    ],
)
def test_malformed_pins_are_refused(entry, message):
    with pytest.raises(DownloadError, match=message):
        midi_download.load_subsets(f"[subset]\n{entry}\n")


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
    assert record["skipped_members_not_dicom"] == 1
    assert record["bytes"] == sum(len(data) for data in FILES)
    assert record["content"] == {"sha256": _content(), "pin": "matched"}
    assert record["manifest"]["pin"] == "matched"
    assert record["answer_key"] == {
        "source": "pinned",
        "sha256": _sha256(KEY),
        "pin": "matched",
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
    assert no_sleep == [2.0, 4.0, 8.0]


def test_a_fetch_that_keeps_failing_names_no_url(tmp_path, no_sleep):
    with pytest.raises(DownloadError) as raised:
        midi_download.download(
            _subset(), tmp_path / "midi", opener=Server(failures=99), workers=1
        )
    assert str(raised.value) == (
        "the manifest could not be fetched after 4 attempts (URLError)"
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
        "the series 2 of 2 could not be fetched after 4 attempts (HTTPError)"
    )


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
