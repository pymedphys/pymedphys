# pylint: disable=import-error

import os
from glob import glob

from js import window, Promise


def update_output():
    def run_promise(resolve, reject):
        try:
            output_filenames = [
                os.path.basename(filepath)
                for filepath in glob('/output/*')
            ]
            window['outputDirectory'].next(output_filenames)
            resolve()
        except Exception as e:
            reject(e)
            raise

    return Promise.new(run_promise)


update_output()
