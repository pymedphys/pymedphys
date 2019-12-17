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

import argparse
import sys

from .app import app_cli
from .bundle import bundle_cli
from .dicom import dicom_cli
from .docker import docker_cli
from .jupyterlab import jupyter_cli
from .labs import labs_cli
from .logfile import logfile_cli
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
    bundle_cli(subparsers)
    dicom_cli(subparsers)
    docker_cli(subparsers)
    jupyter_cli(subparsers)
    labs_cli(subparsers)
    logfile_cli(subparsers)
    trf_cli(subparsers)

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
