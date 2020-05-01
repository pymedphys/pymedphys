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


from .pinnacle import pinnacle_cli


def labs_cli(subparsers):
    labs_parser = subparsers.add_parser(
        "labs", help="Highly experimental tools, not recommended for use."
    )
    labs_subparsers = labs_parser.add_subparsers(dest="labs")

    pinnacle_cli(labs_subparsers)

    return labs_parser
