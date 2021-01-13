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

import json
import os
import shutil
import subprocess
from glob import glob

WHITELIST = (
    "pymedphys_base",
    "pymedphys_coordsandscales",
    "pymedphys_dicom",
    "pymedphys_fileformats",
    "pymedphys_utilities",
    "pymedphys_mudensity",
    "pymedphys_gamma",
    "pymedphys",
)

# ALLOWED_EXTERNAL = (
#     "numpy",
#     "matplotlib",
#     "pydicom",
#     "pandas",
#     "packaging"
# )


def build_wheels_with_yarn():
    yarn = shutil.which("yarn")
    subprocess.call([yarn, "pypi:clean"])
    for package in WHITELIST:
        subprocess.call(
            [yarn, "lerna", "run", "pypi:build", "--scope={}".format(package)]
        )


def copy_wheels(packages_dir, new_dir):
    wheel_filepaths = glob(os.path.join(packages_dir, "*", "dist", "*.whl"))

    pymedphys_wheel_urls = []
    for filepath in wheel_filepaths:
        filename = os.path.basename(filepath)
        if not filename.split("-")[0] in WHITELIST:
            continue

        pymedphys_wheel_urls.append(filename)
        new_filepath = os.path.join(new_dir, filename)
        shutil.copy(filepath, new_filepath)

    filenames_filepath = os.path.join(new_dir, "paths.json")
    with open(filenames_filepath, "w") as filenames_file:
        json.dump(pymedphys_wheel_urls, filenames_file)
