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
import ast
import os

from stdlib_list import stdlib_list

STDLIB = set(stdlib_list())

IMPORT_TYPES = {
    type(ast.parse("import george").body[0]),  # type: ignore
    type(ast.parse("import george as macdonald").body[0]),  # type: ignore
}

IMPORT_FROM_TYPES = {
    type(ast.parse("from george import macdonald").body[0])  # type: ignore
}

ALL_IMPORT_TYPES = IMPORT_TYPES.union(IMPORT_FROM_TYPES)

CONVERSIONS = {
    "attr": "attrs",
    "PIL": "Pillow",
    "Image": "Pillow",
    "mpl_toolkits": "matplotlib",
    "dateutil": "python_dateutil",
    "skimage": "scikit-image",
    "yaml": "PyYAML",
}


def get_imports(filepath, relative_filepath, internal_packages, depth):
    with open(filepath, "r") as file:
        data = file.read()

    parsed = ast.parse(data)
    imports = [node for node in ast.walk(parsed) if type(node) in ALL_IMPORT_TYPES]

    stdlib_imports = set()
    external_imports = set()
    internal_package_imports = set()
    internal_module_imports = set()
    internal_file_imports = set()

    def get_base_converted_module(name):
        name = name.split(".")[0]

        try:
            name = CONVERSIONS[name]
        except KeyError:
            pass

        return name

    def add_level_0(name):
        base_converted = get_base_converted_module(name)

        if base_converted in STDLIB:
            stdlib_imports.add(base_converted)
        elif base_converted in internal_packages:
            internal_package_imports.add(name)
        else:
            external_imports.add(base_converted)

    for an_import in imports:

        if type(an_import) in IMPORT_TYPES:
            for alias in an_import.names:
                add_level_0(alias.name)

        elif type(an_import) in IMPORT_FROM_TYPES:
            if an_import.level == 0:
                add_level_0(an_import.module)
            elif an_import.level == 1 and depth == 2:
                module_path = relative_filepath.split(os.sep)[0:2] + [an_import.module]
                internal_file_imports.add(".".join(module_path))
            elif (an_import.level == 1 and depth == 1) or (
                an_import.level == 2 and depth == 2
            ):
                module_path = relative_filepath.split(os.sep)[0:1] + [an_import.module]
                internal_module_imports.add(".".join(module_path))
            else:
                raise ValueError(
                    "Unexpected depth and import level of relative " "import"
                )

        else:
            raise TypeError("Unexpected import type")

    return {
        "stdlib": stdlib_imports,
        "external": external_imports,
        "internal_package": internal_package_imports,
        "internal_module": internal_module_imports,
        "internal_file": internal_file_imports,
    }
