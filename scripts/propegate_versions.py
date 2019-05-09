import json
from glob import glob

version_filepath = glob("src/pymedphys*/_version.py")[0]

with open('package.json', 'r') as file:
    data = json.load(file)

loaded_version_info = data['version'].replace(
    '.', ' ').replace('-', ' ').split(' ')

version_info = [
    int(number)
    for number in loaded_version_info[0:3]
] + [''.join(loaded_version_info[3::])]  # type: ignore

version_file_contents = """version_info = {}
__version__ = '.'.join(
    map(str, version_info[:3])) + ''.join(version_info[3:])  # type: ignore
""".format(version_info)

with open(version_filepath, 'w') as file:
    file.write(version_file_contents)
