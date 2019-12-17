# Copyright (C) 2019 Simon Biggs
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""A command line interface for the conversion of Elekta binary log files.
"""


from pymedphys._bundle import main


def bundle_cli(subparsers):
    bundle_parser = subparsers.add_parser(
        "bundle", help=("Bundle applications into an installable executable.")
    )
    bundle_subparsers = bundle_parser.add_subparsers(dest="bundle")
    bundle_lab_cli(bundle_subparsers)

    return bundle_parser


def bundle_lab_cli(bundle_subparsers):
    parser = bundle_subparsers.add_parser(
        "jupyterlab", help="Bundles JupyterLab into an installable executable."
    )

    parser.set_defaults(func=main)
