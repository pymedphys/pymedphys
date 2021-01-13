# Copyright (C) 2019,2021 Simon Biggs
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
import pathlib
from typing import Dict, MutableSet, Tuple

HERE = pathlib.Path(__file__).parent.resolve()
LIB_PATH = HERE.parents[1]

CONVERSIONS = {
    "attr": "attrs",
    "PIL": "Pillow",
    "Image": "Pillow",
    "mpl_toolkits": "matplotlib",
    "dateutil": "python_dateutil",
    "skimage": "scikit-image",
    "yaml": "PyYAML",
}

DependencyMap = Dict[str, MutableSet[Tuple[str, str, str]]]


def get_module_dependencies(
    lib_path=LIB_PATH,
    conversions=None,
    package_name="pymedphys",
    apipkg_name="pymedphys._imports",
) -> DependencyMap:
    """Determine PyMedPhys' dependency tree.

    Returns
    -------
    DependencyMap
        Each key represents an internal module within PyMedPhys. Each
        item is a set of tuples containing first the import within the
        module, second, the module which that import is pulled from,
        and last the variable name of that import within the module.
    """
    if conversions is None:
        conversions = CONVERSIONS

    all_filepaths = list(lib_path.glob("**/*.py"))
    module_to_filepath_map = {
        _path_to_module(filepath, lib_path): filepath for filepath in all_filepaths
    }
    all_internal_modules = set(module_to_filepath_map.keys())

    module_dependencies: DependencyMap = {}
    for module, filepath in module_to_filepath_map.items():
        raw_imports = _get_file_imports(filepath, lib_path, apipkg_name)

        module_imports = set()
        for an_import, name_in_module in raw_imports:
            try:
                module_name = _convert_import_to_module_name(
                    an_import, package_name, all_internal_modules, conversions
                )
            except ValueError as e:
                raise ValueError(
                    f"While parsing an import within {module} an error occurred"
                ) from e

            module_imports.add((an_import, module_name, name_in_module))

        module_dependencies[module] = module_imports

    return module_dependencies


def _convert_import_to_module_name(
    an_import, package_name, all_internal_modules, conversions
):
    if an_import.startswith(package_name):
        if an_import in all_internal_modules:
            return an_import
        else:
            adjusted_import = ".".join(an_import.split(".")[:-1])
            if not adjusted_import in all_internal_modules:
                raise ValueError(
                    f"An internal import `{an_import}` did not appear to exist"
                    "within the provided internal modules."
                )
            return adjusted_import
    else:
        adjusted_import = an_import.split(".")[0].replace("_", "-")
        try:
            adjusted_import = conversions[adjusted_import]
        except KeyError:
            pass

        return adjusted_import


def _path_to_module(filepath, library_path):
    relative_path = filepath.relative_to(library_path)
    if relative_path.name == "__init__.py":
        relative_path = relative_path.parent

    module_name = ".".join(relative_path.with_suffix("").parts)

    return module_name


def _get_file_imports(filepath, library_path, apipkg_name):
    relative_path = filepath.relative_to(library_path)

    with open(filepath, "r") as file:
        module_contents = file.read()

    parsed = ast.parse(module_contents)

    all_import_nodes = [
        node
        for node in ast.walk(parsed)
        if isinstance(node, (ast.Import, ast.ImportFrom))
    ]
    import_nodes = [node for node in all_import_nodes if isinstance(node, ast.Import)]
    import_from_nodes = [
        node for node in all_import_nodes if isinstance(node, ast.ImportFrom)
    ]

    imports = set()
    for node in import_nodes:
        for alias in node.names:
            imports.add((alias.name, _get_asname_with_fallback(alias)))

    for node in import_from_nodes:
        if node.level == 0:
            if node.module.startswith(apipkg_name):
                for alias in node.names:
                    imports.add((alias.name, _get_asname_with_fallback(alias)))
            else:
                for alias in node.names:
                    imports.add(
                        (
                            f"{node.module}.{alias.name}",
                            _get_asname_with_fallback(alias),
                        )
                    )

        else:
            module = ".".join(relative_path.parts[: -node.level])

            if node.module:
                module = f"{module}.{node.module}"

            for alias in node.names:
                imports.add(
                    (f"{module}.{alias.name}", _get_asname_with_fallback(alias))
                )

    return imports


def _get_asname_with_fallback(alias):
    if alias.asname:
        return alias.asname
    else:
        return alias.name
