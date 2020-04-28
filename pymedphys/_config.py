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


def get_config_dir():
    config_dir = pathlib.Path.home().joinpath(".pymedphys")
    config_dir.mkdir(exist_ok=True)

    return config_dir


def get_config(path=None):
    if path is None:
        path = get_config_dir()

    path = pathlib.Path(path)

    config_path = path.joinpath("config.toml")

    while True:
        with open(config_path, "r") as f:
            results = toml.load(f)

        try:
            config_path = pathlib.Path(results["redirect"])
        except KeyError:
            break

    return results
