import os
from glob import glob

import pydicom

from pymedphys.dicom import convert_to_one_fraction_group

input_directory = "input"
output_directory = "output"

dicom_filepaths = glob(os.path.join(input_directory, "*.dcm"))

for filepath in dicom_filepaths:
    filename = os.path.basename(filepath)
    print("Processing {}".format(filename))
    print("Loading DICOM file")
    dicom_dataset = pydicom.dcmread(filepath, force=True)

    try:
        fraction_group_numbers = [
            fraction_group.FractionGroupNumber
            for fraction_group in dicom_dataset.FractionGroupSequence
        ]
    except AttributeError:
        print(
            "{} does not appear to be an RT DICOM plan, " "skipping...".format(filepath)
        )
        continue

    print("{} Fraction Group(s) found".format(len(fraction_group_numbers)))

    for fraction_group_number in fraction_group_numbers:
        print("Splitting out fraction group number {}".format(fraction_group_number))

        created_dicom = convert_to_one_fraction_group(
            dicom_dataset, fraction_group_number
        )

        output_filepath = os.path.join(
            output_directory, "{}-{}.dcm".format(filename, fraction_group_number)
        )

        print("Saving {}".format(output_filepath))
        created_dicom.save_as(output_filepath)
