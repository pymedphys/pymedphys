# Copyright (C) 2020 Rafael Ayala

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Export csv data from QuickCheck measurements.
"""

from pymedphys.labs.quickcheck import export_cli


def quickcheck_cli(subparsers):
    quickcheck_parser = subparsers.add_parser(
        "quickcheck",
        help="A toolbox to retreive measurement data from PTW Quickcheck and write it to a csv file.",
    )
    quickcheck_subparsers = quickcheck_parser.add_subparsers(dest="quickcheck")

    export_quickcheck(quickcheck_subparsers)

    return quickcheck_parser


def export_quickcheck(quickcheck_subparsers):
    parser = quickcheck_subparsers.add_parser(
        "to-csv", help="Export Quickcheck data to .csv"
    )

    parser.add_argument(
        "ip", type=str, help="IP address or host name of Quickcheck device"
    )

    parser.add_argument("csv_path", type=str, help="file path for csv file.")

    parser.set_defaults(func=export_cli)
