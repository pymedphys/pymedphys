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
import webbrowser

LIBRARY_ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS_DIR = LIBRARY_ROOT.joinpath("docs")
DOCS_BUILD_DIR = DOCS_DIR.joinpath("_build")
DOCS_HTML_BUILD_DIR = DOCS_BUILD_DIR.joinpath("html")


def build_docs(args):
    subprocess.check_call(
        "pandoc CHANGELOG.md --from markdown --to rst -s -o release-notes.rst",
        cwd=DOCS_DIR,
        shell=True,
    )
    subprocess.check_call(
        "pandoc contributing/CONTRIBUTING.md --from markdown --to rst -s -o contributing/contributing.rst",
        cwd=DOCS_DIR,
        shell=True,
    )

    if args.output:
        output_directory = args.output
    else:
        output_directory = str(DOCS_HTML_BUILD_DIR)

    if args.live:
        webbrowser.open("http://127.0.0.1:8000")

        subprocess.check_call(
            " ".join(["sphinx-autobuild", str(DOCS_DIR), output_directory]), shell=True
        )

    else:
        subprocess.check_call(
            " ".join(["sphinx-build", "-W", str(DOCS_DIR), output_directory]),
            shell=True,
        )
