# pylint: disable=import-error

import os
from glob import glob

from pymedphys_fileformats.trf.trf2csv import trf2csv


trf_files = glob('/*.trf')

assert len(trf_files) == 1

a_file = trf_files[0]

header_csv_filepath, table_csv_filepath = trf2csv(a_file)
header_filename = os.path.basename(header_csv_filepath)
table_filename = os.path.basename(table_csv_filepath)
os.remove(a_file)
