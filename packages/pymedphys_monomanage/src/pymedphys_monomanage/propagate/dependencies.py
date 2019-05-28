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
import textwrap
import json
from glob import glob

ROOT = os.getcwd()


def main():
    with open(os.path.join(ROOT, 'dependencies.json'), 'r') as file:
        dependencies_data = json.load(file)

    tree = dependencies_data['tree']
    pypi_pins = dependencies_data['pins']['pypi']
    npm_pins = dependencies_data['pins']['npm']

    internal_packages = [
        os.path.basename(filepath)
        for filepath in glob(os.path.join(ROOT, 'packages', '*'))
    ]

    try:
        assert set(internal_packages) == set(tree.keys())
    except AssertionError:
        print("Internal packages not in tree: {}".format(
            set(internal_packages).difference(set(tree.keys()))))
        print("Tree packages not in internal: {}".format(
            set(tree.keys()).difference(set(internal_packages))))
        raise

    try:
        assert set(internal_packages) == set(pypi_pins['internal'].keys())
    except AssertionError:
        internal = set(internal_packages)
        pypi = set(pypi_pins['internal'].keys())
        print("Internal packages not in pinned: {}".format(
            internal.difference(pypi)))
        print("Pinned packages not in internal: {}".format(
            pypi.difference(internal)))
        raise

    assert set(internal_packages) == set(npm_pins['internal'].keys())

    for package, dependency_store in tree.items():
        install_requires = []

        keys_to_keep = {'internal', 'external'}
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
            ROOT, "packages", package, "src", package, "_install_requires.py")

        install_requires_contents = textwrap.dedent("""\
            install_requires = {}
        """).format(json.dumps(install_requires, indent=4))

        with open(install_requires_filepath, 'w') as file:
            file.write(install_requires_contents)

    for package, dependency_store in tree.items():
        internal_dependencies = {
            dependency: npm_pins['internal'][dependency]
            for dependency in dependency_store['internal']
        }

        package_json_filepath = os.path.join(
            ROOT, "packages", package, "package.json")

        with open(package_json_filepath, 'r') as file:
            data = json.load(file)

        try:
            external_dependencies = {
                package: pin
                for package, pin in data['dependencies'].items()
                if package not in internal_packages
            }
        except KeyError:
            external_dependencies = {}

        data['dependencies'] = {
            **internal_dependencies,
            **external_dependencies
        }

        with open(package_json_filepath, 'w') as file:
            json.dump(data, file, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
