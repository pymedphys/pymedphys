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
import shutil
import subprocess

import networkx as nx


def save_dot_file(dot_contents, outfilepath):
    tred = shutil.which("tred")
    dot = shutil.which("dot")

    if not tred or not dot:
        print(
            "Graph not drawn, please install graphviz and add it to "
            "your path.\nOn Windows this is done with "
            "`choco install graphviz.portable`.\n")

        return

    with open("temp.dot", 'w') as file:
        file.write(dot_contents)

    try:
        tred_process = subprocess.Popen(
            [tred, 'temp.dot'], stdout=subprocess.PIPE)
        data = tred_process.stdout.read()
        tred_process.wait()
        with open("temp_reduced.dot", 'wb') as file:
            file.write(data)

        output = subprocess.check_output(
            [dot, '-Tsvg', 'temp_reduced.dot', '-o', 'temp.svg'])

        shutil.move("temp.svg", outfilepath)
        shutil.move("temp_reduced.dot", os.path.splitext(
            outfilepath)[0] + ".dot")
    finally:
        os.remove("temp.dot")


def remove_prefix(text, prefix):
    if text.startswith(prefix):
        return text[len(prefix):]
    else:
        return text


def get_levels(dependency_map):
    dag = dag_from_hashmap_of_lists(dependency_map)

    topological = list(nx.topological_sort(dag))

    level_map = {}
    for package in topological[::-1]:
        dependencies = nx.descendants(dag, package)
        levels = {0}
        for dependency in sorted(list(dependencies)):
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


def dag_from_hashmap_of_lists(dictionary):
    keys = list(dictionary.keys())
    keys.sort(reverse=True)

    dag = nx.DiGraph()

    for key in keys:
        values = sorted(dictionary[key], reverse=True)
        dag.add_node(key)
        dag.add_nodes_from(values)
        edge_tuples = [
            (key, value) for value in values
        ]
        dag.add_edges_from(edge_tuples)

    return dag


def remove_postfix(text, postfix):
    if text.endswith(postfix):
        return text[:-len(postfix)]
    else:
        return text


def convert_path_to_package(path):
    return remove_postfix(path.replace(os.sep, '.'), '.py')


def create_href(text):
    return '#{}'.format(text.replace('_', '-').replace('.', '-'))


def create_link(text):
    return '[URL="{}"]'.format(create_href(text))


def create_labels(label_map):
    labels = ""
    for node, label in label_map.items():
        labels += '"{}" [label="{}"] {};\n'.format(
            node, label, create_link(node))

    return labels
