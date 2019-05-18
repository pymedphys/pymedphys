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

from ..tree.build import PackageTree
from .utilities import save_dot_file, create_link

ROOT = os.getcwd()


def draw_packages(save_directory):
    print('pymedphys')
    tree = PackageTree('packages').package_dependencies_dict
    tree.pop('pymedphys')
    internal_packages = tuple(tree.keys())

    keys = list(tree.keys())
    keys.sort(reverse=True)

    dag = nx.DiGraph()

    for key in keys:
        values = tree[key]

        dag.add_node(key)
        dag.add_nodes_from(values['internal'])
        edge_tuples = [
            (key, value) for value in values['internal']
        ]
        dag.add_edges_from(edge_tuples)

    levels = get_levels(dag, internal_packages)
    dot_contents = build_dot_contents(dag, levels)
    save_dot_file(dot_contents, os.path.join(save_directory, 'pymedphys.svg'))


def get_levels(dag, internal_packages):
    topological = list(nx.topological_sort(dag))

    level_map = {}
    for package in topological[::-1]:
        if package not in internal_packages:
            level_map[package] = 0
        else:
            depencencies = nx.descendants(dag, package)
            levels = {0}
            for dependency in depencencies:
                if dependency in internal_packages:
                    try:
                        levels.add(level_map[dependency])
                    except KeyError:
                        pass
            max_level = max(levels)
            level_map[package] = max_level + 1

    levels = {
        level: []
        for level in range(max(level_map.values()) + 1)
    }
    for package, level in level_map.items():
        levels[level].append(package)

    return levels


def remove_prefix(text, prefix):
    if text.startswith(prefix):
        return text[len(prefix):]
    else:
        raise ValueError("Prefix not found.")


def build_dot_contents(dag, levels):
    nodes = ""

    for level in range(max(levels.keys()) + 1):
        if levels[level]:
            trimmed_nodes = [
                '"{}" {}'.format(
                    remove_prefix(node, 'pymedphys_'), create_link(node))
                for node in levels[level]
            ]

            grouped_packages = '; '.join(trimmed_nodes)
            nodes += """
            {{ rank = same; {}; }}
            """.format(grouped_packages)

    edges = ""

    for edge in dag.edges():
        trimmed_edge = [
            remove_prefix(node, 'pymedphys_') for node in edge
        ]
        edges += "{} -> {};\n".format(*trimmed_edge)

    dot_file_contents = """
        strict digraph  {{
            rankdir = LR;
            {}\n{}
        }}
    """.format(nodes, edges)

    return dot_file_contents
