import os
import textwrap
import json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

with open(os.path.join(ROOT, 'dependencies.json'), 'r') as file:
    dependencies_data = json.load(file)


tree = dependencies_data['tree']
pins = dependencies_data['pins']


for package, dependency_store in tree.items():
    install_requires = []

    for where, dependencies in dependency_store.items():
        for dependency in dependencies:
            try:
                pin = " " + pins[where][dependency]
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
