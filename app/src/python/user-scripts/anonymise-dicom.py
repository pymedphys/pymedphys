from os import rename
from os.path import basename, join as pjoin
from glob import glob

from pymedphys.dicom import anonymise_file

INPUT_DIR = "input"
OUTPUT_DIR = "output"

filepaths = glob(pjoin(INPUT_DIR, "*.dcm"))

for filepath in filepaths:
    filename = basename(filepath)
    print("Anonymising {}".format(filename))

    output_filepath = pjoin(OUTPUT_DIR, filename)

    anon_filepath = anonymise_file(filepath, delete_unknown_tags=True)

    rename(anon_filepath, output_filepath)

print("Anonymised {} DICOM file(s)".format(len(filepaths)))
