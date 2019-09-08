import os
from glob import glob

from pymedphys.trf import trf2pandas

input_directory = "input"
output_directory = "output"

filepaths = glob(os.path.join(input_directory, "*.trf"))

for filepath in filepaths:
    filename = os.path.basename(filepath)
    common_output_filepath = os.path.join(output_directory, filename)

    header_csv_filepath = "{}.header.csv".format(common_output_filepath)
    table_csv_filepath = "{}.table.csv".format(common_output_filepath)

    print("Converting {}".format(filepath))

    header, table = trf2pandas(filepath)
    header.to_csv(header_csv_filepath)
    table.to_csv(table_csv_filepath)

print("Converted {} log file(s)".format(len(filepaths)))
