# Copyright (C) 2026 Matthew Jennings
# Copyright (C) 2019 Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import contextlib
import functools
import hashlib
import importlib.util
import json
import logging
import os
import pathlib
import stat
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from http import HTTPStatus

from pymedphys._imports import tqdm

import pymedphys._utilities.filehash
from pymedphys import _config as pmp_config

from . import _zip_safe, retry, zenodo

HERE = pathlib.Path(__file__).resolve().parent
DEFAULT_HASHES_PATH = HERE.joinpath("hashes.json")


# Every URL comes from the package's own urls.json, a Zenodo record listing,
# or the caller of data_path(url=...). file: is kept for local mirrors; the
# caller already has filesystem access, so it grants nothing new. Every other
# scheme, including the ftp: and data: schemes that urllib would accept, is
# rejected.
SUPPORTED_URL_SCHEMES = ("http", "https", "file")

# Seconds to wait for the server to respond, and for each socket read after
# that. A stalled connection then raises instead of hanging the caller
# indefinitely.
DOWNLOAD_TIMEOUT_SECONDS = 60

# HTTP statuses worth retrying. Anything else (404, 403, and so on) will not
# change on a second attempt, so the download gives up at once.
RETRYABLE_HTTP_STATUSES = frozenset(
    {
        HTTPStatus.REQUEST_TIMEOUT,
        HTTPStatus.TOO_EARLY,
        HTTPStatus.TOO_MANY_REQUESTS,
        HTTPStatus.INTERNAL_SERVER_ERROR,
        HTTPStatus.BAD_GATEWAY,
        HTTPStatus.SERVICE_UNAVAILABLE,
        HTTPStatus.GATEWAY_TIMEOUT,
    }
)

DATA_DIR_ENVIRONMENT_VARIABLE = "PYMEDPHYS_DATA_DIR"

# Bytes read per iteration. The progress bar updates once per chunk, so this
# keeps it responsive on slow links (about 0.6 s per update at 100 kB/s) while
# the per-call overhead stays negligible. It does not affect stall detection:
# the timeout applies to each socket read, whatever the chunk size.
_CHUNK_SIZE = 64 * 1024


class _NoProgress:
    """Stands in for tqdm's progress bar where tqdm is not installed."""

    def update(self, _count: int) -> None:
        pass


def _tqdm_installed() -> bool:
    return importlib.util.find_spec("tqdm") is not None


def _progress_bar(total: int | None, description: str):
    """A progress bar for a download, which shows nothing without tqdm.

    tqdm comes with the user extra; text-detection downloads its model
    without it.
    """
    if not _tqdm_installed():
        return contextlib.nullcontext(_NoProgress())
    return tqdm.tqdm(
        total=total,
        unit="B",
        unit_scale=True,
        miniters=1,
        desc=description,
    )


def _is_permanent_failure(error: BaseException) -> bool:
    return (
        isinstance(error, urllib.error.HTTPError)
        and error.code not in RETRYABLE_HTTP_STATUSES
    )


