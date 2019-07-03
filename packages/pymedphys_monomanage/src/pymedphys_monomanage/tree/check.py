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
import sys
import json
import subprocess
import shutil

from .build import PackageTree


def serialise_imports(imports):
    new_imports = {}
    for module_path_raw, values in imports.items():
        module_path = module_path_raw.replace(os.sep, '/')
        new_imports[module_path] = {}

        for where, a_set in values.items():
            new_imports[module_path][where] = sorted(list(a_set))

    return json.dumps(new_imports, sort_keys=True, indent=2)


def is_imports_json_up_to_date(directory):
    packages = os.path.join(directory, 'packages')
    imports_json = os.path.join(directory, 'imports.json')

    with open(imports_json) as file:
        data = json.load(file)

    file_data = json.dumps(data, sort_keys=True, indent=2)
    calced_data = serialise_imports(PackageTree(packages).imports)

    return file_data == calced_data


def commit_hook(directory):
    if not is_imports_json_up_to_date(directory):

        print(
            "\n    \033[1;31;1mThe dependency tree is out of date."
            "\033[1;32;1m Will now run `yarn tree` to update.\n"
            "    \033[1;34;1mYou will need to rerun `git commit` after "
            "this is complete.\033[0;0m\n"
        )

        sys.stdout.flush()

        yarn = shutil.which("yarn")
        git = shutil.which("git")

        subprocess.call([yarn, "tree"])

        subprocess.call([git, "add", "imports.json"])
        subprocess.call([git, "add", "dependencies.json"])
        subprocess.call([git, "add", "*package.json"])
        subprocess.call([git, "add", "*_install_requires.py"])
        subprocess.call([git, "add", "*.dot"])

        subprocess.call([git, "status"])

        print(
            "\n    \033[1;31;1mThe dependency tree was out of date.\n"
            "    \033[1;32;1mThe command `yarn tree` has been run for "
            "you.\n"
            "    \033[1;34;1mPlease rerun your commit.\033[0;0m\n"
            "    To prevent this message in the future run `yarn tree` "
            "whenever you change the dependency structure of "
            "PyMedPhys.\n")

        sys.exit(1)


def update_imports_json(directory):
    packages = os.path.join(directory, 'packages')
    imports_json = os.path.join(directory, 'imports.json')

    with open(imports_json, 'w') as file:
        file.write(serialise_imports(PackageTree(packages).imports))
