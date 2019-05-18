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
import textwrap

import networkx as nx
from copy import copy

from ..tree import PackageTree
from .utilities import (
    save_dot_file, remove_prefix, get_levels, remove_prefix, remove_postfix,
    convert_path_to_package, create_labels, create_href)


ROOT = os.getcwd()


def draw_file_modules(save_directory):
    package_tree = PackageTree(os.path.join(ROOT, 'packages'))

    internal_packages = copy(package_tree.roots)
    internal_packages.remove('pymedphys')

    directory_module_paths = [
        module_path
        for package in internal_packages
        for module_path in package_tree.digraph.neighbors(package)
    ]

    file_module_paths = [
        item
        for directory_module_path in directory_module_paths
        for item in package_tree.digraph.neighbors(directory_module_path)
    ]

    module_map = {
        item: convert_path_to_package(item)
        for item in directory_module_paths + file_module_paths
    }

    dependencies = {
        convert_path_to_package(module): {
            key: [
                convert_path_to_package(item)
                for item in descendants_dependencies
            ]
            for key, descendants_dependencies in package_tree.imports[module].items()
        }
        for module in module_map.keys()
    }

    dependents = {
        key: [] for key in dependencies.keys()
    }
    for file_module, dependency_map in dependencies.items():
        for where, values in dependency_map.items():
            for item in values:
                try:
                    dependents[item].append(file_module)
                except KeyError:
                    pass

    for directory_module_path in directory_module_paths:
        directory_module = convert_path_to_package(directory_module_path)
        print(directory_module)

        package_name = directory_module.split('.')[0]

        current_modules = [
            convert_path_to_package(item)
            for item in package_tree.digraph.neighbors(directory_module_path)
        ] + [directory_module]

        outfilepath = os.path.join(
            save_directory, "{}.svg".format(directory_module))

        if len(current_modules) <= 1:
            dot_file_contents = """
                strict digraph  {{
                    subgraph cluster_0 {{
                        "";
                        label = "{}";
                        style = dashed;
                    }}
                }}
            """.format(directory_module)

            save_dot_file(dot_file_contents, outfilepath)
            continue

        all_current_dependencies = {
            module: dependencies[module]
            for module in current_modules
        }

        keys_to_keep = {'internal_package', 'internal_module', 'internal_file'}

        current_dependencies = {
            module: [
                item
                for key, values in dependencies[module].items()
                if key in keys_to_keep
                for item in values
            ]
            for module in current_modules
        }

        current_dependents = {
            module: dependents[module]
            for module in current_modules
        }

        all_nodes = sorted(list(set([
            *current_dependencies.keys(),
            *[
                item
                for a_list in current_dependencies.values()
                for item in a_list],
            *current_dependents.keys(),
            *[
                item
                for a_list in current_dependents.values()
                for item in a_list]
        ])))

        internal_dependencies = {
            key: [
                value
                for value in values
                if value in current_modules
            ]
            for key, values in current_dependencies.items()
            if key in current_modules
        }

        internal_ranks = ""

        levels = get_levels(internal_dependencies)

        for level in range(max(levels.keys()) + 1):
            if levels[level]:
                grouped_packages = '"; "'.join(sorted(list(levels[level])))
                internal_ranks += textwrap.dedent("""\
                    {{ rank = same; "{}"; }}
                """.format(grouped_packages))

        in_same_module_other_dir = [
            node
            for node in all_nodes
            if node.startswith(package_name)
            and not node.startswith(directory_module)]

        if in_same_module_other_dir:
            in_same_module_other_dir_string = '"{}";'.format(
                '";\n"'.join(in_same_module_other_dir))
        else:
            in_same_module_other_dir_string = ''

        def simplify(text):
            text = remove_prefix(text, "{}.".format(package_name))
            text = remove_prefix(text, 'pymedphys_')

            return text

        label_map = {
            node: simplify(node)
            for node in all_nodes
        }

        label_map_str = ""
        for node, label in label_map.items():
            label_map_str += '"{}" [label="{}"] {};\n'.format(
                node, label, get_github_url(node))

        edges = ""

        for module in sorted(current_modules):
            for dependency in sorted(list(current_dependencies[module])):
                edges += '"{}" -> "{}";\n'.format(module, dependency)

            for dependent in sorted(list(current_dependents[module])):
                edges += '"{}" -> "{}";\n'.format(dependent, module)

        dot_file_contents = textwrap.dedent("""\
        strict digraph  {{
            rankdir = LR;

            subgraph cluster_0 {{
                {}
                label = "{}";
                URL = "{}";
                style = dashed;

                subgraph cluster_1 {{
        {}
                    label = "{}";
                    URL = "{}"
                }}
            }}

        {}
        {}}}
        """).format(
            in_same_module_other_dir_string,
            package_name,
            create_href(package_name),
            textwrap.indent(internal_ranks, ' '*12),
            directory_module,
            create_href(directory_module),
            textwrap.indent(label_map_str, ' '*4),
            textwrap.indent(edges, ' '*4))

        save_dot_file(dot_file_contents, outfilepath)


def get_github_url(module):
    url_module = module.replace('.', '/')
    split_module = url_module.split('/')

    if len(split_module) == 3:
        url_module += '.py'

    top_level_package = split_module[0]
    url = "https://github.com/pymedphys/pymedphys/blob/master/packages/{}/src/{}".format(
        top_level_package, url_module
    )

    hyperlink = '[URL="{}"]'.format(url)
    return hyperlink
