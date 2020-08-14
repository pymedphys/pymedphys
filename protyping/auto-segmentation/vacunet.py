import glob

import config
import create_rs
import dicom_helpers
import inference

import pydicom
from pydicom.dataset import Dataset


def vacunet(study_path, root_uid):

    dicom_paths = glob.glob(study_path + "/*.dcm")

    dicom_files = dicom_helpers.read_dicom_paths(dicom_paths)
    dicom_series, *rest = dicom_helpers.filter_dicom_files(dicom_files)
    dicom_series = dicom_helpers.sort_slice_location(dicom_series)

    predictions = inference.get_predictions(dicom_series)

    contours = []
    for dicom, prediction in zip(dicom_series, predictions):
        contour = inference.predict_to_contour(dicom, prediction)
        contours.append(contour)
    assert len(contours) == len(dicom_series)

    dicom_structure_file = create_rs.create_rs_file(dicom_series, contours, root_uid)

    return dicom_structure_file
