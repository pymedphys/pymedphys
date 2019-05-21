import os
from glob import glob

from pymedphys.trf import trf2pandas

input_directory = 'input'
output_directory = 'output'

filepaths = glob(os.path.join(input_directory, '*.trf'))

for filepath in filepaths:
    filename = os.path.basename(filepath)
    new_filename = os.path.join(output_directory, filename)

    header_csv_filepath = "{}.header.csv".format(new_filename)
    table_csv_filepath = "{}.table.csv".format(new_filename)

    print("Converting {}".format(filepath))

    header, table = trf2pandas(filepath)
    header.to_csv(header_csv_filepath)
    table.to_csv(table_csv_filepath)

print("Converted {} log file(s)".format(len(filepaths)))
