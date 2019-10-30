# Copyright (C) 2019 Cancer Care Associates

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version (the "AGPL-3.0+").

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License and the additional terms for more
# details.

# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

# ADDITIONAL TERMS are also included as allowed by Section 7 of the GNU
# Affero General Public License. These additional terms are Sections 1, 5,
# 6, 7, 8, and 9 from the Apache License, Version 2.0 (the "Apache-2.0")
# where all references to the definition "License" are instead defined to
# mean the AGPL-3.0+.

# You should have received a copy of the Apache-2.0 along with this
# program. If not, see <http://www.apache.org/licenses/LICENSE-2.0>.


import json
import pathlib
import urllib
import warnings

import pymedphys._utilities.filehash

HERE = pathlib.Path(__file__).resolve().parent


def get_config_dir():
    config_dir = pathlib.Path.home().joinpath(".pymedphys")
    config_dir.mkdir(exist_ok=True)

    return config_dir


def get_data_dir():
    data_dir = get_config_dir().joinpath("data")
    data_dir.mkdir(exist_ok=True)

    return data_dir


def get_file(filename):
    filepath = get_data_dir().joinpath(filename)

    with open(HERE.joinpath("hashes.json"), "r") as hash_file:
        hashes = json.load(hash_file)

    if not filepath.exists():
        with open(HERE.joinpath("urls.json"), "r") as url_file:
            urls = json.load(url_file)

        try:
            url = urls[filename]
        except KeyError:
            raise ValueError(
                "The file provided isn't within pymedphys' urls.json record."
            )

        urllib.request.urlretrieve(url, filepath)

    calculated_filehash = pymedphys._utilities.filehash.hash_file(  # pylint: disable = protected-access
        filepath
    )

    try:
        cached_filehash = hashes[filename]

        if cached_filehash != calculated_filehash:
            raise ValueError("The file on disk does not match the recorded hash.")
    except KeyError:
        warnings.warn("Hash not found in hashes.json. File will be updated.")
        hashes[filename] = calculated_filehash

        with open(HERE.joinpath("hashes.json"), "w") as hash_file:
            json.dump(hashes, hash_file)

    return filepath.resolve()
