# pylint: disable=import-error

import os
from glob import glob

from js import window

from pymedphys_fileformats.trf.trf2csv import trf2csv_by_directory


def callback(filename):
    print('Completed processing of {}'.format(filename))
    output_filenames = [
        os.path.basename(filepath)
        for filepath in glob('/output/*')
    ]
    window['outputDirectory'].next(output_filenames)


trf2csv_by_directory('/input', '/output', callback=callback)
