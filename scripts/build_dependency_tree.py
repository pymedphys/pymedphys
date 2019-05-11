import ast
import os
import json
from copy import copy
import difflib

import networkx as nx

from stdlib_list import stdlib_list
STDLIB = set(stdlib_list())

CONVERSIONS = {
    'attr': 'attrs',
    'PIL': 'Pillow',
    'Image': 'Pillow',
    'mpl_toolkits': 'matplotlib',
    'dateutil': 'python_dateutil'
}

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEPENDENCIES_JSON_FILEPATH = os.path.join(ROOT, 'dependencies.json')

IMPORT_TYPES = {
    type(ast.parse('import george').body[0]),  # type: ignore
    type(ast.parse('import george as macdonald').body[0])}  # type: ignore

IMPORT_FROM_TYPES = {
    type(ast.parse('from george import macdonald').body[0])  # type: ignore
}

ALL_IMPORT_TYPES = IMPORT_TYPES.union(IMPORT_FROM_TYPES)


def create_directory_digraph():
    dirtree = nx.DiGraph()

    exclude_dirs = {'node_modules', '__pycache__', 'dist'}
    exclude_files = {'__init__.py', '_version.py', '_install_requires.py'}
    packages_dir = os.path.join(ROOT, 'packages')

    for root, dirs, files in os.walk(packages_dir, topdown=True):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]

        if '__init__.py' in files:
            module_init = os.path.join(root, '__init__.py')
            files[:] = [f for f in files if f not in exclude_files]

            dirtree.add_node(module_init)
            parent_init = os.path.join(os.path.dirname(root), '__init__.py')
            if os.path.exists(parent_init):
                dirtree.add_edge(parent_init, module_init)

            for f in files:
                if f.endswith('.py'):
                    filepath = os.path.join(root, f)
                    dirtree.add_node(filepath)
                    dirtree.add_edge(module_init, filepath)

    return dirtree


def get_imports(filepath, internal_packages):
    with open(filepath, 'r') as file:
        data = file.read()

    parsed = ast.parse(data)
    imports = [
        node for node in ast.walk(parsed) if type(node) in ALL_IMPORT_TYPES]

    stdlib_imports = set()
    external_imports = set()
    internal_imports = set()
    near_relative_imports = set()
    far_relative_imports = set()

    def get_base_converted_module(name):
        name = name.split('.')[0]

        try:
            name = CONVERSIONS[name]
        except KeyError:
            pass

        return name

    def add_level_0(name):
        if name in STDLIB:
            stdlib_imports.add(name)
        elif name in internal_packages:
            internal_imports.add(name)
        else:
            external_imports.add(name)

    for an_import in imports:

        if type(an_import) in IMPORT_TYPES:
            for alias in an_import.names:
                name = get_base_converted_module(alias.name)
                add_level_0(name)

        elif type(an_import) in IMPORT_FROM_TYPES:
            name = get_base_converted_module(an_import.module)
            if an_import.level == 0:
                add_level_0(name)
            elif an_import.level == 1:
                near_relative_imports.add(name)
            else:
                far_relative_imports.add(name)

        else:
            raise TypeError("Unexpected import type")

    return {
        'stdlib': stdlib_imports,
        'external': external_imports,
        'internal': internal_imports,
        'near_relative': near_relative_imports,
        'far_relative': far_relative_imports}


def build_tree():
    dirtree = create_directory_digraph()

    package_roots = [n for n, d in dirtree.in_degree() if d == 0]
    package_root_map = {
        os.path.basename(os.path.dirname(package_root)): package_root
        for package_root in package_roots
    }

    internal_packages = list(package_root_map.keys())
    all_imports = {
        filepath: get_imports(filepath, internal_packages)
        for filepath in dirtree.nodes()
    }

    keys_to_keep = {'internal', 'external'}

    def get_descendants_dependencies(filepath):
        dependencies = {}
        for key in keys_to_keep:
            dependencies[key] = copy(all_imports[filepath][key])

        for descendant in nx.descendants(dirtree, filepath):
            for key in keys_to_keep:
                dependencies[key] |= all_imports[descendant][key]

        for key in keys_to_keep:
            dependencies[key] = list(dependencies[key])
            dependencies[key].sort()

        return dependencies

    tree = {
        package: get_descendants_dependencies(root)
        for package, root in package_root_map.items()
    }

    return tree


def save_tree():
    tree = build_tree()

    with open(DEPENDENCIES_JSON_FILEPATH, 'r') as file:
        data = json.load(file)

    data['tree'] = tree

    with open(DEPENDENCIES_JSON_FILEPATH, 'w') as file:
        json.dump(data, file, indent=2, sort_keys=True)


def test_tree():
    tree = build_tree()
    assert_tree_unchanged(tree)
    assert_tree_has_no_cycles(tree)


def assert_tree_has_no_cycles(tree):
    dag = nx.DiGraph()

    for key, values in tree.items():
        dag.add_node(key)
        dag.add_nodes_from(values['internal'])
        edge_tuples = [
            (key, value) for value in values['internal']
        ]
        dag.add_edges_from(edge_tuples)

    assert nx.is_directed_acyclic_graph(dag)


def assert_tree_unchanged(tree):
    with open(DEPENDENCIES_JSON_FILEPATH, 'r') as file:
        data = json.load(file)

    file_data = json.dumps(data['tree'], sort_keys=True, indent=2)
    calced_data = json.dumps(tree, sort_keys=True, indent=2)
    if file_data != calced_data:
        diff = difflib.unified_diff(
            file_data.split('\n'), calced_data.split('\n'))
        print('\n'.join(diff))
        raise AssertionError
