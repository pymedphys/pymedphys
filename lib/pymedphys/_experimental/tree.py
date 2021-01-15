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
import collections
import pathlib
from typing import Dict, MutableSet, Tuple

import networkx

from . import graphviz

HERE = pathlib.Path(__file__).parent.resolve()
LIB_PATH = HERE.parents[1]
SVG_PATH = LIB_PATH / "pymedphys" / "docs" / "trees"

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


def create_trees(svg_path: pathlib.Path = SVG_PATH, lib_path=LIB_PATH):
    module_dependencies = get_module_dependencies()
    internal_modules = set(module_dependencies.keys())

    module_api_map = _get_public_api_map(module_dependencies, internal_modules)

    module_to_url_map = _get_module_to_url_map(lib_path)

    for module_name, api_names in module_api_map.items():
        _create_svg(
            api_names,
            module_name,
            module_to_url_map,
            module_dependencies,
            internal_modules,
            output_directory=svg_path,
        )


def _get_module_to_url_map(lib_path):
    module_to_filepath_map = _get_module_to_filepath_map(lib_path)

    module_to_url_map = {
        module: _filepath_to_url(lib_path, filepath)
        for module, filepath in module_to_filepath_map.items()
    }

    return module_to_url_map


def _filepath_to_url(lib_path, filepath):
    relative_path = filepath.relative_to(lib_path)
    relative_path = str(relative_path).replace("\\", "/")
    url = f"https://github.com/pymedphys/pymedphys/tree/main/lib/{relative_path}"

    return url


def _get_module_to_filepath_map(lib_path):
    all_filepaths = list(lib_path.glob("**/*.py"))
    module_to_filepath_map = {
        _path_to_module(filepath, lib_path): filepath for filepath in all_filepaths
    }

    return module_to_filepath_map


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

    module_to_filepath_map = _get_module_to_filepath_map(lib_path)
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


def _get_exposed_internal_imports(module, module_dependencies, internal_modules):
    return [
        item
        for item in module_dependencies[module]
        if not item[2].startswith("_") and item[1] in internal_modules
    ]


def _get_public_api_map(module_dependencies, internal_modules, root="pymedphys"):
    top_level_api = _get_exposed_internal_imports(
        root, module_dependencies, internal_modules
    )
    module_apis = [item[0] for item in top_level_api if item[0] == item[1]]

    second_level_apis = {}
    for module in module_apis:
        second_level_apis[module] = _get_exposed_internal_imports(
            module, module_dependencies, internal_modules
        )

    exposure_module_maps = {
        f"{root}.{item[2]}": item[1] for item in top_level_api if item[0] != item[1]
    }

    for module, second_level_api in second_level_apis.items():
        exposure_module_maps = {
            **exposure_module_maps,
            **{f"{module}.{item[2]}": item[1] for item in second_level_api},
        }

    module_api_map = collections.defaultdict(lambda: [])
    for key, item in exposure_module_maps.items():
        module_api_map[item].append(key)

    return module_api_map


def _create_svg(
    api_names,
    module_name,
    module_to_url_map,
    module_dependencies,
    internal_modules,
    output_directory,
):
    di_graph = networkx.DiGraph()
    di_graph.add_node(module_name)
    traversal_nodes = {module_name}

    while traversal_nodes:
        node = traversal_nodes.pop()
        raw_dependencies = module_dependencies[node]

        for dependency in raw_dependencies:
            if dependency[1] in internal_modules:
                if not dependency[1] in di_graph:
                    traversal_nodes.add(dependency[1])
                    di_graph.add_node(dependency[1])

                di_graph.add_edge(node, dependency[1])

    node_urls = ""
    for node in di_graph.nodes:
        node_urls += (
            f'"{node}" '
            f'[label="{remove_prefix(node, "pymedphys.")}" '
            f'URL="{module_to_url_map[node]}"];\n'
        )

    for api_name in api_names:
        node_urls += f'"{api_name}" [URL="{module_to_url_map[module_name]}"];\n'
        di_graph.add_node(api_name)
        di_graph.add_edge(api_name, module_name)

    edges = ""
    for edge in di_graph.edges:
        edges += f'"{edge[0]}" -> "{edge[1]}";\n'

    graphviz.dot_string_to_svg(
        f"""
            digraph "{module_name}" {{
                {{
                    {node_urls}
                }}

                {edges}
            }}
        """,
        output_directory / f"{module_name}.svg",
    )


# https://stackoverflow.com/a/16892491/3912576
def remove_prefix(text, prefix):
    return text[text.startswith(prefix) and len(prefix) :]


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
