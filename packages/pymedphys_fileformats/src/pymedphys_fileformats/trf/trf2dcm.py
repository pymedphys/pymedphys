import os
import pydicom

from pymedphys_core.deliverydata import (
    delivery_data_to_dicom)
from .trf2deliverydata import delivery_data_from_logfile


def trf2dcm(dcm_template_filepath, trf_filepath, gantry_angle, output_dir):
    trf_filename = os.path.basename(trf_filepath)
    filepath_out = os.path.join(output_dir, "{}.dcm".format(trf_filename))

    dicom_template = pydicom.read_file(dcm_template_filepath, force=True)
    delivery_data = delivery_data_from_logfile(trf_filepath)
    edited_dicom = delivery_data_to_dicom(
        delivery_data, dicom_template, gantry_angle)

    edited_dicom.save_as(filepath_out)
