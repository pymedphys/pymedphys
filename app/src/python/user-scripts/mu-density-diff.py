import os
from glob import glob

import pydicom

from pymedphys import DeliveryData

input_directory = 'input'
output_directory = 'output'

trf_filepaths = glob(os.path.join(input_directory, '*.trf'))
first_dicom_filepath = glob(os.path.join(input_directory, '*.dcm'))[0]

dicom_template = pydicom.dcmread(first_dicom_filepath, force=True)

for filepath in trf_filepaths:
    print("Preparing to convert {}".format(filepath))
    filename = os.path.basename(filepath)
    output_filepath = os.path.join(output_directory, "{}.dcm".format(filename))

    print("Loading log file")
    delivery_data = DeliveryData.from_logfile(filepath)

    print("Converting log file to RT Plan DICOM")
    created_dicom = delivery_data.to_dicom(dicom_template)

    print("Saving newly created RT Plan DICOM")
    created_dicom.save_as(output_filepath)


print("Converted {} log file(s)".format(len(trf_filepaths)))
