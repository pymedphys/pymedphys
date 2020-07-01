# Copyright (C) 2019 South Western Sydney Local Health District,
# University of New South Wales

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Export DICOM objects from raw Pinnacle data.
"""

from pymedphys._experimental.pinnacle import export_cli


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
