import os
import textwrap
import json
from glob import glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

with open(os.path.join(ROOT, 'dependencies.json'), 'r') as file:
    dependencies_data = json.load(file)


tree = dependencies_data['tree']
pypi_pins = dependencies_data['pins']['pypi']
npm_pins = dependencies_data['pins']['npm']

internal_packages = [
    os.path.basename(filepath)
    for filepath in glob(os.path.join(ROOT, 'packages', '*'))
]

assert set(internal_packages) == set(tree.keys())
assert set(internal_packages) == set(pypi_pins['internal'].keys())
assert set(internal_packages) == set(npm_pins['internal'].keys())


for package, dependency_store in tree.items():
    install_requires = []

    for where, dependencies in dependency_store.items():
        for dependency in dependencies:
            try:
                pin = " " + pypi_pins[where][dependency]
            except KeyError:
                pin = ""

            requirement_string = dependency + pin
            install_requires.append(requirement_string)

    install_requires.sort()

    install_requires_filepath = os.path.join(
        ROOT, "packages", package, "src", package, "_install_requires.py")

    install_requires_contents = textwrap.dedent("""\
        install_requires = {}
    """).format(json.dumps(install_requires, indent=4))

    with open(install_requires_filepath, 'w') as file:
        file.write(install_requires_contents)


for package, dependency_store in tree.items():
    internal_dependencies = {
        dependency: npm_pins['internal'][dependency]
        for dependency in dependency_store['internal']
    }

    package_json_filepath = os.path.join(
        ROOT, "packages", package, "package.json")

    with open(package_json_filepath, 'r') as file:
        data = json.load(file)

    try:
        external_dependencies = {
            package: pin
            for package, pin in data['dependencies'].items()
            if package not in internal_packages
        }
    except KeyError:
        external_dependencies = {}

    data['dependencies'] = {
        **internal_dependencies,
        **external_dependencies
    }

    with open(package_json_filepath, 'w') as file:
        json.dump(data, file, indent=2, sort_keys=True)
