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

"""Data downloads require recorded hashes unless explicitly opted out.

Every test works offline: sources are ``file://`` URLs, the cache is a
temporary ``PYMEDPHYS_DATA_DIR``, and hashes come from a temporary copy of
``hashes.json``.
"""

import hashlib
import json
import os
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


@pytest.mark.parametrize("damage", ["truncate", "delete"])
def test_damaged_extracted_file_is_extracted_again(cache, tmp_path, damage):
    _, hashes = cache
    source = _zip(tmp_path / "v1.zip", {"a.txt": "complete contents"})
    _record(hashes, "archive.zip", source)
    (extracted,) = download.zip_data_paths(
        "archive.zip", url=source.as_uri(), hash_filepath=hashes
    )

    if damage == "truncate":
        extracted.write_text("trunc", encoding="utf-8")
    else:
        extracted.unlink()
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


@pytest.mark.parametrize(
    "member",
    [
        download.EXTRACTED_ARCHIVE_MARKER,
        f"{download.EXTRACTED_ARCHIVE_MARKER}/data.txt",
    ],
)
def test_archive_members_named_like_marker_are_preserved(cache, tmp_path, member):
    _, hashes = cache
    source = _zip(tmp_path / "source.zip", {member: "archived contents"})
    _record(hashes, "archive.zip", source)

    for _ in range(2):
        (extracted,) = download.zip_data_paths(
            "archive.zip", url=source.as_uri(), hash_filepath=hashes
        )
        assert extracted.read_text(encoding="utf-8") == "archived contents"


def test_empty_archive_returns_no_files(cache, tmp_path):
    data_dir, hashes = cache
    source = _zip(tmp_path / "empty.zip", {})
    _record(hashes, "archive.zip", source)

    for _ in range(2):
        assert (
            download.zip_data_paths(
                "archive.zip", url=source.as_uri(), hash_filepath=hashes
            )
            == []
        )
        assert (data_dir / "archive").is_dir()


def test_invalid_marker_refreshes_the_extraction(cache, tmp_path):
    data_dir, hashes = cache
    source = _zip(tmp_path / "source.zip", {"data.txt": "complete contents"})
    _record(hashes, "archive.zip", source)
    (extracted,) = download.zip_data_paths(
        "archive.zip", url=source.as_uri(), hash_filepath=hashes
    )
    (marker,) = data_dir.rglob(f"*{download.EXTRACTED_ARCHIVE_MARKER}")
    marker.write_bytes(b"\xff")
    # Equal sizes ensure that the invalid marker itself triggers the refresh.
    extracted.write_text("tampered contents", encoding="utf-8")

    (again,) = download.zip_data_paths(
        "archive.zip", url=source.as_uri(), hash_filepath=hashes
    )

    assert again.read_text(encoding="utf-8") == "complete contents"
    assert marker.read_text(encoding="utf-8") == _sha1(source)


def test_complete_extraction_is_reused(cache, tmp_path, monkeypatch):
    _, hashes = cache
    source = _zip(tmp_path / "source.zip", {"data.txt": "complete contents"})
    _record(hashes, "archive.zip", source)
    first = download.zip_data_paths(
        "archive.zip", url=source.as_uri(), hash_filepath=hashes
    )

    def unexpected_extraction(*_args, **_kwargs):
        pytest.fail("A complete, unchanged archive should not be extracted again")

    monkeypatch.setattr(zipfile.ZipFile, "extractall", unexpected_extraction)

    assert (
        download.zip_data_paths(
            "archive.zip", url=source.as_uri(), hash_filepath=hashes
        )
        == first
    )


def test_interrupted_refresh_is_retried(cache, tmp_path, monkeypatch):
    data_dir, hashes = cache
    members = {"a.txt": "complete a", "b.txt": "complete b"}
    source = _zip(tmp_path / "source.zip", members)
    _record(hashes, "archive.zip", source)
    download.zip_data_paths("archive.zip", url=source.as_uri(), hash_filepath=hashes)
    (data_dir / "archive/b.txt").write_text("truncated", encoding="utf-8")

    def interrupted_extraction(archive, path):
        archive.extract("a.txt", path=path)
        raise OSError("Interrupted extraction")

    with monkeypatch.context() as patch:
        patch.setattr(zipfile.ZipFile, "extractall", interrupted_extraction)
        with pytest.raises(OSError, match="Interrupted extraction"):
            download.zip_data_paths(
                "archive.zip", url=source.as_uri(), hash_filepath=hashes
            )

    assert not list(data_dir.rglob(f"*{download.EXTRACTED_ARCHIVE_MARKER}"))

    paths = download.zip_data_paths(
        "archive.zip", url=source.as_uri(), hash_filepath=hashes
    )
    assert {path.name: path.read_text(encoding="utf-8") for path in paths} == members


def test_archives_sharing_an_extraction_directory_refresh_each_other(cache, tmp_path):
    _, hashes = cache
    sources = {
        "archive.zip": _zip(tmp_path / "one.zip", {"data.txt": "one"}),
        "archive.npz": _zip(tmp_path / "two.zip", {"data.txt": "two"}),
    }
    for name, source in sources.items():
        _record(hashes, name, source)

    for name, contents in [
        ("archive.zip", "one"),
        ("archive.npz", "two"),
        ("archive.zip", "one"),
    ]:
        (extracted,) = download.zip_data_paths(
            name, url=sources[name].as_uri(), hash_filepath=hashes
        )
        assert extracted.read_text(encoding="utf-8") == contents


