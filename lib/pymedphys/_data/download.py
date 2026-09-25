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


import functools
import json
import logging
import os
import pathlib
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from http import HTTPStatus

from pymedphys._imports import tqdm

import pymedphys._utilities.filehash
from pymedphys import _config as pmp_config

from . import retry, zenodo

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
                tqdm.tqdm(
                    total=expected_size,
                    unit="B",
                    unit_scale=True,
                    miniters=1,
                    desc=url.split("/")[-1],
                ) as progress,
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

    logging.debug("Filepath saving to is %s", filepath)
    logging.debug("Does filepath exist? %s", filepath.exists())

    if check_hash and filepath.exists():
        try:
            get_cached_filehash(filename, hash_filepath=hash_filepath)
        except NoHashFound:
            if delete_when_no_hash_found:
                logging.warning("No hash found, deleting current file")
                filepath.unlink()  # Force a redownload

    if not filepath.exists():
        if url is None:
            url = get_url(filename)

        download_with_progress(url, filepath)

    if check_hash:
        try:
            hash_agrees = data_file_hash_check(filename, hash_filepath=hash_filepath)
        except NoHashFound:
            return filepath.resolve()

        if not hash_agrees:
            if redownload_on_hash_mismatch:
                filepath.unlink()
                return data_path(
                    filename,
                    redownload_on_hash_mismatch=False,
                    url=url,
                    hash_filepath=hash_filepath,
                )

            raise ValueError("The file on disk does not match the recorded hash.")

    return filepath.resolve()


class NoHashFound(KeyError):
    pass


def get_cached_filehash(filename, hash_filepath=None):
    if hash_filepath is None:
        hash_filepath = DEFAULT_HASHES_PATH

    filename = str(filename).replace(os.sep, "/")

    with open(hash_filepath) as hash_file:
        hashes = json.load(hash_file)

    try:
        cached_filehash = hashes[filename]
    except KeyError:
        logging.warning("No hash found for file '%s'", filename)
        logging.debug("Hashes found were %s", hashes.keys())
        raise NoHashFound

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

    try:
        cached_filehash = get_cached_filehash(filename, hash_filepath=hash_filepath)

        logging.debug("Cached filehash is %s", cached_filehash)
    except NoHashFound:
        logging.warning("Hash not found in %s. File will be updated.", hash_filepath)
        with open(hash_filepath) as hash_file:
            hashes = json.load(hash_file)

        hashes[filename] = calculated_filehash

        with open(hash_filepath, "w") as hash_file:
            json.dump(hashes, hash_file, indent=2, sort_keys=True)

        raise

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


def zip_data_paths(
    filename,
    check_hash=True,
    redownload_on_hash_mismatch=True,
    delete_when_no_hash_found=True,
    url=None,
    extract_directory=None,
    hash_filepath=None,
):
    zip_filepath = data_path(
        filename,
        check_hash=check_hash,
        redownload_on_hash_mismatch=redownload_on_hash_mismatch,
        delete_when_no_hash_found=delete_when_no_hash_found,
        url=url,
        hash_filepath=hash_filepath,
    )

    if extract_directory is None:
        relative_extract_directory = pathlib.Path(os.path.splitext(filename)[0])
        extract_directory = get_data_dir().joinpath(relative_extract_directory)
    else:
        extract_directory = pathlib.Path(extract_directory)

    with zipfile.ZipFile(zip_filepath, "r") as zip_file:
        namelist = zip_file.namelist()

        for zipped_filename in namelist:
            if not extract_directory.joinpath(zipped_filename).exists():
                zip_file.extract(zipped_filename, path=extract_directory)

    resolved_paths = [
        extract_directory.joinpath(zipped_filename).resolve()
        for zipped_filename in namelist
    ]

    resolved_filepaths = [path for path in resolved_paths if path.is_file()]

    return resolved_filepaths