@retry.retry(
    (urllib.error.URLError, ConnectionError, TimeoutError),
    giveup=_is_permanent_failure,
)
def download_with_progress(url: str, filepath: str | os.PathLike[str]) -> None:
    """Download ``url`` to ``filepath`` while showing a progress bar.

    The progress bar needs tqdm; without it the download is silent.

    The download is written to a temporary file beside ``filepath`` and only
    moved into place once it is complete, so an interrupted download never
    leaves a truncated file behind. Network errors, timeouts, and transient
    HTTP statuses are retried with an exponential backoff; other HTTP errors,
    such as 404, are raised immediately.

    Parameters
    ----------
    url : str
        An ``http``, ``https``, or ``file`` URL. Any other scheme raises
        ``ValueError``.
    filepath : str or os.PathLike
        Where the download is written.
    """
    scheme = urllib.parse.urlsplit(url).scheme
    if scheme not in SUPPORTED_URL_SCHEMES:
        raise ValueError(
            f"Unsupported URL scheme {scheme!r} in {url!r}; "
            f"expected one of {SUPPORTED_URL_SCHEMES}"
        )

    filepath = pathlib.Path(filepath)

    # The scheme was checked against SUPPORTED_URL_SCHEMES above, and the
    # note on that constant explains why file: is acceptable here.
    with urllib.request.urlopen(  # nosec B310
        url, timeout=DOWNLOAD_TIMEOUT_SECONDS
    ) as response:
        content_length = response.headers.get("Content-Length")
        expected_size = int(content_length) if content_length else None

        file_descriptor, temp_name = tempfile.mkstemp(
            dir=filepath.parent, prefix=f".{filepath.name}.", suffix=".part"
        )
        temp_path = pathlib.Path(temp_name)
        try:
            with (
                os.fdopen(file_descriptor, "wb") as temp_file,
                _progress_bar(expected_size, url.split("/")[-1]) as progress,
            ):
                received = 0
                while chunk := response.read(_CHUNK_SIZE):
                    temp_file.write(chunk)
                    received += len(chunk)
                    progress.update(len(chunk))

            if expected_size is not None and received < expected_size:
                raise urllib.error.ContentTooShortError(
                    f"Download of {url} stopped after {received} of "
                    f"{expected_size} bytes",
                    (str(filepath), response.headers),
                )

            os.replace(temp_path, filepath)
        except BaseException:
            temp_path.unlink(missing_ok=True)
            raise


def get_data_dir():
    """Return the directory that caches downloaded data, creating it if needed.

    The ``PYMEDPHYS_DATA_DIR`` environment variable overrides the default of
    ``~/.pymedphys/data``.
    """
    override = os.environ.get(DATA_DIR_ENVIRONMENT_VARIABLE)
    if override:
        data_dir = pathlib.Path(override)
    else:
        data_dir = pmp_config.get_config_dir().joinpath("data")

    data_dir.mkdir(parents=True, exist_ok=True)

    return data_dir


def get_file_within_data_zip(zip_name, file_name):
    dose_data_files = pymedphys.zip_data_paths(zip_name)
    path_match = [path for path in dose_data_files if path.name == file_name]

    if len(path_match) != 1:
        print(path_match)

        raise ValueError("Expected to find exactly one file")

    return str(path_match[0])


@functools.lru_cache()
def get_url_map():
    with open(HERE.joinpath("urls.json")) as f:
        url_map = json.load(f)

    return url_map


def get_url(filename):
    filename = str(filename).replace(os.sep, "/")
    url_map = get_url_map()

    try:
        url = url_map[filename]
    except KeyError:
        raise ValueError("The file provided isn't within pymedphys' urls.json record.")

    return url


def download_all():
    paths = []
    for file_name in get_url_map().keys():
        paths.append(data_path(file_name))

    return paths


def data_path(
    filename,
    check_hash=True,
    redownload_on_hash_mismatch=True,
    delete_when_no_hash_found=True,
    url=None,
    hash_filepath=None,
):
    filename = str(filename).replace(os.sep, "/")
    filepath = get_data_dir().joinpath(filename)

    containing_directory = pathlib.Path(filepath).parent
    containing_directory.mkdir(exist_ok=True, parents=True)

    # Callers of the same file take turns to check, download, or repair it, so
    # two of them cannot both replace or delete it; replacing a file that
    # another process has open fails on Windows. A valid file is never
    # modified, so callers can use the returned path after the lock is
    # released.
    with download_lock(filepath):
        return _checked_data_path(
            filename,
            filepath,
            check_hash=check_hash,
            redownload_on_hash_mismatch=redownload_on_hash_mismatch,
            delete_when_no_hash_found=delete_when_no_hash_found,
            url=url,
            hash_filepath=hash_filepath,
        )


