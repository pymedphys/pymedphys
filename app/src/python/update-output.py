# pylint: disable=import-error

import os
from glob import globZ

output_filenames = [
    os.path.basename(filepath)
    for filepath in glob('/output/*')
]

output_filenames
