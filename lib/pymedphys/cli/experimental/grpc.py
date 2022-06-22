# Copyright (C) 2022 Simon Biggs

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from pymedphys._experimental._grpc import main


def grpc_cli(subparsers):
    grpc_parser = subparsers.add_parser(
        "grpc", help="Starts a gRPC server built to create alternative language APIs."
    )

    grpc_parser.add_argument(
        "token",
        help=(
            "Defining the secret token that the client will need to "
            "provide to secure the localhost socket communications."
        ),
    )

    grpc_parser.set_defaults(func=start)

    return grpc_parser


def start(args):
    main.start(token=args.token)
