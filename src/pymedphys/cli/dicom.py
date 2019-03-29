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


from ..dicom import (
    adjust_machine_name_cli, adjust_RED_cli,
    adjust_RED_by_structure_name_cli)


def dicom_cli(subparsers):
    dicom_parser = subparsers.add_parser(
        'dicom',
        help='A toolbox for the manipulation of DICOM files.')
    dicom_subparsers = dicom_parser.add_subparsers(dest='dicom')

    dicom_adjust_machine_name(dicom_subparsers)
    dicom_adjust_rel_elec_density(dicom_subparsers)
    dicom_structure_name_RED_adjust(dicom_subparsers)

    return dicom_parser


def dicom_adjust_machine_name(dicom_subparsers):
    parser = dicom_subparsers.add_parser(
        'adjust-machine-name',
        help='Change the machine name in an RT plan DICOM file')

    parser.add_argument('input_file', type=str)
    parser.add_argument('output_file', type=str)
    parser.add_argument('new_machine_name', type=str)
    parser.set_defaults(func=adjust_machine_name_cli)


def dicom_adjust_rel_elec_density(dicom_subparsers):
    parser = dicom_subparsers.add_parser(
        'adjust-RED',
        help='Adjust the RED of structures within an RT structure DICOM file')

    parser.add_argument('input_file', type=str)
    parser.add_argument('output_file', type=str)
    parser.add_argument(
        'adjustment_map', type=str, nargs='+',
        help=(
            'An alternating list of structure name and then its associated '
            'RED. For example, '
            ' ``pymedphys dicom adjust-RED "structure with space" 1.5 another-struct 0.2``'
        ))

    parser.add_argument(
        '-i', '--ignore_missing_structure', action='store_true',
        help=(
            "By default if a provided structure name doesn't exist an error "
            "will be raised. This flag makes this error be ignored."
        ))

    parser.set_defaults(func=adjust_RED_cli)


def dicom_structure_name_RED_adjust(dicom_subparsers):
    parser = dicom_subparsers.add_parser(
        'adjust-RED-by-structure-name',
        help='Use structure name '
    )

    parser.add_argument('input_file', type=str, help='input_file')
    parser.add_argument('output_file', type=str, help='output_file')

    parser.set_defaults(func=adjust_RED_by_structure_name_cli)
