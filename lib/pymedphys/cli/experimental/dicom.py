# Copyright (C) 2020 Simon Biggs
# Copyright (C) 2023 Stuart Swerdloff


# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Experimental command line DICOM tools.

If you wish to utilise standard anonymisation, please instead use `pymedphys dicom anonymise`
as opposed to `pymedphys experimental dicom pseudonymise`."""

from pymedphys.cli import dicom

from pymedphys._experimental.pseudonymisation import anonymise_with_pseudo_cli


def dicom_cli(subparsers):
    dicom_parser, dicom_subparsers = dicom.set_up_dicom_cli(subparsers)
    pseudonymise(dicom_subparsers)

    return dicom_parser


def pseudonymise(dicom_subparsers):
    parser = dicom_subparsers.add_parser(
        "pseudonymise", help="Pseudonymise DICOM files."
    )

    parser.add_argument(
        "input_path",
        type=str,
        help=(
            "Input file or directory path. If a directory is "
            "supplied, all DICOM files within the directory and its "
            "subdirectories will be pseudonymised"
        ),
    )

    parser.add_argument(
        "-o",
        "--output_path",
        type=str,
        default=None,
        help=("Output file or directory path."),
    )

    parser.add_argument(
        "-d",
        "--delete_original_files",
        action="store_true",
        help=(
            "Use this flag to delete the original, non-pseudonymised "
            "files in the processed directory. Each original file "
            "will only be deleted if pseudonymisation completed "
            "successfully for that file."
        ),
    )

    parser.add_argument(
        "-f",
        "--preserve_filenames",
        action="store_true",
        help=(
            "Use this flag to preserve the original filenames in the "
            "pseudonymised DICOM filenames. Note that '_Anonymised.dcm' "
            "will still be appended. Use with caution, since DICOM "
            "filenames may contain identifying information"
        ),
    )

    parser.add_argument(
        "-c",
        "--clear_values",
        action="store_true",
        help=(
            "Use this flag to simply clear the values of all of the "
            "identifying elements in the pseudonymised DICOM files, "
            "as opposed to replacing them with 'dummy' values."
        ),
    )

    parser.add_argument(
        "-k",
        "--keywords_to_leave_unchanged",
        metavar="KEYWORD",
        type=str,
        nargs="*",
        help=(
            "A space-separated list of DICOM keywords (e.g. "
            "'PatientName') to exclude from pseudonymisation and "
            "error checking."
        ),
    )

    parser.add_argument(
        "-p",
        "--keep_private_tags",
        action="store_true",
        help=(
            "Use this flag to preserve private tags in the "
            "pseudonymised DICOM files."
        ),
    )

    unknown_tags_group = parser.add_mutually_exclusive_group()
    unknown_tags_group.add_argument(
        "-u",
        "--delete_unknown_tags",
        action="store_true",
        help=(
            "Use this flag to delete any unrecognised tags from the "
            "pseudonymised DICOM files."
        ),
    )
    unknown_tags_group.add_argument(
        "-i",
        "--ignore_unknown_tags",
        action="store_true",
        help=(
            "Use this flag to ignore any unrecognised tags in the "
            "pseudonymised DICOM files."
        ),
    )

    parser.set_defaults(func=anonymise_with_pseudo_cli)

    return parser
