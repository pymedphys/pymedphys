import os
import shutil

import networkx as nx


def save_dot_file(dot_contents, outfilepath):
    with open("temp.dot", 'w') as file:
        file.write(dot_contents)

    os.system("cat temp.dot | tred | dot -Tsvg -o temp.svg")
    os.remove("temp.dot")
    # shutil.move("temp.dot", outfilepath + ".dot")

    shutil.move("temp.svg", outfilepath)


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