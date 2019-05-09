import os
from glob import glob
import subprocess
import json
from copy import copy
import difflib

import networkx as nx

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEPENDENCIES_JSON_FILEPATH = os.path.join(ROOT, 'dependencies.json')


def build_tree():
    package_dirs = list(map(os.path.dirname, glob(os.path.join(
        ROOT, 'packages/pymedphys*/src/pymedphys*/__init__.py'))))

    internal_packages = [
        os.path.basename(directory) for directory in package_dirs]
    subpackages = copy(internal_packages)
    subpackages.remove('pymedphys')

    dependencies = {}
    for directory in package_dirs:
        package = os.path.basename(directory)
        dependencies[package] = json.loads(subprocess.run(
            ["pydeps", directory, "--external"],
            stdout=subprocess.PIPE).stdout)

    dependencies['pymedphys'] += subpackages

    all_modules = set()

    for dependency_list in dependencies.values():
        for item in dependency_list:
            all_modules.add(item)

    all_conversion = {
        module: module
        for module in all_modules
    }

    conversion = {
        **all_conversion,
        'attr': 'attrs',
        'PIL': 'Pillow',
        'Image': 'Pillow',
        'mpl_toolkits': 'matplotlib',
        'docker': None,
        'collections': None,
        'dateutil': None
    }

    dependencies_set = {
        package: {
            conversion[module]
            for module in dependency_list if conversion[module] is not None}
        for package, dependency_list in dependencies.items()
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

    tree = {}
    for package, dependencies in minimal_deps.items():
        external = [
            dependency for dependency in dependencies
            if dependency not in internal_packages
        ]
        internal = [
            dependency for dependency in dependencies
            if dependency in internal_packages
        ]

        external.sort()
        internal.sort()

        tree[package] = {
            "external": external,
            "internal": internal
        }

    return tree


def save_tree():
    tree = build_tree()

    with open(DEPENDENCIES_JSON_FILEPATH, 'r') as file:
        data = json.load(file)

    data['tree'] = tree

    with open(DEPENDENCIES_JSON_FILEPATH, 'w') as file:
        json.dump(data, file, indent=2, sort_keys=True)


def assert_tree_unchanged():
    tree = build_tree()

    with open(DEPENDENCIES_JSON_FILEPATH, 'r') as file:
        data = json.load(file)

    file_data = json.dumps(data['tree'], sort_keys=True, indent=2)
    calced_data = json.dumps(tree, sort_keys=True, indent=2)
    if file_data != calced_data:
        diff = difflib.unified_diff(
            file_data.split('\n'), calced_data.split('\n'))
        print('\n'.join(diff))
        raise AssertionError
