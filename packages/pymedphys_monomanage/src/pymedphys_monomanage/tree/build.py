
import os
import json
from copy import copy, deepcopy
import difflib

import networkx as nx

from ..parse.imports import get_imports


DEPENDENCIES_JSON_FILEPATH = 'dependencies.json'
DEFAULT_EXCLUDE_DIRS = {'node_modules', '__pycache__', 'dist', '.tox'}
DEFAULT_EXCLUDE_FILES = {'__init__.py', '_version.py', '_install_requires.py'}
DEFAULT_KEYS_TO_KEEP = {'stdlib', 'internal', 'external'}


class PackageTree:
    def __init__(self, directory, exclude_dirs=None, exclude_files=None):
        if exclude_dirs is None:
            exclude_dirs = DEFAULT_EXCLUDE_DIRS

        if exclude_files is None:
            exclude_files = DEFAULT_EXCLUDE_FILES

        self.exclude_dirs = exclude_dirs
        self.exclude_files = exclude_files

        self.directory = directory


    def trim_path(self, path):
        relpath = os.path.relpath(path, self.directory)
        split = relpath.split(os.sep)
        assert split[0] == split[2]
        assert split[1] == 'src'

        if split[-1] == '__init__.py':
            split = split[:-1]

        return os.path.join(*split[2:])


    def expand_path(self, path):
        split = path.split(os.sep)
        relpath = os.path.join(split[0], 'src', path)

        if not relpath.endswith('.py'):
            relpath = os.path.join(relpath, '__init__.py')

        return os.path.join(self.directory, relpath)


    def build_directory_digraph(self):
        digraph = nx.DiGraph()
        depth = {}

        for root, dirs, files in os.walk(self._directory, topdown=True):
            dirs[:] = [d for d in dirs if d not in self.exclude_dirs]

            if '__init__.py' in files:
                module = self.trim_path(os.path.join(root, '__init__.py'))
                current_depth = module.count(os.sep) + 1
                files[:] = [f for f in files if f not in self.exclude_files]

                digraph.add_node(module)
                depth[module] = current_depth
                parent_init = os.path.join(os.path.dirname(root), '__init__.py')
                if os.path.exists(parent_init):
                    digraph.add_edge(self.trim_path(parent_init), module)

                for f in files:
                    if f.endswith('.py'):
                        filepath = self.trim_path(os.path.join(root, f))
                        digraph.add_node(filepath)
                        depth[filepath] = current_depth
                        digraph.add_edge(module, filepath)

        if not digraph.nodes:
            raise ValueError('Directory provided does not contain modules')

        self.digraph = digraph
        self.depth = depth
        self.calc_properties()


    def calc_properties(self):
        self.roots = [n for n, d in self.digraph.in_degree() if d == 0]
        self.imports = {
            filepath: get_imports(
                self.expand_path(filepath), filepath, self.roots,
                self.depth[filepath])
            for filepath in self.digraph.nodes()
        }
        self._cache = {}
        self._cache['descendants_dependencies'] = {}


    @property
    def directory(self):
        return self._directory


    @directory.setter
    def directory(self, value):
        self._directory = value
        self.build_directory_digraph()


    def descendants_dependencies(self, filepath):
        try:
            return self._cache['descendants_dependencies'][filepath]
        except KeyError:
            dependencies = deepcopy(self.imports[filepath])

            for descendant in nx.descendants(self.digraph, filepath):
                for key in dependencies:
                    dependencies[key] |= self.imports[descendant][key]

            for key in dependencies:
                dependencies[key] = list(dependencies[key])
                dependencies[key].sort()

            self._cache['descendants_dependencies'][filepath] = dependencies
            return dependencies


    @property
    def package_dependencies_dict(self):
        try:
            return self._cache['package_dependencies_dict']
        except KeyError:
            key_map = {
                'internal_package': 'internal',
                'external': 'external',
                'stdlib': 'stdlib'
            }

            tree = {
                package: {
                        key_map[key]: sorted(list({package.split('.')[0] for package in packages}))
                        for key, packages in self.descendants_dependencies(package).items()
                        if key in key_map.keys()
                    }
                for package in self.roots
            }

            self._cache['package_dependencies_dict'] = tree
            return tree


    @property
    def package_dependencies_digraph(self):
        try:
            return self._cache['package_dependencies_digraph']
        except KeyError:
            dag = nx.DiGraph()

            for key, values in self.package_dependencies_dict.items():
                dag.add_node(key)
                dag.add_nodes_from(values['internal'])
                edge_tuples = [
                    (key, value) for value in values['internal']
                ]
                dag.add_edges_from(edge_tuples)

            self._cache['package_dependencies_digraph'] = dag
            return dag


    def is_acyclic(self):
        return nx.is_directed_acyclic_graph(self.package_dependencies_digraph)


def build_tree(directory):
    with open(DEPENDENCIES_JSON_FILEPATH, 'r') as file:
        data = json.load(file)

    data['tree'] = PackageTree(directory).package_dependencies_dict

    with open(DEPENDENCIES_JSON_FILEPATH, 'w') as file:
        json.dump(data, file, indent=2, sort_keys=True)


def test_tree(directory):
    package_tree = PackageTree(directory)
    assert package_tree.is_acyclic()
    assert_tree_unchanged(package_tree.package_dependencies_dict)


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
