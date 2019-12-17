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


"""A command line interface for the management of log files.

Requires two configuration csv files detailed as following:

``config_mosaiq_sql.csv``
-------------------------

::

                  , Timezone        , Mosaiq SQL Server (Hostname:Port)
    a_centre      , Australia/Sydney, mosaiq:1433
    another_centre, Australia/Sydney, another-mosaiq:1433


``config_linac_details.csv``
----------------------------

::

        , Centre        , IP
    1234, a_centre      , 192.168.150.40
    1236, a_centre      , 192.168.150.41
    1238, another_centre, 10.0.0.40
"""


from pymedphys.labs.managelogfiles.orchestration import orchestration_cli


def logfile_cli(subparsers):
    logfile_parser = subparsers.add_parser(
        "logfile", help="A toolbox for managing logfiles."
    )
    logfile_subparsers = logfile_parser.add_subparsers(dest="logfile")

    logfile_orchestration(logfile_subparsers)


def logfile_orchestration(logfile_subparsers):
    parser = logfile_subparsers.add_parser(
        "orchestration",
        help=(
            "Manages the orchestration of Elekta Linac fetching logfiles "
            "from their backup directories and then indexing the collected "
            "files via Mosaiq SQL queries. "
            "Designed to be scheduled to run nightly or manually after an "
            "unscheduled backup. Requires two "
            "configuration csv files to be created, one for Mosaiq SQL "
            "configuration and the other for logfile configuration. See "
            "documentation for specification of the configuration files."
        ),
    )

    parser.add_argument(
        "data_directory", type=str, help="The path for storing the indexed log files."
    )

    parser.add_argument(
        "-m",
        "--mosaiq_sql",
        type=str,
        default=None,
        help=(
            "Define a custom path for the Mosaiq SQL configuration file. "
            "Defaults to ``{data_directory}/config_mosaiq_sql.csv``"
        ),
    )
    parser.add_argument(
        "-l",
        "--linac_details",
        type=str,
        default=None,
        help=(
            "Define a custom path for the Linac configuration file. "
            "Defaults to ``{data_directory}/config_linac_details.csv``"
        ),
    )

    parser.set_defaults(func=orchestration_cli)
