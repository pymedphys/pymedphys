import os
from glob import glob
import subprocess
import json
from copy import copy, deepcopy

import networkx as nx

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


def create_dot_file_contents(glob_string):
    package_dirs = list(map(os.path.dirname, glob(glob_string)))
    internal_packages = [
        os.path.basename(directory) for directory in package_dirs]

    dependencies_from_pydeps = {}
    for directory in package_dirs:
        package = os.path.basename(directory)
        dependencies_from_pydeps[package] = json.loads(subprocess.run(
            ["pydeps", directory, "--external"],
            stdout=subprocess.PIPE).stdout)

    dependencies_set = {
        package: {
            dependency for dependency in dependency_list
            if dependency in internal_packages
        }
        for package, dependency_list in dependencies_from_pydeps.items()
    }

    dag = nx.DiGraph()

    for key, values in dependencies_set.items():
        dag.add_node(key)
        dag.add_nodes_from(values)
        edge_tuples = [
            (key, value) for value in values
        ]
        dag.add_edges_from(edge_tuples)

    assert nx.is_directed_acyclic_graph(dag)

    topological = list(nx.topological_sort(dag))

    minimal_deps = {}

    for package in topological[::-1]:
        if package in internal_packages:
            already_dependend_on = set()
            package_decendants = nx.descendants(dag, package)
            for dependency in package_decendants:
                if dependency in minimal_deps.keys():
                    for already_in in nx.descendants(dag, dependency):
                        already_dependend_on.add(already_in)

            minimal_deps[package] = package_decendants.difference(
                already_dependend_on)

    minimal_dag = nx.DiGraph()

    for package in minimal_deps.keys():
        minimal_dag.add_node(package)

    for package, dependencies in minimal_deps.items():

        edge_tuples = [
            (package, dependency) for dependency in dependencies
        ]

        minimal_dag.add_edges_from(edge_tuples)

    topological = list(nx.topological_sort(minimal_dag))

    level_map = {}
    for package in topological[::-1]:
        depencencies = nx.descendants(minimal_dag, package)
        levels = {0}
        for dependency in depencencies:
            try:
                levels.add(level_map[dependency])
            except KeyError:
                pass
        max_level = max(levels)
        level_map[package] = max_level + 1

    levels = {
        i + 1: []
        for i in range(max(level_map.values()))
    }
    for package, level in level_map.items():
        levels[level].append(package)

    clusters = ""

    for i in range(max(level_map.values())):
        level = i + 1
        cluster_packages = ';\n        '.join(levels[level])
        clusters += """
        subgraph cluster_{} {{
            {};
            label = "Level {}";
            style = dashed;
            color = grey80;
        }}
        """.format(i, cluster_packages, level)

    edges = ""

    for edge in minimal_dag.edges():
        edges += "    {} -> {};\n".format(*edge)

    dot_file_contents = """
    strict digraph  {{

        rankdir = LR;
        node [
            shape = box;
            width = 3;
        ];
        splines = polyline;

    {}
    {}
    }}
    """.format(clusters, edges)

    return dot_file_contents
