# Copyright (C) 2020 Simon Biggs

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import pathlib
import subprocess

LIBRARY_ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS_DIR = LIBRARY_ROOT.joinpath("docs")


def build_docs(args):
    if args.output:
        output_directory = args.output
    else:
        output_directory = str(DOCS_DIR)

    if args.clean:
        subprocess.check_call(["jupyter-book", "clean", output_directory])
    else:
        subprocess.check_call(
            [
                "jupyter-book",
                "build",
                # "-W",
                # "-n",
                # "--keep-going",
                str(DOCS_DIR),
                "--path-output",
                output_directory,
            ]
        )
