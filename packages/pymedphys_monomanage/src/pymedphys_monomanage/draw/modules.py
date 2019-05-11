import os

import networkx as nx
from copy import copy

from ..tree import PackageTree
from .utilities import save_dot_file, remove_prefix



ROOT = os.getcwd()


def draw_modules(save_directory):
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
        module.replace(os.sep, '.'): [
            '.'.join(item.split('.')[0:2])
            for item in
            package_tree.descendants_dependencies(module)['internal_module'] +
            package_tree.descendants_dependencies(module)['internal_package']
        ]
        for module in modules.keys()
    }

    dependents = {  # type: ignore
        key: [] for key in dependencies.keys()
    }
    for key, values in dependencies.items():
        for item in values:
            dependents[item].append(key)  # type: ignore

    for package in internal_packages:
        build_graph_for_a_module(
            package, package_tree, dependencies, dependents, save_directory)




def get_levels(dag):

    topological = list(nx.topological_sort(dag))

    level_map = {}
    for package in topological[::-1]:
        depencencies = nx.descendants(dag, package)
        levels = {0}
        for dependency in sorted(depencencies):
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



def build_graph_for_a_module(graphed_package, package_tree, dependencies,
                             dependents, save_directory):
    print(graphed_package)

    current_modules = [
        item.replace(os.sep, '.')
        for item in package_tree.digraph.neighbors(graphed_package)
    ]

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
        for module in package_tree.digraph.neighbors(graphed_package)
    }

    dag = nx.DiGraph()

    for key, values in module_internal_relationships.items():
        dag.add_node(key)
        dag.add_nodes_from(values)
        edge_tuples = [
            (key, value) for value in values
        ]
        dag.add_edges_from(edge_tuples)


    dag.edges()

    levels = get_levels(dag)

    def simplify(text):
        text = remove_prefix(text, "{}.".format(graphed_package))
        text = remove_prefix(text, 'pymedphys_')

        return text

    nodes = ""

    for level in range(max(levels.keys()) + 1):
        if levels[level]:
            trimmed_nodes = [
                simplify(node) for node in levels[level]
            ]

            grouped_packages = '"; "'.join(trimmed_nodes)
            nodes += """
            {{ rank = same; "{}"; }}
            """.format(grouped_packages)


    edges = ""
    current_packages = ""

    current_dependents = set()
    current_dependencies = set()


    for module in current_modules:
        module_repr = simplify(module)
        current_packages += '"{}";\n'.format(module_repr)

        for dependency in sorted(dependencies[module]):
            simplified = simplify(dependency)
            edges += '"{}" -> "{}";\n'.format(module_repr, simplified)
            if not dependency in current_modules:
                current_dependencies.add(simplified)

        for dependent in sorted(dependents[module]):
            simplified = simplify(dependent)
            edges += '"{}" -> "{}";\n'.format(simplified, module_repr)
            if not dependent in current_modules:
                current_dependents.add(simplified)


    external_ranks = ""
    if current_dependents:
        grouped_dependents = '"; "'.join(sorted(current_dependents))
        external_ranks += '{{ rank = same; "{}"; }}\n'.format(grouped_dependents)

    if current_dependencies:
        grouped_dependencies = '"; "'.join(sorted(current_dependencies))
        external_ranks += '{{ rank = same; "{}"; }}\n'.format(grouped_dependencies)

    dot_file_contents = """
        strict digraph  {{
            rankdir = LR;
            {}
            subgraph cluster_0 {{
                {}
                label = "{}";
                style = dashed;
                {}
            }}
            {}
        }}
    """.format(external_ranks, current_packages, graphed_package, nodes, edges)

    save_dot_file(dot_file_contents, outfilepath)
