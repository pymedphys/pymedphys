# Copyright (C) 2019 Simon Biggs

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version (the "AGPL-3.0+").

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License and the additional terms for more
# details.

# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

# ADDITIONAL TERMS are also included as allowed by Section 7 of the GNU
# Affero General Public License. These additional terms are Sections 1, 5,
# 6, 7, 8, and 9 from the Apache License, Version 2.0 (the "Apache-2.0")
# where all references to the definition "License" are instead defined to
# mean the AGPL-3.0+.

# You should have received a copy of the Apache-2.0 along with this
# program. If not, see <http://www.apache.org/licenses/LICENSE-2.0>.


import os
import shutil
from glob import glob
import subprocess
import json


WHITELIST = (
    'pymedphys_base',
    'pymedphys_coordsandscales',
    'pymedphys_dicom',
    'pymedphys_fileformats',
    'pymedphys_utilities',
    'pymedphys_mudensity',
    'pymedphys_gamma',
    'pymedphys')


def build_wheels_with_yarn():
    yarn = shutil.which("yarn")
    subprocess.call([yarn, "pypi:clean"])
    for package in WHITELIST:
        subprocess.call(
            [yarn, "lerna", "run", "pypi:build", "--scope={}".format(package)])


def copy_wheels(packages_dir, new_dir):
    wheel_filepaths = glob(os.path.join(packages_dir, '*', 'dist', '*.whl'))

    pymedphys_wheel_urls = []
    for filepath in wheel_filepaths:
        filename = os.path.basename(filepath)
        if not filename.split('-')[0] in WHITELIST:
            continue

        pymedphys_wheel_urls.append(filename)
        new_filepath = os.path.join(new_dir, filename)
        shutil.copy(filepath, new_filepath)

    filenames_filepath = os.path.join(new_dir, 'paths.json')
    with open(filenames_filepath, 'w') as filenames_file:
        json.dump(pymedphys_wheel_urls, filenames_file)
