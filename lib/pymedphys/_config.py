# Copyright (C) 2020 Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import pathlib

from pymedphys._imports import toml

is_cli = False


def config_dir_path() -> pathlib.Path:
    """Return the path of the PyMedPhys configuration directory, without creating it."""
    return pathlib.Path.home().joinpath(".pymedphys")


def get_config_dir() -> pathlib.Path:
    config_dir = config_dir_path()
    config_dir.mkdir(exist_ok=True)

    return config_dir


def get_config(path=None):
    if path is None:
        path = get_config_dir()

    path = pathlib.Path(path)

    config_path = path.joinpath("config.toml")
    visited = set()

    while True:
        resolved = config_path.resolve()
        if resolved in visited:
            raise ValueError(
                f"Config redirect loop: {config_path} was already visited."
            )
        visited.add(resolved)

        with open(config_path) as f:
            results = toml.load(f)

        try:
            redirect = results["redirect"]
        except KeyError:
            break

        # A relative redirect is relative to the file that contains it, not
        # to the directory PyMedPhys happened to be started from.
        config_path = config_path.parent.joinpath(redirect)

    return results
