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
import sys

from .app import app_cli
from .dicom import dicom_cli
from .docker import docker_cli
from .logfile import logfile_cli
from .pinnacle import pinnacle_cli
from .trf import trf_cli


class DefaultHelpParser(argparse.ArgumentParser):
    def error(self, message):
        sys.stderr.write("error: %s\n" % message)
        self.print_help()
        sys.exit(2)


def define_parser():
    parser = DefaultHelpParser(prog="pymedphys")
    subparsers = parser.add_subparsers()

    app_cli(subparsers)
    dicom_cli(subparsers)
    docker_cli(subparsers)
    logfile_cli(subparsers)
    trf_cli(subparsers)
    pinnacle_cli(subparsers)

    return parser


def pymedphys_cli():
    parser = define_parser()

    args = parser.parse_args()

    if hasattr(args, "func"):
        args.func(args)
    else:
        subparser_names = [
            attribute for attribute in dir(args) if not attribute.startswith("_")
        ]

        if not subparser_names:
            parser.print_help()
        else:
            assert len(subparser_names) == 1

            subparser_name = subparser_names[0]
            assert getattr(args, subparser_name) is None

            parser.parse_args([subparser_name, "--help"])
