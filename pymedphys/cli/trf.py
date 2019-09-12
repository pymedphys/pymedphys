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


"""A command line interface for the conversion of Elekta binary log files.
"""


from pymedphys._trf.trf2csv import trf2csv_cli


def trf_cli(subparsers):
    trf_parser = subparsers.add_parser(
        "trf",
        help=("A toolbox to work with the Elekta Linac ``.trf`` binary log files."),
    )
    trf_subparsers = trf_parser.add_subparsers(dest="trf")
    trf_to_csv(trf_subparsers)

    return trf_parser


def trf_to_csv(dicom_subparsers):
    parser = dicom_subparsers.add_parser(
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
