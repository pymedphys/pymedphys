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

"""The data cache serves only files that match their recorded hashes.

Every test works offline: sources are ``file://`` URLs, the cache is a
temporary ``PYMEDPHYS_DATA_DIR``, and hashes come from a temporary copy of
``hashes.json``.
"""

import hashlib
import json
import pathlib
import zipfile

from pymedphys._imports import pytest

from pymedphys._data import download


def _sha1(path: pathlib.Path) -> str:
    return hashlib.sha1(path.read_bytes(), usedforsecurity=False).hexdigest()


@pytest.fixture(name="cache")
def fixture_cache(tmp_path, monkeypatch):
    data_dir = tmp_path / "cache"
    monkeypatch.setenv(download.DATA_DIR_ENVIRONMENT_VARIABLE, str(data_dir))
    hashes = tmp_path / "hashes.json"
    hashes.write_text("{}", encoding="utf-8")
    return data_dir, hashes


def _record(hashes: pathlib.Path, name: str, source: pathlib.Path):
    recorded = json.loads(hashes.read_text(encoding="utf-8"))
    recorded[name] = _sha1(source)
    hashes.write_text(json.dumps(recorded), encoding="utf-8")


def _zip(path: pathlib.Path, members: dict[str, str]) -> pathlib.Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, text in members.items():
            archive.writestr(name, text)
    return path


def test_file_without_a_recorded_hash_is_refused(cache, tmp_path):
    data_dir, hashes = cache
    source = tmp_path / "unrecorded.txt"
    source.write_text("data", encoding="utf-8")

    with pytest.raises(download.NoHashFound, match="unrecorded.txt"):
        download.data_path("unrecorded.txt", url=source.as_uri(), hash_filepath=hashes)

    assert json.loads(hashes.read_text(encoding="utf-8")) == {}
    assert not (data_dir / "unrecorded.txt").exists()


def test_missing_hash_never_changes_the_package_hashes(cache, tmp_path, monkeypatch):
    _, hashes = cache
    monkeypatch.setattr(download, "DEFAULT_HASHES_PATH", hashes)
    source = tmp_path / "unrecorded.txt"
    source.write_text("data", encoding="utf-8")

    with pytest.raises(download.NoHashFound):
        download.data_path("unrecorded.txt", url=source.as_uri())

    assert json.loads(hashes.read_text(encoding="utf-8")) == {}


def test_hash_checks_can_still_be_skipped_explicitly(cache, tmp_path):
    _, hashes = cache
    source = tmp_path / "unrecorded.txt"
    source.write_text("data", encoding="utf-8")

    path = download.data_path(
        "unrecorded.txt", check_hash=False, url=source.as_uri(), hash_filepath=hashes
    )

    assert path.read_text(encoding="utf-8") == "data"


def test_extracted_files_follow_a_changed_archive(cache, tmp_path):
    _, hashes = cache
    source = _zip(tmp_path / "v1.zip", {"a.txt": "one", "b/c.txt": "sea"})
    _record(hashes, "archive.zip", source)
    first = download.zip_data_paths(
        "archive.zip", url=source.as_uri(), hash_filepath=hashes
    )
    assert {path.read_text(encoding="utf-8") for path in first} == {"one", "sea"}

    # A new release of the same archive changes a member's content.
    source = _zip(tmp_path / "v2.zip", {"a.txt": "two", "b/c.txt": "sea"})
    _record(hashes, "archive.zip", source)
    second = download.zip_data_paths(
        "archive.zip", url=source.as_uri(), hash_filepath=hashes
    )

    contents = {path.name: path.read_text(encoding="utf-8") for path in second}
    assert contents == {"a.txt": "two", "c.txt": "sea"}


def test_damaged_extracted_file_is_extracted_again(cache, tmp_path):
    _, hashes = cache
    source = _zip(tmp_path / "v1.zip", {"a.txt": "complete contents"})
    _record(hashes, "archive.zip", source)
    (extracted,) = download.zip_data_paths(
        "archive.zip", url=source.as_uri(), hash_filepath=hashes
    )

    extracted.write_text("trunc", encoding="utf-8")  # e.g. an interrupted copy
    (again,) = download.zip_data_paths(
        "archive.zip", url=source.as_uri(), hash_filepath=hashes
    )

    assert again.read_text(encoding="utf-8") == "complete contents"


def test_every_downloadable_file_has_a_recorded_hash():
    urls = json.loads(download.HERE.joinpath("urls.json").read_text(encoding="utf-8"))
    hashes = json.loads(download.DEFAULT_HASHES_PATH.read_text(encoding="utf-8"))

    assert sorted(set(urls) - set(hashes)) == []


def test_caller_directories_keep_edited_files(cache, tmp_path):
    # The GUI demo extracts into the user's working directory, where people
    # edit the extracted configuration; those edits must survive.
    _, hashes = cache
    source = _zip(tmp_path / "v1.zip", {"config.toml": "demo"})
    _record(hashes, "archive.zip", source)
    working = tmp_path / "working"
    (config,) = download.zip_data_paths(
        "archive.zip",
        url=source.as_uri(),
        hash_filepath=hashes,
        extract_directory=working,
    )
    config.write_text("edited by the user", encoding="utf-8")

    (again,) = download.zip_data_paths(
        "archive.zip",
        url=source.as_uri(),
        hash_filepath=hashes,
        extract_directory=working,
    )

    assert again.read_text(encoding="utf-8") == "edited by the user"
    assert sorted(path.name for path in working.iterdir()) == ["config.toml"]
