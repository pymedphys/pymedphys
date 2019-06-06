import os
import tarfile
import json
import hashlib
from glob import glob


def tar_filter(tar_info: tarfile.TarInfo):
    blacklist = [
        'tests', 'build', 'dist', 'node_modules', 'egg-info', '__pycache__',
        '.pyc', 'yarn-error.log', '.mypy_cache', 'sphinxtheme']

    for item in blacklist:
        if item in tar_info.name:
            return None

    return tar_info


def main():
    with open('lerna.json') as lerna_json:
        version = json.load(lerna_json)['version']

    licenses = glob('LICENSE*')

    to_archive = [
        'packages', 'package.json', 'README.rst', 'lerna.json'] + licenses

    output_filename = 'v{}.tar.gz'.format(version)

    try:
        os.remove(output_filename)
    except FileNotFoundError:
        pass

    with tarfile.open(output_filename, "w:gz") as tar:
        for path in to_archive:
            tar.add(path, arcname=os.path.basename(path), filter=tar_filter)

    with open(output_filename, "rb") as created_tar:
        hash_result = hashlib.sha256(created_tar.read()).hexdigest()

    print(hash_result)


if __name__ == "__main__":
    main()
