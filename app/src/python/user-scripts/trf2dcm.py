import os
from glob import glob

import pydicom

from pymedphys import Delivery

input_directory = "input"
output_directory = "output"

trf_filepaths = glob(os.path.join(input_directory, "*.trf"))
dicom_filepaths = glob(os.path.join(input_directory, "*.dcm"))


for filepath in trf_filepaths:
    print("Preparing to convert {}".format(filepath))
    filename = os.path.basename(filepath)
    output_filepath = os.path.join(output_directory, "{}.dcm".format(filename))

    print("Loading log file")
    delivery_data = Delivery.from_logfile(filepath)

    print("Converting log file to RT Plan DICOM")
    for dicom_filepath in dicom_filepaths:
        dicom_template = pydicom.dcmread(dicom_filepath, force=True)
        try:
            created_dicom = delivery_data.to_dicom(dicom_template)
            print(
                "{} appears to be an RT DICOM plan with appropriate "
                "angle meterset combination, using this one.".format(dicom_filepath)
            )
            continue
        except AttributeError:
            print(
                "{} does not appear to be an RT DICOM plan, "
                "skipping...".format(dicom_filepath)
            )

    print("Saving newly created RT Plan DICOM")
    created_dicom.save_as(output_filepath)


print("Converted {} log file(s)".format(len(trf_filepaths)))
