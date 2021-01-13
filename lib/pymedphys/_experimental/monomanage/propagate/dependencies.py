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

from ..clean import blacken_str

ROOT = os.getcwd()


def main():
    with open(os.path.join(ROOT, "dependencies.json"), "r") as file:
        dependencies_data = json.load(file)

    tree = dependencies_data["tree"]
    pypi_pins = dependencies_data["pins"]["pypi"]
    npm_pins = dependencies_data["pins"]["npm"]

    internal_packages = [
        os.path.basename(filepath)
        for filepath in glob(os.path.join(ROOT, "packages", "*"))
    ]

    try:
        assert set(internal_packages) == set(tree.keys())
    except AssertionError:
        print(
            "Internal packages not in tree: {}".format(
                set(internal_packages).difference(set(tree.keys()))
            )
        )
        print(
            "Tree packages not in internal: {}".format(
                set(tree.keys()).difference(set(internal_packages))
            )
        )
        raise

    try:
        assert set(internal_packages) == set(pypi_pins["internal"].keys())
    except AssertionError:
        internal = set(internal_packages)
        pypi = set(pypi_pins["internal"].keys())
        print("Internal packages not in pinned: {}".format(internal.difference(pypi)))
        print("Pinned packages not in internal: {}".format(pypi.difference(internal)))
        raise

    assert set(internal_packages) == set(npm_pins["internal"].keys())

    for package, dependency_store in tree.items():
        install_requires = []

        keys_to_keep = {"internal", "external"}
        for where, dependencies in dependency_store.items():
            if where in keys_to_keep:
                for dependency in dependencies:
                    try:
                        pin = " " + pypi_pins[where][dependency]
                    except KeyError:
                        pin = ""

                    requirement_string = dependency + pin
                    install_requires.append(requirement_string)

        install_requires.sort()

        install_requires_filepath = os.path.join(
            ROOT, "packages", package, "src", package, "_install_requires.py"
        )

        install_requires_contents = textwrap.dedent(
            """\
            install_requires = {}
        """
        ).format(json.dumps(install_requires, indent=4))

        install_requires_contents_blackened = blacken_str(install_requires_contents)

        with open(install_requires_filepath, "w") as file:
            file.write(install_requires_contents_blackened)

    for package, dependency_store in tree.items():
        internal_dependencies = {
            dependency: npm_pins["internal"][dependency]
            for dependency in dependency_store["internal"]
        }

        package_json_filepath = os.path.join(ROOT, "packages", package, "package.json")

        with open(package_json_filepath, "r") as file:
            data = json.load(file)

        try:
            external_dependencies = {
                package: pin
                for package, pin in data["dependencies"].items()
                if package not in internal_packages
            }
        except KeyError:
            external_dependencies = {}

        data["dependencies"] = {**internal_dependencies, **external_dependencies}

        with open(package_json_filepath, "w") as file:
            json.dump(data, file, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
