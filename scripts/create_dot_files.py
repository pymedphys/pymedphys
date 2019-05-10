import sys
import os
from glob import glob
import subprocess
import json
from copy import copy, deepcopy
import textwrap

import networkx as nx

sys.path.insert(0, '.')
from build_dependency_tree import build_tree  # nopep8

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODULE_PACKAGE_MAP = {
    'attr': 'attrs',
    'PIL': 'Pillow',
    'Image': 'Pillow',
    'mpl_toolkits': 'matplotlib',
    'docker': None,
    'collections': None,
    'dateutil': None
}


def create_all():
    full_graph()
    trimmed_graph()


def full_graph():
    tree = build_tree()
    internal_packages = tuple(tree.keys())
    dag = nx.DiGraph()

    for key, values in tree.items():
        dag.add_node(key)
        dag.add_nodes_from(values['internal'])
        dag.add_nodes_from(values['external'])
        edge_tuples = [
            (key, value) for value in values['internal']
        ]
        dag.add_edges_from(edge_tuples)
        edge_tuples = [
            (key, value) for value in values['external']
        ]
        dag.add_edges_from(edge_tuples)

    levels = get_levels(dag, internal_packages)
    dot_contents = build_dot_contents(dag, levels)
    save_dot_file(dot_contents, 'graph_full.dot')


def trimmed_graph():
    tree = build_tree()
    tree.pop('pymedphys')
    internal_packages = tuple(tree.keys())

    dag = nx.DiGraph()

    for key, values in tree.items():
        dag.add_node(key)
        dag.add_nodes_from(values['internal'])
        edge_tuples = [
            (key, value) for value in values['internal']
        ]
        dag.add_edges_from(edge_tuples)

    levels = get_levels(dag, internal_packages)
    dot_contents = build_dot_contents(dag, levels)
    save_dot_file(dot_contents, 'graph_trimmed.dot')


def save_dot_file(dot_contents, filename):
    dot_filepath = os.path.join(ROOT, filename)
    with open(dot_filepath, 'w') as file:
        file.write(dot_contents)

    svg_filepath = os.path.splitext(dot_filepath)[0] + ".svg"

    subprocess.call(["dot", "-Tsvg", dot_filepath, "-o", svg_filepath])


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


def build_dot_contents(dag, levels):
    clusters = ""

    for level in range(max(levels.keys()) + 1):
        if levels[level]:
            cluster_packages = ';\n                '.join(levels[level])
            clusters += textwrap.indent(textwrap.dedent("""
            subgraph cluster_{0} {{
                {1};
                label = "Level {0}";
                style = dashed;
                color = grey80;
            }}
            """.format(level, cluster_packages)), '        ')

    edges = ""

    for edge in dag.edges():
        edges += "        {} -> {};\n".format(*edge)

    dot_file_contents = textwrap.dedent("""\
    strict digraph  {{

        rankdir = LR;
        node [
            shape = box;
            width = 3;
        ];
        splines = spline;
    {}\n{}    }}
    """.format(clusters, edges))

    return dot_file_contents
