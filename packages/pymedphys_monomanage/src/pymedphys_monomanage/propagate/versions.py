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
import json
from glob import glob
import textwrap


import semver

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(os.getcwd())))


def main():
    version_filepath = glob(os.path.join(
        "src", "pymedphys*", "_version.py"))[0]
    package_name = os.path.split(os.path.dirname(version_filepath))[-1]

    with open('package.json', 'r') as file:
        data = json.load(file)

    semver_string = data['version']

    loaded_version_info = semver_string.replace(
        '.', ' ').replace('-', ' ').split(' ')

    version_info = [
        int(number)
        for number in loaded_version_info[0:3]
    ] + [''.join(loaded_version_info[3::])]  # type: ignore

    __version__ = '.'.join(
        map(str, version_info[:3])) + ''.join(version_info[3:])  # type: ignore

    version_file_contents = textwrap.dedent("""\
        version_info = {}
        __version__ = "{}"
    """.format(version_info, __version__))

    with open(version_filepath, 'w') as file:
        file.write(version_file_contents)

    semver_parsed = semver.parse(semver_string)

    if semver_parsed['major'] == 0:
        upper_limit = semver.bump_minor(semver_string)
        npm_version_prepend = "~"
    else:
        upper_limit = semver.bump_major(semver_string)
        npm_version_prepend = "^"

    dependencies_filepath = os.path.join(ROOT, "dependencies.json")

    with open(dependencies_filepath, 'r') as file:
        dependencies_data = json.load(file)

    dependencies_data['pins']['pypi']['internal'][package_name] = (
        ">= {}, < {}".format(__version__, upper_limit))
    dependencies_data['pins']['npm']['internal'][package_name] = (
        "{}{}".format(npm_version_prepend, semver_string))

    with open(dependencies_filepath, 'w') as file:
        json.dump(dependencies_data, file, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
