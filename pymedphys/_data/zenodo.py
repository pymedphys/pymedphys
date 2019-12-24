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
import urllib.request
import warnings
import zipfile

import tqdm

import pymedphys._utilities.filehash

HERE = pathlib.Path(__file__).resolve().parent


class DownloadProgressBar(tqdm.tqdm):
    def update_to(self, b=1, bsize=1, tsize=None):
        if tsize is not None:
            self.total = tsize
        self.update(b * bsize - self.n)


def get_config_dir():
    config_dir = pathlib.Path.home().joinpath(".pymedphys")
    config_dir.mkdir(exist_ok=True)

    return config_dir


def get_data_dir():
    data_dir = get_config_dir().joinpath("data")
    data_dir.mkdir(exist_ok=True)

    return data_dir


@functools.lru_cache()
def data_path(filename, check_hash=True, redownload_on_hash_mismatch=True):
    filepath = get_data_dir().joinpath(filename)

    if not filepath.exists():
        with open(HERE.joinpath("urls.json"), "r") as url_file:
            urls = json.load(url_file)

        try:
            url = urls[filename]
        except KeyError:
            raise ValueError(
                "The file provided isn't within pymedphys' urls.json record."
            )

        with DownloadProgressBar(
            unit="B", unit_scale=True, miniters=1, desc=url.split("/")[-1]
        ) as t:

            urllib.request.urlretrieve(url, filepath, reporthook=t.update_to)

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


def zip_data_paths(
    filename,
    check_hashes=True,
    redownload_on_hash_mismatch=True,
    reextract_on_hash_mismatch=True,
):
    zip_filepath = data_path(
        filename,
        check_hash=check_hashes,
        redownload_on_hash_mismatch=redownload_on_hash_mismatch,
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

    paths_are_files = [path.is_file() for path in resolved_paths]

    resolved_filepaths = [
        path for path, is_file in zip(resolved_paths, paths_are_files) if is_file
    ]

    if check_hashes:
        non_matching_filepaths = []

        for zipped_filename, is_file in zip(namelist, paths_are_files):
            if is_file:
                relative_filename = relative_extract_directory.joinpath(zipped_filename)

                try:
                    hash_agrees = data_file_hash_check(relative_filename)
                    if not hash_agrees:
                        non_matching_filepaths.append(relative_filename)
                except NoHashFound:
                    pass

        if reextract_on_hash_mismatch:
            for zipped_relative_filename in non_matching_filepaths:
                extract_directory.joinpath(zipped_relative_filename).unlink()

            return zip_data_paths(
                filename,
                redownload_on_hash_mismatch=redownload_on_hash_mismatch,
                reextract_on_hash_mismatch=False,
            )

        if non_matching_filepaths:
            raise ValueError(
                "At least one file on disk does not match the recorded hash."
            )

    return resolved_filepaths
