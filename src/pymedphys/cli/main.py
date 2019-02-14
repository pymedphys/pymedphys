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


import argparse

from ..dcm import adjust_machine_name_cli
from ..docker import server_cli


def pymedphys_cli():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()

    dicom_parser = subparsers.add_parser('dicom')
    dicom_subparsers = dicom_parser.add_subparsers()

    dicom_adjust_machine_name_parser = dicom_subparsers.add_parser(
        'adjust-machine-name')

    dicom_adjust_machine_name_parser.add_argument('input_file', type=str)
    dicom_adjust_machine_name_parser.add_argument('output_file', type=str)
    dicom_adjust_machine_name_parser.add_argument('new_machine_name', type=str)
    dicom_adjust_machine_name_parser.set_defaults(func=adjust_machine_name_cli)

    docker_parser = subparsers.add_parser('docker')
    docker_subparsers = docker_parser.add_subparsers()

    docker_server_parser = docker_subparsers.add_parser(
        'server'
    )

    docker_server_parser.set_defaults(func=server_cli)

    args = parser.parse_args()
    args.func(args)
