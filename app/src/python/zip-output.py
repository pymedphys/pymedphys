# pylint: disable=import-error

import os
from glob import glob
from zipfile import ZipFile

from js import window, Promise


def zip_output():
    def run_promise(resolve, reject):
        try:
            files = glob('output/*')

            with ZipFile('output.zip', 'w') as myzip:
                for filename in files:
                    myzip.write(filename, os.path.basename(filename))
            resolve()
        except Exception as e:
            reject(e)
            raise

    return Promise.new(run_promise)


zip_output()
