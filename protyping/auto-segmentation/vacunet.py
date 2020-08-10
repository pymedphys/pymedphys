import glob

import pydicom
from pydicom.dataset import Dataset

import config
import create_rs
import dicom_helpers
import inference


def vacunet(data_path, root_uid):

    dicom_paths = glob.glob(data_path + "/*.dcm")

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

    dicom_helpers.print_dicom_file(dicom_structure_file)

    # NOTE Remove AUTO label in production
    save_path = data_path + "/AUTO_" + dicom_structure_file.SOPInstanceUID + ".dcm"
    dicom_structure_file.save_as(save_path, write_like_original=False)
    print("\nEXPORTED:", save_path)


if __name__ == "__main__":
    ROOT_UID = "1.2.826.0.1.3680043.8.498."  # Pydicom ROOT UID
    DATA_PATH = "/media/matthew/secondary/dicom_prostate_images_created_rs"
    vacunet(DATA_PATH, ROOT_UID)
