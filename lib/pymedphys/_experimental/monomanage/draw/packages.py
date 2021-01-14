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

import os

import networkx as nx

ROOT = os.getcwd()


def draw_packages(save_directory):
    print("pymedphys")
    tree = PackageTree("packages").package_dependencies_dict
    tree.pop("pymedphys")
    internal_packages = tuple(tree.keys())

    keys = list(tree.keys())
    keys.sort(reverse=True)

    dag = nx.DiGraph()

    for key in keys:
        values = tree[key]

        dag.add_node(key)
        dag.add_nodes_from(values["internal"])
        edge_tuples = [(key, value) for value in values["internal"]]
        dag.add_edges_from(edge_tuples)

    levels = get_levels(dag, internal_packages)
    dot_contents = build_dot_contents(dag, levels)
    save_dot_file(dot_contents, os.path.join(save_directory, "pymedphys.svg"))


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

    levels = {level: [] for level in range(max(level_map.values()) + 1)}
    for package, level in level_map.items():
        levels[level].append(package)

    return levels


def remove_prefix(text, prefix):
    if text.startswith(prefix):
        return text[len(prefix) :]
    else:
        raise ValueError("Prefix not found.")


def build_dot_contents(dag, levels):
    nodes = ""

    for level in range(max(levels.keys()) + 1):
        if levels[level]:
            trimmed_nodes = [
                '"{}" {}'.format(remove_prefix(node, "pymedphys_"), create_link(node))
                for node in levels[level]
            ]

            grouped_packages = "; ".join(trimmed_nodes)
            nodes += """
            {{ rank = same; {}; }}
            """.format(
                grouped_packages
            )

    edges = ""

    for edge in dag.edges():
        trimmed_edge = [remove_prefix(node, "pymedphys_") for node in edge]
        edges += "{} -> {};\n".format(*trimmed_edge)

    dot_file_contents = """
        strict digraph  {{
            rankdir = LR;
            {}\n{}
        }}
    """.format(
        nodes, edges
    )

    return dot_file_contents
