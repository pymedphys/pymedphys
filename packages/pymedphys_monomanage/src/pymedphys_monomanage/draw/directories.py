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

import networkx as nx
from copy import copy

from ..tree import PackageTree
from .utilities import (
    save_dot_file, remove_prefix, get_levels, create_labels, create_href)


ROOT = os.getcwd()


def draw_directory_modules(save_directory):
    package_tree = PackageTree(os.path.join(ROOT, 'packages'))

    internal_packages = copy(package_tree.roots)
    internal_packages.remove('pymedphys')

    module_paths = [
        item
        for package in internal_packages
        for item in package_tree.digraph.neighbors(package)
    ]

    modules = {
        item: os.path.splitext(item)[0].replace(os.sep, '.')
        for item in module_paths
    }

    dependencies = {
        module.replace(os.sep, '.'): {
            '.'.join(item.split('.')[0:2])
            for item in
            package_tree.descendants_dependencies(module)['internal_module'] +
            package_tree.descendants_dependencies(module)['internal_package']
            # package_tree.descendants_dependencies(module)['internal_file'] +
            # list(package_tree.imports[module]['internal_module']) +
            # list(package_tree.imports[module]['internal_package']) +
            # list(package_tree.imports[module]['internal_file'])
        }
        for module in modules.keys()
    }

    dependents = {  # type: ignore
        key: set() for key in dependencies.keys()
    }
    try:
        for key, values in dependencies.items():
            for item in values:
                dependents[item].add(key)  # type: ignore
    except KeyError:
        print("\n{}".format(dependents.keys()))
        print("\n{}".format(dependencies))
        raise

    for package in internal_packages:
        build_graph_for_a_module(
            package, package_tree, dependencies, dependents, save_directory)


def build_graph_for_a_module(graphed_package, package_tree, dependencies,
                             dependents, save_directory):
    print(graphed_package)

    current_modules = sorted([
        item.replace(os.sep, '.')
        for item in package_tree.digraph.neighbors(graphed_package)
    ])

    outfilepath = os.path.join(
        save_directory, "{}.svg".format(graphed_package.replace(os.sep, '.')))

    if not current_modules:
        dot_file_contents = """
            strict digraph  {{
                subgraph cluster_0 {{
                    "";
                    label = "{}";
                    style = dashed;
                }}
            }}
        """.format(graphed_package)

        save_dot_file(dot_file_contents, outfilepath)
        return

    module_internal_relationships = {
        module.replace(os.sep, '.'): [
            '.'.join(item.split('.')[0:2])
            for item in
            package_tree.descendants_dependencies(module)['internal_module']
        ]
        for module in sorted(list(package_tree.digraph.neighbors(graphed_package)))
    }

    levels = get_levels(module_internal_relationships)

    internal_nodes = sorted(list(set(module_internal_relationships.keys())))
    external_nodes = set()
    for module in current_modules:
        external_nodes |= dependencies[module]
        external_nodes |= dependents[module]

    external_nodes = sorted(list(external_nodes))

    all_nodes = internal_nodes + external_nodes

    def simplify(text):
        text = remove_prefix(text, "{}.".format(graphed_package))
        text = remove_prefix(text, 'pymedphys_')

        return text

    label_map = {
        node: simplify(node)
        for node in all_nodes
    }

    nodes = ""

    for level in range(max(levels.keys()) + 1):
        if levels[level]:
            grouped_packages = '"; "'.join(sorted(list(levels[level])))
            nodes += """
            {{ rank = same; "{}"; }}
            """.format(grouped_packages)

    edges = ""
    current_packages = ""

    current_dependents = set()
    current_dependencies = set()

    for module in current_modules:
        current_packages += '"{}";\n'.format(module)

        for dependency in sorted(list(dependencies[module])):
            edges += '"{}" -> "{}";\n'.format(module, dependency)
            if not dependency in current_modules:
                current_dependencies.add(dependency)

        for dependent in sorted(list(dependents[module])):
            edges += '"{}" -> "{}";\n'.format(dependent, module)
            if not dependent in current_modules:
                current_dependents.add(dependent)

    external_ranks = ""
    if current_dependents:
        grouped_dependents = '"; "'.join(sorted(list(current_dependents)))
        external_ranks += '{{ rank = same; "{}"; }}\n'.format(
            grouped_dependents)

    if current_dependencies:
        grouped_dependencies = '"; "'.join(sorted(list(current_dependencies)))
        external_ranks += '{{ rank = same; "{}"; }}\n'.format(
            grouped_dependencies)

    external_labels = create_labels(label_map)

    dot_file_contents = """
        strict digraph  {{
            rankdir = LR;
            subgraph cluster_0 {{
                {}
                label = "{}";
                URL = "{}";
                style = dashed;
                {}
            }}
            {}
            {}
            {}
        }}
    """.format(
        current_packages, graphed_package, create_href(graphed_package),
        nodes, external_labels, external_ranks, edges)

    save_dot_file(dot_file_contents, outfilepath)
