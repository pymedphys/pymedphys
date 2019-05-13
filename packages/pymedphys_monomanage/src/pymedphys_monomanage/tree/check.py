import os
import json
from copy import deepcopy

from .build import PackageTree


def serialise_imports(imports):
    new_imports = {}
    for module_path_raw, values in imports.items():
        module_path = module_path_raw.replace(os.sep, '/')
        new_imports[module_path] = {}

        for where, a_set in values.items():
            new_imports[module_path][where] = sorted(list(a_set))

    return json.dumps(new_imports, sort_keys=True, indent=2)


def is_imports_json_up_to_date(directory):
    packages = os.path.join(directory, 'packages')
    imports_json = os.path.join(directory, 'imports.json')

    with open(imports_json) as file:
        data = json.load(file)

    file_data = json.dumps(data, sort_keys=True, indent=2)
    calced_data = serialise_imports(PackageTree(packages).imports)

    return file_data == calced_data


def commit_hook(directory):
    if not is_imports_json_up_to_date(directory):
        os.system("yarn tree")
        raise ValueError("Tree was out of date. Please rerun commit.")


def update_imports_json(directory):
    packages = os.path.join(directory, 'packages')
    imports_json = os.path.join(directory, 'imports.json')

    with open(imports_json, 'w') as file:
        file.write(serialise_imports(PackageTree(packages).imports))