@pytest.mark.parametrize("member", ["", "empty/"])
def test_missing_empty_directories_are_recreated(cache, tmp_path, member):
    data_dir, hashes = cache
    source = _zip(tmp_path / "source.zip", {member: ""} if member else {})
    _record(hashes, "archive.zip", source)
    download.zip_data_paths("archive.zip", url=source.as_uri(), hash_filepath=hashes)
    directory = data_dir / "archive" / member
    directory.rmdir()

    assert not download.zip_data_paths(
        "archive.zip", url=source.as_uri(), hash_filepath=hashes
    )
    assert directory.is_dir()


def test_duplicate_zip_members_reuse_the_final_entry(cache, tmp_path, monkeypatch):
    _, hashes = cache
    source = _zip(tmp_path / "source.zip", {"data.txt": "old"})
    with zipfile.ZipFile(source, "a") as archive:
        with pytest.warns(UserWarning, match="Duplicate name"):
            archive.writestr("data.txt", "final contents")
    _record(hashes, "archive.zip", source)
    first = download.zip_data_paths(
        "archive.zip", url=source.as_uri(), hash_filepath=hashes
    )
    assert all(path.read_text(encoding="utf-8") == "final contents" for path in first)

    def unexpected_extraction(*_args, **_kwargs):
        pytest.fail("Repeated member names should not invalidate a complete extraction")

    monkeypatch.setattr(zipfile.ZipFile, "extractall", unexpected_extraction)
    assert (
        download.zip_data_paths(
            "archive.zip", url=source.as_uri(), hash_filepath=hashes
        )
        == first
    )


def test_long_archive_names_can_be_extracted(cache, tmp_path, monkeypatch):
    data_dir, hashes = cache
    # Exercise the component-length limit independently of Windows' legacy
    # total-path limit and of the downloader's temporary filename.
    if os.name == "nt":
        data_dir = pathlib.Path("\\\\?\\" + str(data_dir.resolve()))
        monkeypatch.setenv(download.DATA_DIR_ENVIRONMENT_VARIABLE, str(data_dir))
    data_dir.mkdir(parents=True)
    name = "x" * 224 + ".zip"
    source = _zip(tmp_path / "source.zip", {"data.txt": "contents"})
    _record(hashes, name, source)
    (data_dir / name).write_bytes(source.read_bytes())

    for _ in range(2):
        (extracted,) = download.zip_data_paths(name, hash_filepath=hashes)
        assert extracted.read_text(encoding="utf-8") == "contents"


def test_direct_hash_check_does_not_record_unverified_content(cache):
    data_dir, hashes = cache
    data_dir.mkdir()
    (data_dir / "unrecorded.txt").write_text("unverified", encoding="utf-8")

    with pytest.raises(download.NoHashFound):
        download.data_file_hash_check("unrecorded.txt", hash_filepath=hashes)

    assert hashes.read_text(encoding="utf-8") == "{}"


@pytest.mark.parametrize("delete_cached", [False, True])
def test_missing_hash_respects_cached_file_deletion(cache, monkeypatch, delete_cached):
    data_dir, hashes = cache
    data_dir.mkdir()
    cached = data_dir / "unrecorded.txt"
    cached.write_text("unverified", encoding="utf-8")

    def unexpected_download(*_args, **_kwargs):
        pytest.fail("A missing recorded hash must be rejected before downloading")

    monkeypatch.setattr(download, "download_with_progress", unexpected_download)
    with pytest.raises(download.NoHashFound):
        download.data_path(
            "unrecorded.txt",
            hash_filepath=hashes,
            delete_when_no_hash_found=delete_cached,
        )

    if delete_cached:
        assert not cached.exists()
    else:
        assert cached.read_text(encoding="utf-8") == "unverified"
    assert hashes.read_text(encoding="utf-8") == "{}"


@pytest.mark.parametrize("filename", ["data.txt", "archive.zip"])
def test_zenodo_downloads_require_hashes_unless_skipped(
    cache, tmp_path, monkeypatch, filename
):
    data_dir, hashes = cache
    source = tmp_path / filename
    if source.suffix == ".zip":
        _zip(source, {"data.txt": "contents"})
    else:
        source.write_text("contents", encoding="utf-8")
    monkeypatch.setattr(download, "DEFAULT_HASHES_PATH", hashes)
    monkeypatch.setattr(
        download.zenodo,
        "get_zenodo_file_urls",
        lambda _record: {filename: source.as_uri()},
    )

    with pytest.raises(download.NoHashFound):
        download.zenodo_data_paths("review-record")
    assert not (data_dir / "review-record" / filename).exists()

    (path,) = download.zenodo_data_paths("review-record", check_hash=False)
    assert path.read_text(encoding="utf-8") == "contents"
    assert hashes.read_text(encoding="utf-8") == "{}"
