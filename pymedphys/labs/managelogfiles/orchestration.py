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

import json
import os

from pymedphys._imports import pandas as pd

from .diagnostics_zips import (
    extract_diagnostic_zips_and_archive,
    fetch_system_diagnostics_multi_linac,
)
from .index import index_logfiles


def orchestration(mosaiq_sql, linac_details, logfile_data_directory):
    """Accepts a data directory for organising the log files as well as a
    machine map.

    Example
    -------

    mosaiq_sql = {
        "rccc": {
            "timezone": "Australia/Sydney",
            "mosaiq_sql_server": "mosaiq:1433"
        }
    }

    linac_details = {
        "2619": {
            "centre": "rccc",
            "ip": "10.0.0.1"
        },
        "2694": {
            "centre": "rccc",
            "ip": "10.0.0.2"
        }
    }

    data_directory = "path/to/logfile/storage"

    orchestration(mosaiq_sql, linac_details, data_directory)
    """

    machine_ip_map = {
        machine: machine_lookup["ip"]
        for machine, machine_lookup in linac_details.items()
    }

    diagnostics_directory = os.path.join(logfile_data_directory, "diagnostics")

    print("Fetching diagnostic zip files from Linacs...")
    fetch_system_diagnostics_multi_linac(machine_ip_map, diagnostics_directory)

    print("Extracting trf logfiles from diagnostics zip files...")
    extract_diagnostic_zips_and_archive(logfile_data_directory)

    print("Indexing logfiles...")
    index_logfiles(mosaiq_sql, linac_details, logfile_data_directory)


def orchestration_cli(args):
    data_directory = args.data_directory

    if args.mosaiq_sql is None:
        mosaiq_sql_path = os.path.join(data_directory, "config_mosaiq_sql.csv")
    else:
        mosaiq_sql_path = args.mosaiq_sql

    if args.linac_details is None:
        linac_details_path = os.path.join(data_directory, "config_linac_details.csv")

    else:
        linac_details_path = args.linac_details

    mosaiq_sql_table = pd.read_csv(mosaiq_sql_path, index_col=0)
    linac_details_table = pd.read_csv(linac_details_path, index_col=0)

    print("Data directory used:\n    {}\n".format(data_directory))

    mosaiq_sql = {
        str(centre): {
            "timezone": row["Timezone"],
            "mosaiq_sql_server": row["Mosaiq SQL Server (Hostname:Port)"],
        }
        for centre, row in mosaiq_sql_table.iterrows()
    }

    print(
        "Mosaiq SQL configuration used:\n{}\n".format(json.dumps(mosaiq_sql, indent=4))
    )

    linac_details = {
        str(machine): {"centre": row["Centre"], "ip": row["IP"]}
        for machine, row in linac_details_table.iterrows()
    }

    print("Linac configuration used:\n{}\n".format(json.dumps(linac_details, indent=4)))

    orchestration(mosaiq_sql, linac_details, data_directory)
