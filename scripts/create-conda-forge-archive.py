import os
import tarfile
import json
from glob import glob


def main():

    with open('lerna.json') as lerna_json:
        version = json.load(lerna_json)['version']

    licenses = glob('LICENSE*')

    to_archive = ['packages', 'package.json', 'README.rst'] + licenses

    output_filename = 'v{}.tar.gz'.format(version)

    with tarfile.open(output_filename, "w:gz") as tar:
        for path in to_archive:
            tar.add(path, arcname=os.path.basename(path))


if __name__ == "__main__":
    main()
