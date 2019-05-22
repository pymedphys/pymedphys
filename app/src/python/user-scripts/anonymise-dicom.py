from os.path import basename, join as pjoin
from glob import glob

from pymedphys.dicom import DicomBase

INPUT_DIR = 'input'
OUTPUT_DIR = 'output'

filepaths = glob(pjoin(INPUT_DIR, "*.dcm"))

for filepath in filepaths:
    filename = basename(filepath)
    print("Anonymising {}".format(filename))

    output_filepath = pjoin(OUTPUT_DIR, filename)
    dcm = DicomBase.from_file(filepath)
    dcm.anonymise()
    dcm.to_file(output_filepath)

print("Anonymised {} log file(s)".format(len(filepaths)))
