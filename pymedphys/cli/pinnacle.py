# Copyright (C) 2019 South Western Sydney Local Health District,
# University of New South Wales

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

"""Export DICOM objects from raw Pinnacle data.
"""

from pymedphys.labs.pinnacle import export_cli


def pinnacle_cli(subparsers):
    pinnacle_parser = subparsers.add_parser(
        "pinnacle", help="A toolbox to export raw Pinnacle data to DICOM."
    )
    pinnacle_subparsers = pinnacle_parser.add_subparsers(dest="pinnacle")

    export_pinnacle(pinnacle_subparsers)

    return pinnacle_parser


def export_pinnacle(pinnacle_subparsers):
    parser = pinnacle_subparsers.add_parser("export", help="Export a raw file to DICOM")

    parser.add_argument(
        "input_path",
        type=str,
        help=(
            "Root Patient directory of raw Pinnacle data (directory "
            "containing the 'Patient' file). Alternatively a TAR archive "
            "can be supplied."
        ),
    )

    parser.add_argument(
        "-o",
        "--output-directory",
        help=("Directory in which to generate DICOM objects."),
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help=("Flag to output debug information."),
    )

    parser.add_argument(
        "-l",
        "--list",
        action="store_true",
        help=("List all plans and trials available."),
    )

    parser.add_argument(
        "-m",
        "--modality",
        action="append",
        default=[],
        help=("Modalities to export (CT exports the plans primary " "planning CT)."),
    )

    parser.add_argument(
        "-p",
        "--plan",
        help=(
            "The name of the plan to export (first plan will be "
            "exported by default)."
        ),
    )

    parser.add_argument(
        "-t",
        "--trial",
        help=(
            "The name of the trial to export (first trial will be "
            "exported by default)."
        ),
    )

    parser.add_argument(
        "-i",
        "--image",
        help=(
            "The UID of an image series you would like to export "
            "(or 'all' to export all images)."
        ),
    )

    parser.add_argument(
        "-u", "--uid-prefix", help=("Prefix to use for generated UIDs.")
    )

    parser.set_defaults(func=export_cli)