def _checked_data_path(
    filename,
    filepath,
    check_hash,
    redownload_on_hash_mismatch,
    delete_when_no_hash_found,
    url,
    hash_filepath,
):
    """Check, download, or repair one cached file; the caller holds its lock."""
    logging.debug("Filepath saving to is %s", filepath)
    logging.debug("Does filepath exist? %s", filepath.exists())

    if check_hash:
        try:
            get_cached_filehash(filename, hash_filepath=hash_filepath)
        except NoHashFound:
            # Unverifiable data is never served: remove any cached copy so a
            # later call cannot pick it up, and do not download it.
            if delete_when_no_hash_found and filepath.exists():
                filepath.unlink()
            raise

    if not filepath.exists():
        if url is None:
            url = get_url(filename)

        download_with_progress(url, filepath)

    if check_hash:
        hash_agrees = data_file_hash_check(filename, hash_filepath=hash_filepath)

        if not hash_agrees:
            if redownload_on_hash_mismatch:
                filepath.unlink()
                # Retry inside the lock this call already holds.
                return _checked_data_path(
                    filename,
                    filepath,
                    check_hash=True,
                    redownload_on_hash_mismatch=False,
                    delete_when_no_hash_found=True,
                    url=url,
                    hash_filepath=hash_filepath,
                )

            raise ValueError("The file on disk does not match the recorded hash.")

    return filepath.resolve()


class NoHashFound(KeyError):
    """The file has no recorded hash, so its contents cannot be verified."""


def get_cached_filehash(filename, hash_filepath=None):
    if hash_filepath is None:
        hash_filepath = DEFAULT_HASHES_PATH

    filename = str(filename).replace(os.sep, "/")

    with open(hash_filepath) as hash_file:
        hashes = json.load(hash_file)

    try:
        cached_filehash = hashes[filename]
    except KeyError:
        raise NoHashFound(
            f"No hash is recorded for '{filename}' in {hash_filepath}, so it "
            "cannot be verified. Record its hash, or pass check_hash=False to "
            "use it unverified."
        ) from None

    return cached_filehash


def data_file_hash_check(filename, hash_filepath=None):
    if hash_filepath is None:
        hash_filepath = DEFAULT_HASHES_PATH

    filename = str(filename).replace(os.sep, "/")

    filepath = get_data_dir().joinpath(filename)
    calculated_filehash = pymedphys._utilities.filehash.hash_file(  # pylint: disable = protected-access
        filepath
    )

    logging.debug("Calculated filehash is %s", calculated_filehash)

    cached_filehash = get_cached_filehash(filename, hash_filepath=hash_filepath)
    logging.debug("Cached filehash is %s", cached_filehash)

    return cached_filehash == calculated_filehash


def zenodo_data_paths(
    record_name, check_hash=True, redownload_on_hash_mismatch=True, filenames=None
):
    file_urls = zenodo.get_zenodo_file_urls(record_name)

    if filenames is not None:
        file_urls = {
            filename: url
            for filename, url in file_urls.items()
            if filename in filenames
        }

    logging.debug("File URLS are %s", file_urls)

    record_directory = get_data_dir().joinpath(record_name)
    record_directory.mkdir(exist_ok=True)

    relative_record_path = pathlib.Path(record_name)

    data_paths = []
    for filename, url in file_urls.items():
        filename = pathlib.Path(filename)
        save_filename = relative_record_path.joinpath(filename)

        if filename.suffix == ".zip":
            data_paths += zip_data_paths(
                save_filename,
                check_hash=check_hash,
                redownload_on_hash_mismatch=redownload_on_hash_mismatch,
                url=url,
            )
        else:
            data_paths.append(
                data_path(
                    save_filename,
                    check_hash=check_hash,
                    redownload_on_hash_mismatch=redownload_on_hash_mismatch,
                    url=url,
                )
            )

    return data_paths


EXTRACTED_ARCHIVE_MARKER = ".pymedphys-extracted-archive-sha1"
EXTRACTION_LOCK_SUFFIX = ".pymedphys-extraction-lock"
DOWNLOAD_LOCK_SUFFIX = ".pymedphys-download-lock"


def _sidecar_path(path, suffix):
    """Return a hidden file beside a cached file or directory, named after it.

    Keeping metadata outside the extracted members means an archive can never
    contain it, and naming it after the directory gives one file per
    directory even when several archives share that directory. A valid
    name can leave too little room for the suffix, so overlong names are
    hashed to fit the usual 255-byte filename component limit.
    """
    name = f".{path.name}{suffix}"
    if len(os.fsencode(name)) > 255:
        path_key = hashlib.sha256(os.fsencode(os.path.normcase(path.name))).hexdigest()
        name = f".{path_key}{suffix}"
    return path.with_name(name)


