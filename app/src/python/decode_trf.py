# pylint: disable=import-error

import os
from glob import glob

from js import window

from pymedphys_fileformats.trf.trf2csv import trf2csv_by_directory


trf2csv_by_directory('/input', '/output')

output_filenames = [
    os.path.basename(filepath)
    for filepath in glob('/output/*')
]

window['outputDirectory'].next(output_filenames)
