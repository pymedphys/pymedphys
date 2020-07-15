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


from .dicom import dicom_cli
from .pinnacle import pinnacle_cli
from .quickcheck import quickcheck_cli


def experimental_cli(subparsers):
    experimental_parser = subparsers.add_parser(
        "experimental", help="Experimental tools."
    )
    experimental_subparsers = experimental_parser.add_subparsers(dest="experimental")

    dicom_cli(experimental_subparsers)
    pinnacle_cli(experimental_subparsers)
    quickcheck_cli(experimental_subparsers)

    return experimental_parser
