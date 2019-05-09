import os
import json
from glob import glob

version_filepath = glob("src/pymedphys*/_version.py")[0]
package_name = os.path.split(os.path.dirname(version_filepath))[-1]

with open('package.json', 'r') as file:
    data = json.load(file)

loaded_version_info = data['version'].replace(
    '.', ' ').replace('-', ' ').split(' ')

version_info = [
    int(number)
    for number in loaded_version_info[0:3]
] + [''.join(loaded_version_info[3::])]  # type: ignore

__version__ = '.'.join(
    map(str, version_info[:3])) + ''.join(version_info[3:])  # type: ignore

version_file_contents = """version_info = {}
__version__ = {}
""".format(version_info, __version__)

with open(version_filepath, 'w') as file:
    file.write(version_file_contents)

with open('../../dependencies.json', 'r') as file:
    dependencies_data = json.load(file)


dependencies_data['pins']['internal'][package_name] = ">= {}".format(
    __version__)

with open('../../dependencies.json', 'w') as file:
    json.dump(dependencies_data, file, indent=2)
