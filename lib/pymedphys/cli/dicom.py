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

"""Provides a various set of tools for DICOM header manipulation.
"""

from pymedphys._dicom.anonymise import anonymise_cli
from pymedphys._dicom.connect.listen import listen_cli
from pymedphys._dicom.connect.send import send_cli
from pymedphys._dicom.header import (
    adjust_machine_name_cli,
    adjust_RED_by_structure_name_cli,
    adjust_RED_cli,
)
from pymedphys._dicom.structure.merge import merge_contours_cli


def set_up_dicom_cli(subparsers):
    dicom_parser = subparsers.add_parser(
        "dicom", help="A toolbox for the manipulation of DICOM files."
    )
    dicom_subparsers = dicom_parser.add_subparsers(dest="dicom")

    anonymise(dicom_subparsers)
    merge_contours(dicom_subparsers)
    adjust_machine_name(dicom_subparsers)
    adjust_rel_elec_density(dicom_subparsers)
    adjust_RED_by_structure_name(dicom_subparsers)
    listen(dicom_subparsers)
    send(dicom_subparsers)

    return dicom_parser, dicom_subparsers


def dicom_cli(subparsers):
    dicom_parser, _ = set_up_dicom_cli(subparsers)

    return dicom_parser


def merge_contours(dicom_subparsers):
    parser = dicom_subparsers.add_parser(
        "merge-contours",
        help="Merge overlapping contours within a DICOM structure file",
    )

    parser.add_argument("input_file", type=str)
    parser.add_argument("output_file", type=str)
    parser.add_argument(
        "--structures",
        type=str,
        default=None,
        nargs="+",
        help=(
            "The structures for which to run the merge on. If not "
            "provided, then all structures will be processed."
        ),
    )
    parser.set_defaults(func=merge_contours_cli)


def adjust_machine_name(dicom_subparsers):
    parser = dicom_subparsers.add_parser(
        "adjust-machine-name", help="Change the machine name in an RT plan DICOM file"
    )

    parser.add_argument("input_file", type=str)
    parser.add_argument("output_file", type=str)
    parser.add_argument("new_machine_name", type=str)
    parser.set_defaults(func=adjust_machine_name_cli)


def adjust_rel_elec_density(dicom_subparsers):
    parser = dicom_subparsers.add_parser(
        "adjust-RED",
        help="Adjust the RED of structures within an RT structure DICOM file",
    )

    parser.add_argument("input_file", type=str)
    parser.add_argument("output_file", type=str)
    parser.add_argument(
        "adjustment_map",
        type=str,
        nargs="+",
        help=(
            "An alternating list of structure name and then its associated "
            "RED. For example, "
            "``pymedphys dicom adjust-RED`` ``input.dcm output.dcm`` "
            "``struct_name 1.5 another_struct_name 0.2``"
        ),
    )

    parser.add_argument(
        "-i",
        "--ignore_missing_structure",
        action="store_true",
        help=(
            "Use this flag to no longer raise an error when a defined "
            "structure name doesn't exist within the input DICOM file."
        ),
    )

    parser.set_defaults(func=adjust_RED_cli)


def adjust_RED_by_structure_name(dicom_subparsers):
    parser = dicom_subparsers.add_parser(
        "adjust-RED-by-structure-name",
        help=(
            "Use structure naming conventions to automatically "
            "adjust the relative electron density of a structure "
            "within a DICOM RT Structure set. For example, naming "
            "a structure ``a_structure_name RED=1.15`` will cause "
            "that structure to have an override of 1.15 applied."
        ),
    )

    parser.add_argument("input_file", type=str, help="input_file")
    parser.add_argument("output_file", type=str, help="output_file")

    parser.set_defaults(func=adjust_RED_by_structure_name_cli)


def anonymise(dicom_subparsers):
    parser = dicom_subparsers.add_parser("anonymise", help=("Anonymise DICOM files."))

    parser.add_argument(
        "input_path",
        type=str,
        help=(
            "Input file or directory path. If a directory is "
            "supplied, all DICOM files within the directory and its "
            "subdirectories will be anonymised"
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
            "Use this flag to delete the original, non-anonymised "
            "files in the processed directory. Each original file "
            "will only be deleted if anonymisation completed "
            "successfully for that file."
        ),
    )

    parser.add_argument(
        "-f",
        "--preserve_filenames",
        action="store_true",
        help=(
            "Use this flag to preserve the original filenames in the "
            "anonymised DICOM filenames. Note that '_Anonymised.dcm' "
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
            "identifying elements in the anonymised DICOM files, "
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
            "'PatientName') to exclude from anonymisation and "
            "error checking."
        ),
    )

    parser.add_argument(
        "-p",
        "--keep_private_tags",
        action="store_true",
        help=(
            "Use this flag to preserve private tags in the " "anonymised DICOM files."
        ),
    )

    unknown_tags_group = parser.add_mutually_exclusive_group()
    unknown_tags_group.add_argument(
        "-u",
        "--delete_unknown_tags",
        action="store_true",
        help=(
            "Use this flag to delete any unrecognised tags from the "
            "anonymised DICOM files."
        ),
    )
    unknown_tags_group.add_argument(
        "-i",
        "--ignore_unknown_tags",
        action="store_true",
        help=(
            "Use this flag to ignore any unrecognised tags in the "
            "anonymised DICOM files."
        ),
    )

    parser.set_defaults(func=anonymise_cli)

    return parser


def listen(dicom_subparsers):
    parser = dicom_subparsers.add_parser(
        "listen", help="Start a DICOM listener on the specified port"
    )

    parser.add_argument("port", type=int, help="The port on which to listen")
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        type=str,
        help="The host/IP to bind to",
    )
    parser.add_argument("-d", "--storage_directory", default=".", type=str, help="")
    parser.add_argument(
        "-a",
        "--aetitle",
        default="PYMEDPHYS",
        type=str,
        help="The AE Title of this listen service",
    )

    parser.set_defaults(func=listen_cli)


def send(dicom_subparsers):
    parser = dicom_subparsers.add_parser(
        "send", help="Send DICOM objects to a DICOM endpoint"
    )

    parser.add_argument("host", type=str, help="The host name/IP of the DICOM listener")
    parser.add_argument("port", type=int, help="The port of the DICOM listener")
    parser.add_argument("dcmfiles", help="Path to DICOM objects to send", nargs="*")

    parser.add_argument(
        "-a",
        "--aetitle",
        default="PYMEDPHYS",
        type=str,
        help="The Called AE Title",
    )
    parser.set_defaults(func=send_cli)
