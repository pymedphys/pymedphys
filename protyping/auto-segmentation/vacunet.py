import glob

import config
import create_rs
import dicom_helpers
import inference
import structure_storage_scu


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

    # For RT structure file instance
    save_path = study_path + "/" + dicom_structure_file.SOPInstanceUID + ".dcm"
    dicom_structure_file.save_as(save_path, write_like_original=False)

    # Forward to SCU for export
    if config.FORWARD_IMAGES:
        structure_storage_scu.export_files(study_path, directory=True)
    else:
        structure_storage_scu.export_files([save_path], directory=False)

    return dicom_structure_file