def extraction_lock(extract_directory):
    """Hold the lock that serialises the use of one cached archive.

    ``zip_data_paths`` holds it, for the archive's extraction directory in the
    data cache, while it downloads or repairs the archive, opens it, and
    extracts it.
    """
    return _exclusive_lock(
        _sidecar_path(pathlib.Path(extract_directory), EXTRACTION_LOCK_SUFFIX)
    )


def download_lock(filepath):
    """Hold the lock that serialises checking, downloading, or repairing a file.

    ``data_path`` holds it for each cached file.
    """
    return _exclusive_lock(_sidecar_path(pathlib.Path(filepath), DOWNLOAD_LOCK_SUFFIX))


@contextlib.contextmanager
def _exclusive_lock(lock_path):
    """Hold an exclusive lock on a lock file, shared by every process.

    Processes that share the data cache, such as parallel test workers, take
    it in turn. Each open of the lock file is a separate owner, so threads in
    one process also take turns. The operating system releases it when the
    lock file is closed, including when a process dies, so it cannot be left
    stale.
    """
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "a+b") as lock_file:
        if sys.platform == "win32":
            import msvcrt  # pylint: disable = import-error

            while True:
                # Lock the first byte, which may lie beyond the end of the
                # empty file. LK_LOCK gives up after about ten seconds.
                lock_file.seek(0)
                try:
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
                    break
                except OSError:
                    continue
            try:
                yield
            finally:
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _extraction_is_current(zip_file, extract_directory, archive_hash, marker):
    """Whether the archive's cache still contains complete, safe member files.

    The marker identifies the archive, and no-follow directory lookups check
    each member against the expected final archived size.
    """
    try:
        if (
            not stat.S_ISDIR(
                _zip_safe.member_stat(extract_directory, ".").st_mode
            )
            or _zip_safe.marker_bytes(marker).strip() != archive_hash.encode("ascii")
        ):
            return False
    except (OSError, RuntimeError, ValueError):
        return False

    # Extracted aliases share the same path. Check only the final member
    # at that path, including duplicates named data and ./data.
    for info in _zip_safe.last_members(zip_file):
        name = info.filename
        try:
            current = _zip_safe.member_stat(extract_directory, name)
        except (OSError, RuntimeError, ValueError):
            return False
        if info.is_dir():
            if not stat.S_ISDIR(current.st_mode):
                return False
        elif not stat.S_ISREG(current.st_mode) or current.st_size != info.file_size:
            return False

    return True


def _refresh_cached_extraction(zip_file, zip_filepath, extract_directory):
    """Extract the archive again unless the cache already holds it intact."""
    archive_hash = pymedphys._utilities.filehash.hash_file(  # pylint: disable = protected-access
        zip_filepath
    )
    marker = _sidecar_path(extract_directory, EXTRACTED_ARCHIVE_MARKER)
    if _extraction_is_current(zip_file, extract_directory, archive_hash, marker):
        return

    # Publish the marker only after every archive member has been installed.
    # Atomically replacing it avoids following a swapped marker symlink.
    _zip_safe.unlink_marker(marker)
    _zip_safe.extract_members(zip_file, extract_directory, missing_only=False)
    _zip_safe.write_marker(marker, archive_hash)


