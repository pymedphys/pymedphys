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

import pymedphys._icom.listener


def icom_cli(subparsers):
    icom_parser = subparsers.add_parser("icom")
    icom_subparsers = icom_parser.add_subparsers(dest="icom")

    icom_listen(icom_subparsers)

    return icom_parser


def icom_listen(icom_subparsers):
    parser = icom_subparsers.add_parser("listen")

    parser.add_argument("ip")
    parser.add_argument("directory")
    parser.set_defaults(
        func=pymedphys._icom.listener.listen_cli  # pylint: disable = protected-access
    )
