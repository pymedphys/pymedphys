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


import functools
import os
import pathlib
from typing import Callable, Dict

from pymedphys._imports import streamlit as st
from typing_extensions import Literal

from pymedphys import _config as pmp_config


@st.cache
def get_config(path=None):
    result = pmp_config.get_config(path=path)

    return result


def get_monaco_from_site_config(site_config):
    return pathlib.Path(site_config["monaco"]["focaldata"]).joinpath(
        site_config["monaco"]["clinic"]
    )


def get_export_directory_from_site_config(site_config, export_directory):
    return pathlib.Path(
        os.path.expanduser(site_config["export-directories"][export_directory])
    )


DirectoryConfigOptions = Literal[
    "monaco", "escan", "anonymised_monaco", "iviewdb", "icom"
]

DirectoriesForSite = Dict[DirectoryConfigOptions, pathlib.Path]


@st.cache
def get_site_directories(config) -> Dict[str, DirectoriesForSite]:
    """A config wrapper that retrieves a dictionary that maps site to directories.

    Returns
    -------
    site_directories
        A dictionary indexed by site. Each site has within it a
        dictionary that is indexed by directory type.

    """
    site_directory_functions: Dict[DirectoryConfigOptions, Callable] = {
        "monaco": get_monaco_from_site_config,
        "escan": functools.partial(
            get_export_directory_from_site_config, export_directory="escan"
        ),
        "anonymised_monaco": functools.partial(
            get_export_directory_from_site_config, export_directory="anonymised_monaco"
        ),
        "iviewdb": functools.partial(
            get_export_directory_from_site_config, export_directory="iviewdb"
        ),
        "icom": functools.partial(
            get_export_directory_from_site_config, export_directory="icom"
        ),
    }

    site_directories: Dict[str, DirectoriesForSite] = {}
    for site in config["site"]:
        site_name = site["name"]
        site_directories[site_name] = {}

        for key, func in site_directory_functions.items():
            try:
                site_directories[site_name][key] = func(site)
            except KeyError:
                pass

    return site_directories
