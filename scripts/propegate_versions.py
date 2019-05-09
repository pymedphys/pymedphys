import os
import json
from glob import glob

import semver

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

version_filepath = glob(os.path.join(
    "src", "pymedphys*", "_version.py"))[0]
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
__version__ = "{}"
""".format(version_info, __version__)

with open(version_filepath, 'w') as file:
    file.write(version_file_contents)


if version_info[3]:
    dev_string = '-' + ''.join(version_info[3:])  # type: ignore
else:
    dev_string = ""

semver_string = '.'.join(map(str, version_info[:3])) + dev_string
semver_parsed = semver.parse(semver_string)

if semver_parsed['major'] == 0:
    upper_limit = semver.bump_minor(semver_string)
    npm_version_prepend = "~"
else:
    upper_limit = semver.bump_major(semver_string)
    npm_version_prepend = "^"


dependencies_filepath = os.path.join(ROOT, "dependencies.json")


with open(dependencies_filepath, 'r') as file:
    dependencies_data = json.load(file)


dependencies_data['pins']['pypi']['internal'][package_name] = (
    ">= {}, < {}".format(__version__, upper_limit))
dependencies_data['pins']['npm']['internal'][package_name] = (
    "{}{}".format(npm_version_prepend, semver_string))

with open(dependencies_filepath, 'w') as file:
    json.dump(dependencies_data, file, indent=2, sort_keys=True)
