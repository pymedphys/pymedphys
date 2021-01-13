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
import textwrap
from glob import glob

import semver

from ..clean import blacken_str

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(os.getcwd())))


def main():
    version_filepath = glob(os.path.join("src", "pymedphys*", "_version.py"))[0]
    package_name = os.path.split(os.path.dirname(version_filepath))[-1]

    with open("package.json", "r") as file:
        data = json.load(file)

    semver_string = data["version"]

    loaded_version_info = semver_string.replace(".", " ").replace("-", " ").split(" ")

    version_info = [int(number) for number in loaded_version_info[0:3]] + [
        "".join(loaded_version_info[3::])
    ]  # type: ignore

    __version__ = ".".join(map(str, version_info[:3])) + "".join(
        version_info[3:]
    )  # type: ignore

    version_file_contents = textwrap.dedent(
        """\
        version_info = {}
        __version__ = "{}"
    """.format(
            version_info, __version__
        )
    )

    version_file_contents_blackened = blacken_str(version_file_contents)

    with open(version_filepath, "w") as file:
        file.write(version_file_contents_blackened)

    semver_parsed = semver.parse(semver_string)

    if semver_parsed["major"] == 0:
        upper_limit = semver.bump_minor(semver_string)
        npm_version_prepend = "~"
    else:
        upper_limit = semver.bump_major(semver_string)
        npm_version_prepend = "^"

    dependencies_filepath = os.path.join(ROOT, "dependencies.json")

    with open(dependencies_filepath, "r") as file:
        dependencies_data = json.load(file)

    dependencies_data["pins"]["pypi"]["internal"][package_name] = ">= {}, < {}".format(
        __version__, upper_limit
    )
    dependencies_data["pins"]["npm"]["internal"][package_name] = "{}{}".format(
        npm_version_prepend, semver_string
    )

    with open(dependencies_filepath, "w") as file:
        json.dump(dependencies_data, file, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
