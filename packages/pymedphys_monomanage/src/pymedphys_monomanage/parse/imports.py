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
import ast

from stdlib_list import stdlib_list
STDLIB = set(stdlib_list())


IMPORT_TYPES = {
    type(ast.parse('import george').body[0]),  # type: ignore
    type(ast.parse('import george as macdonald').body[0])}  # type: ignore

IMPORT_FROM_TYPES = {
    type(ast.parse('from george import macdonald').body[0])  # type: ignore
}

ALL_IMPORT_TYPES = IMPORT_TYPES.union(IMPORT_FROM_TYPES)

CONVERSIONS = {
    'attr': 'attrs',
    'PIL': 'Pillow',
    'Image': 'Pillow',
    'mpl_toolkits': 'matplotlib',
    'dateutil': 'python_dateutil'
}


def get_imports(filepath, relative_filepath, internal_packages, depth):
    with open(filepath, 'r') as file:
        data = file.read()

    parsed = ast.parse(data)
    imports = [
        node for node in ast.walk(parsed) if type(node) in ALL_IMPORT_TYPES]

    stdlib_imports = set()
    external_imports = set()
    internal_package_imports = set()
    internal_module_imports = set()
    internal_file_imports = set()

    def get_base_converted_module(name):
        name = name.split('.')[0]

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
                module_path = (
                    relative_filepath.split(os.sep)[0:2] + [an_import.module])
                internal_file_imports.add('.'.join(module_path))
            elif (
                    (an_import.level == 1 and depth == 1) or
                    (an_import.level == 2 and depth == 2)):
                module_path = (
                    relative_filepath.split(os.sep)[0:1] + [an_import.module])
                internal_module_imports.add('.'.join(module_path))
            else:
                raise ValueError(
                    "Unexpected depth and import level of relative "
                    "import")

        else:
            raise TypeError("Unexpected import type")

    return {
        'stdlib': stdlib_imports,
        'external': external_imports,
        'internal_package': internal_package_imports,
        'internal_module': internal_module_imports,
        'internal_file': internal_file_imports
    }
