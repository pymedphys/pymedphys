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

import shutil
import subprocess

import pymedphys

from .paths import LIBRARY_PATH, REPO_ROOT

DOCS_PATH = LIBRARY_PATH.joinpath("docs")

DOCS_README = DOCS_PATH.joinpath("README.rst")
ROOT_README = REPO_ROOT.joinpath("README.rst")

ROOT_CHANGELOG = REPO_ROOT.joinpath("CHANGELOG.md")
DOCS_CHANGELOG = DOCS_PATH.joinpath("release-notes.md")

ROOT_CONTRIBUTING = REPO_ROOT.joinpath("CONTRIBUTING.md")
DOCS_CONTRIBUTING = DOCS_PATH.joinpath("contrib", "index.md")

FILES_TO_PRE_DOWNLOAD = ["original_dose_beam_4.dcm", "logfile_dose_beam_4.dcm"]


FILE_COPY_MAPPING = [
    # Reference document, copied-to location
    (ROOT_README, DOCS_README),
    (ROOT_CHANGELOG, DOCS_CHANGELOG),
    (ROOT_CONTRIBUTING, DOCS_CONTRIBUTING),
]


def build_docs(args):
    if args.output:
        output_directory = args.output
    else:
        output_directory = str(DOCS_PATH)

    if args.clean:
        subprocess.check_call(["jupyter-book", "clean", output_directory])

        return

    for original_path, target_path in FILE_COPY_MAPPING:
        shutil.copy(original_path, target_path)

    for file_name in FILES_TO_PRE_DOWNLOAD:
        # Implemented to remove the downloading prompts from appearing
        # within the online doc notebooks
        pymedphys.data_path(file_name)

    if args.prep:
        subprocess.check_call(["jupyter-book", "config", "sphinx", output_directory])

        return

    subprocess.check_call(
        [
            "jupyter-book",
            "build",
            # "-W",
            # "-n",
            # "--keep-going",
            str(DOCS_PATH),
            "--path-output",
            output_directory,
        ]
    )
