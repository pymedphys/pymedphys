import sys
import os
from glob import glob
import subprocess
import json
from copy import copy, deepcopy
import textwrap
import shutil

import networkx as nx

from .build import build_tree

ROOT = os.getcwd()


def draw_all(save_directory):
    # full_graph(save_directory)
    trimmed_graph(save_directory)


# def full_graph(save_directory):
#     tree = build_tree()
#     internal_packages = tuple(tree.keys())
#     dag = nx.DiGraph()

#     for key, values in tree.items():
#         dag.add_node(key)
#         dag.add_nodes_from(values['internal'])
#         dag.add_nodes_from(values['external'])
#         edge_tuples = [
#             (key, value) for value in values['internal']
#         ]
#         dag.add_edges_from(edge_tuples)
#         edge_tuples = [
#             (key, value) for value in values['external']
#         ]
#         dag.add_edges_from(edge_tuples)

#     levels = get_levels(dag, internal_packages)
#     dot_contents = build_dot_contents(dag, levels)
#     save_dot_file(dot_contents, save_directory, 'graph_full.dot')


def trimmed_graph(save_directory):
    tree = build_tree()
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


def save_dot_file(dot_contents, outfilepath):
    with open("temp.dot", 'w') as file:
        file.write(dot_contents)

    os.system("cat temp.dot | tred | dot -Tsvg -o temp.svg")
    os.remove("temp.dot")

    shutil.move("temp.svg", outfilepath)



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

    for node in dag.nodes():
        trimmed_node = remove_prefix(node, 'pymedphys_')
        nodes += "{};\n".format(trimmed_node)

    nodes = ""

    for level in range(max(levels.keys()) + 1):
        if levels[level]:
            trimmed_nodes = [
                remove_prefix(node, 'pymedphys_') for node in levels[level]
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
