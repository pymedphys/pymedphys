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


"""This module exposes a CLI that is designed to be run once per day. It pulls
diagnostic zip files from the backups on the network share on the Linac.
This diagnostic zip file contains the Elekta trf logfiles within it.

This zip file is then extracted into the to be indexed directory, and indexing
is run.
"""

import pathlib

from pymedphys import _config

from .diagnostics_zips import (
    extract_diagnostic_zips_and_archive,
    fetch_system_diagnostics_multi_linac,
)
from .index import index_logfiles


def orchestration(config):
    logfile_data_directory = pathlib.Path(config["trf_logfiles"]["root_directory"])
    print("Data directory used:\n    {}\n".format(logfile_data_directory))

    linac_details = {}
    machine_ip_map = {}
    mosaiq_sql = {}
    for site_config in config["site"]:
        try:
            site_name = site_config["name"]
            mosaiq_config = site_config["mosaiq"]
            timezone = mosaiq_config["timezone"]
            hostname_port = f"{mosaiq_config['hostname']}:{mosaiq_config['port']}"
        except KeyError:
            continue

        mosaiq_sql[site_name] = {
            "timezone": timezone,
            "mosaiq_sql_server": hostname_port,
        }

        for linac_config in site_config["linac"]:
            try:
                linac_name = linac_config["name"]

                # TODO: Use of SAMBA IP is a work-a-round
                ip = linac_config["samba_ip"]
            except KeyError:
                continue

            machine_ip_map[linac_name] = ip
            linac_details[linac_name] = {"centre": site_name, "ip": ip}

    diagnostics_directory = logfile_data_directory.joinpath("diagnostics")

    print("Fetching diagnostic zip files from Linacs...")
    fetch_system_diagnostics_multi_linac(machine_ip_map, diagnostics_directory)

    print("Extracting trf logfiles from diagnostics zip files...")
    extract_diagnostic_zips_and_archive(logfile_data_directory)

    print("Indexing logfiles...")
    index_logfiles(mosaiq_sql, linac_details, logfile_data_directory)


def orchestration_cli(_):
    config = _config.get_config()
    orchestration(config)
