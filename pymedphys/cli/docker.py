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


"""Creates a Docker server.

In the future this shall be easily configurable. In its current form it is
mostly only usable in one configuration. Watch this space for further
information.
"""


from ..docker import server_cli


def docker_cli(subparsers):
    docker_parser = subparsers.add_parser(
        "docker", help="Interface for creating a preconfigured docker server"
    )
    docker_subparsers = docker_parser.add_subparsers(dest="docker")

    docker_server_parser = docker_subparsers.add_parser(
        "server", help="Creates a preconfigured docker server."
    )

    docker_server_parser.set_defaults(func=server_cli)
