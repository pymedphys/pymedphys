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


"""A command line interface for the conversion of Elekta binary log files.
"""


from pymedphys._trf.decode.detect import detect_cli
from pymedphys._trf.decode.trf2csv import trf2csv_cli
from pymedphys._trf.manage.orchestration import orchestration_cli


def trf_cli(subparsers):
    trf_parser = subparsers.add_parser(
        "trf",
        help=("A toolbox to work with the Elekta Linac ``.trf`` binary log files."),
    )
    trf_subparsers = trf_parser.add_subparsers(dest="trf")
    trf_to_csv(trf_subparsers)
    trf_detect(trf_subparsers)
    trf_orchestration(trf_subparsers)

    return trf_parser


def trf_to_csv(trf_subparsers):
    parser = trf_subparsers.add_parser(
        "to-csv", help="Converts ``.trf`` files to ``.csv`` table and header files."
    )

    parser.add_argument(
        "filepaths",
        type=str,
        nargs="+",
        help=(
            "A list of ``.trf`` filepaths that you wish to convert to ``.csv``. "
            "Use of the glob wildcard * is enabled, which means that running "
            "``pymedphys trf to-csv *.trf`` will convert all logfiles in the "
            "current directory to csv files."
        ),
    )

    parser.set_defaults(func=trf2csv_cli)


def trf_detect(trf_subparsers):
    parser = trf_subparsers.add_parser(
        "detect", help="Attempts to detect trf encoding method."
    )

    parser.add_argument("filepath", type=str, help=("The filepath of a trf file."))

    parser.set_defaults(func=detect_cli)


def trf_orchestration(trf_subparsers):
    parser = trf_subparsers.add_parser(
        "orchestrate",
        help=(
            """A command line interface for the management of trf files.

Requires two configuration csv files detailed as following:

``config_mosaiq_sql.csv``
-------------------------

::

    ,Timezone,Mosaiq SQL Server (Hostname:Port)
    a_centre,Australia/Sydney,mosaiq:1433
    another_centre,Australia/Sydney,another-mosaiq:1433


``config_linac_details.csv``
----------------------------

::

    ,Centre,IP
    1234,a_centre,192.168.150.40
    1236,a_centre,192.168.150.41
    1238,another_centre,10.0.0.40
"""
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
