# pylint: disable=import-error

import os
from glob import glob

output_filenames = [os.path.basename(filepath) for filepath in glob("/output/*")]

output_filenames
