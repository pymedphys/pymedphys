import os

import networkx as nx
from copy import copy

from ..tree import PackageTree
from .utilities import save_dot_file, remove_prefix, get_levels



ROOT = os.getcwd()


def draw_directory_modules(save_directory):
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
        module.replace(os.sep, '.'): {
            '.'.join(item.split('.')[0:2])
            for item in
            package_tree.descendants_dependencies(module)['internal_module'] +
            package_tree.descendants_dependencies(module)['internal_package']
        }
        for module in modules.keys()
    }

    dependents = {  # type: ignore
        key: set() for key in dependencies.keys()
    }
    for key, values in dependencies.items():
        for item in values:
            dependents[item].add(key)  # type: ignore

    for package in internal_packages:
        build_graph_for_a_module(
            package, package_tree, dependencies, dependents, save_directory)


def build_graph_for_a_module(graphed_package, package_tree, dependencies,
                             dependents, save_directory):
    print(graphed_package)

    current_modules = sorted([
        item.replace(os.sep, '.')
        for item in package_tree.digraph.neighbors(graphed_package)
    ])

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
        for module in sorted(list(package_tree.digraph.neighbors(graphed_package)))
    }

    levels = get_levels(module_internal_relationships)


    internal_nodes = sorted(list(set(module_internal_relationships.keys())))
    external_nodes = set()
    for module in current_modules:
        external_nodes |= dependencies[module]
        external_nodes |= dependents[module]

    external_nodes = sorted(list(external_nodes))

    all_nodes = internal_nodes + external_nodes

    def simplify(text):
        text = remove_prefix(text, "{}.".format(graphed_package))
        text = remove_prefix(text, 'pymedphys_')

        return text

    label_map = {
        node: simplify(node)
        for node in all_nodes
    }


    nodes = ""

    for level in range(max(levels.keys()) + 1):
        if levels[level]:
            grouped_packages = '"; "'.join(sorted(list(levels[level])))
            nodes += """
            {{ rank = same; "{}"; }}
            """.format(grouped_packages)


    edges = ""
    current_packages = ""

    current_dependents = set()
    current_dependencies = set()


    for module in current_modules:
        current_packages += '"{}";\n'.format(module)

        for dependency in sorted(list(dependencies[module])):
            edges += '"{}" -> "{}";\n'.format(module, dependency)
            if not dependency in current_modules:
                current_dependencies.add(dependency)

        for dependent in sorted(list(dependents[module])):
            edges += '"{}" -> "{}";\n'.format(dependent, module)
            if not dependent in current_modules:
                current_dependents.add(dependent)


    external_ranks = ""
    if current_dependents:
        grouped_dependents = '"; "'.join(sorted(list(current_dependents)))
        external_ranks += '{{ rank = same; "{}"; }}\n'.format(grouped_dependents)

    if current_dependencies:
        grouped_dependencies = '"; "'.join(sorted(list(current_dependencies)))
        external_ranks += '{{ rank = same; "{}"; }}\n'.format(grouped_dependencies)

    external_labels = ""
    for node, label in label_map.items():
        external_labels += '"{}" [label="{}"];\n'.format(node, label)


    dot_file_contents = """
        strict digraph  {{
            rankdir = LR;
            subgraph cluster_0 {{
                {}
                label = "{}";
                style = dashed;
                {}
            }}
            {}
            {}
            {}
        }}
    """.format(
        current_packages, graphed_package,
        nodes, external_labels, external_ranks, edges)

    save_dot_file(dot_file_contents, outfilepath)