def _validate_zip_member_paths(
    zip_file: zipfile.ZipFile, extract_directory: os.PathLike[str] | str
) -> pathlib.Path:
    """Reject archive paths that could access files outside the destination.

    Perform preflight validation before cache reuse or extraction, and return
    the canonical extraction root. Subsequent operations use that canonical
    root rather than resolving a potentially substituted caller-provided path.
    Validation errors do not contain archive member names.
    """
    try:
        candidate = pathlib.Path(extract_directory)
        if candidate.is_symlink() or candidate.is_junction():
            raise ValueError("Cannot safely resolve ZIP extraction directory")
        root = candidate.resolve()
    except (OSError, RuntimeError):
        raise ValueError("Cannot safely resolve ZIP extraction directory") from None

    windows_devices = frozenset(
        {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
        | {f"{prefix}{index}" for prefix in ("COM", "LPT") for index in range(1, 10)}
        | {f"{prefix}{digit}" for prefix in ("COM", "LPT") for digit in "¹²³"}
    )
    seen_casefolded = {}
    for info in zip_file.infolist():
        name = info.filename.replace("\\", "/")
        # An empty, zero-length root entry is harmless; do not use it as
        # a file or include it in returned paths.
        if name in {"", ".", "./"}:
            if info.file_size == 0:
                continue
            raise ValueError("ZIP archive contains an unsafe member path")

        relative = pathlib.PurePosixPath(name)
        components = name.split("/")
        if (
            relative.is_absolute()
            or pathlib.PureWindowsPath(name).drive
            or ".." in relative.parts
            or any(
                (part and part not in {".", ".."} and part.rstrip(" .") != part)
                or any(
                    ord(character) < 32 or character in '<>:"|?*'
                    for character in part
                )
                or part.split(".")[0].rstrip(" ").upper() in windows_devices
                for part in components
            )
        ):
            raise ValueError("ZIP archive contains an unsafe member path")

        # Windows maps case variants to one path. Refuse distinct spellings
        # that would collide in staging or the caller's extraction directory.
        canonical = relative.parts
        folded = tuple(part.casefold() for part in canonical)
        previous = seen_casefolded.setdefault(folded, canonical)
        if previous != canonical:
            raise ValueError("ZIP archive contains an unsafe member path")

        try:
            current = root
            for part in relative.parts:
                current = current / part
                if current.is_symlink() or current.is_junction():
                    raise ValueError("ZIP archive contains a linked extraction path")

            target = current.resolve()
            if target == root or not target.is_relative_to(root):
                raise ValueError("ZIP archive member escapes the extraction directory")
            if target.is_file() and target.stat().st_nlink > 1:
                raise ValueError("ZIP archive targets a multiply linked file")
        except (OSError, RuntimeError):
            raise ValueError("Cannot safely resolve ZIP archive member") from None

    return root


def zip_data_paths(
    filename,
    check_hash=True,
    redownload_on_hash_mismatch=True,
    delete_when_no_hash_found=True,
    url=None,
    extract_directory=None,
    hash_filepath=None,
):
    cache_directory = get_data_dir().joinpath(
        pathlib.Path(os.path.splitext(filename)[0])
    )
    if extract_directory is None:
        extract_directory = cache_directory
        cache_managed = True
    else:
        extract_directory = pathlib.Path(extract_directory)
        cache_managed = False

    # Every caller of this archive, including one that extracts into its own
    # directory, holds the lock from checking or downloading the archive until
    # the extraction is complete. Otherwise another process could replace or
    # delete the archive while it is open, which fails on Windows, or rewrite
    # files while they are read.
    with extraction_lock(cache_directory):
        zip_filepath = data_path(
            filename,
            check_hash=check_hash,
            redownload_on_hash_mismatch=redownload_on_hash_mismatch,
            delete_when_no_hash_found=delete_when_no_hash_found,
            url=url,
            hash_filepath=hash_filepath,
        )

        with zipfile.ZipFile(zip_filepath, "r") as zip_file:
            namelist = zip_file.namelist()
            safe_root = _validate_zip_member_paths(zip_file, extract_directory)

            if cache_managed:
                _refresh_cached_extraction(zip_file, zip_filepath, safe_root)
            else:
                # A caller-selected working directory may contain edited files.
                # Insert missing files only; never follow a substituted link.
                _zip_safe.extract_members(zip_file, safe_root, missing_only=True)

        resolved_filepaths = []
        for name in namelist:
            if name.replace("\\", "/") in {"", ".", "./"}:
                continue
            try:
                current = _zip_safe.member_stat(safe_root, name)
            except (OSError, RuntimeError, ValueError):
                raise ValueError(
                    "ZIP archive contains a linked extraction path"
                ) from None
            if stat.S_ISREG(current.st_mode):
                relative = pathlib.PurePosixPath(name.replace("\\", "/"))
                resolved_filepaths.append(safe_root.joinpath(*relative.parts))

        return resolved_filepaths
