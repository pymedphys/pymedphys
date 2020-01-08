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
import os
import pathlib
import warnings
import zipfile

import pymedphys._utilities.filehash

from .resume import download_with_resume
from .zenodo import get_zenodo_file_urls

HERE = pathlib.Path(__file__).resolve().parent


def get_config_dir():
    config_dir = pathlib.Path.home().joinpath(".pymedphys")
    config_dir.mkdir(exist_ok=True)

    return config_dir


def get_data_dir():
    data_dir = get_config_dir().joinpath("data")
    data_dir.mkdir(exist_ok=True)

    return data_dir


@functools.lru_cache()
def get_url(filename):
    with open(HERE.joinpath("urls.json"), "r") as url_file:
        urls = json.load(url_file)

    try:
        url = urls[filename]
    except KeyError:
        raise ValueError("The file provided isn't within pymedphys' urls.json record.")

    return url


def data_path(filename, check_hash=True, redownload_on_hash_mismatch=True, url=None):
    filepath = get_data_dir().joinpath(filename)

    if not filepath.exists():
        if url is None:
            url = get_url(filename)

        download_with_resume(url, filepath)

    if check_hash:
        try:
            hash_agrees = data_file_hash_check(filename)
        except NoHashFound:
            return filepath.resolve()

        if not hash_agrees:
            if redownload_on_hash_mismatch:
                filepath.unlink()
                return data_path(filename, redownload_on_hash_mismatch=False)

            raise ValueError("The file on disk does not match the recorded hash.")

    return filepath.resolve()


class NoHashFound(KeyError):
    pass


def data_file_hash_check(filename):
    filename = str(filename).replace(os.sep, "/")

    with open(HERE.joinpath("hashes.json"), "r") as hash_file:
        hashes = json.load(hash_file)

    filepath = get_data_dir().joinpath(filename)
    calculated_filehash = pymedphys._utilities.filehash.hash_file(  # pylint: disable = protected-access
        filepath
    )

    try:
        cached_filehash = hashes[filename]
    except KeyError:
        warnings.warn("Hash not found in hashes.json. File will be updated.")
        hashes[filename] = calculated_filehash

        with open(HERE.joinpath("hashes.json"), "w") as hash_file:
            json.dump(hashes, hash_file, indent=2, sort_keys=True)

        raise NoHashFound

    return cached_filehash == calculated_filehash


def zenodo_data_paths(record_name, check_hash=True, redownload_on_hash_mismatch=True):
    file_urls = get_zenodo_file_urls(record_name)

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
    filename, check_hash=True, redownload_on_hash_mismatch=True, url=None
):
    zip_filepath = data_path(
        filename,
        check_hash=check_hash,
        redownload_on_hash_mismatch=redownload_on_hash_mismatch,
        url=url,
    )
    relative_extract_directory = pathlib.Path(os.path.splitext(filename)[0])
    extract_directory = get_data_dir().joinpath(relative_extract_directory)

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
