# Copyright (C) 2021 Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import io
import zipfile

from pymedphys._imports import pydicom
from pymedphys._imports import streamlit as st

import pymedphys._dicom.create as _pp_dcm_create
from pymedphys import _losslessjpeg as lljpeg
from pymedphys._dicom import uid
from pymedphys._streamlit import categories
from pymedphys._streamlit.utilities import config as st_config
from pymedphys._streamlit.utilities import download

import pymedphys._experimental.wlutz.iview as _pp_wlutz_iview
from pymedphys._experimental.streamlit.utilities.iview import ui as iview_ui

CATEGORY = categories.PLANNING
TITLE = "iView to DICOM"


def main():
    config = st_config.get_config()
    advanced_mode = st.sidebar.checkbox("Advanced Mode")

    (
        database_table,
        database_directory,
        _,  # qa_directory,
        _,  # selected_date,
    ) = iview_ui.iview_and_icom_filter_and_align(
        config, advanced_mode=advanced_mode, filter_angles_by_default=True
    )

    # st.write(database_table)

    if not st.button("Create DICOM files"):
        st.stop()

    progress_bar = st.progress(0)
    total_rows = len(database_table)

    st.write("Converting iView images to DICOM...")
    status_text = st.empty()

    dicom_datasets = []
    for i, (_, row) in enumerate(database_table.iterrows()):
        file_name = (
            f"{row['treatment']}_{row['port']}_"
            f"{row['datetime'].strftime('%Y%m%d%H%M%S')}_"
            f"G{row['gantry']:+.1f}_C{row['collimator']:+.1f}_TT{row['turn_table']:+.1f}.dcm"
        )
        status_text.write(f"`{file_name}`")

        full_image_path = database_directory.joinpath(row["filepath"])
        gantry = bipolar_to_IEC(row["gantry"])
        collimator = bipolar_to_IEC(row["collimator"])
        table = bipolar_to_IEC(row["turn_table"])
        patient_name = f"{row['LAST_NAME']}^{row['FIRST_NAME']}"

        dicom_iview_image_dataset = _create_portal_image_dicom_dataset(
            patient_name,
            row["patient_id"],
            row["datetime"],
            gantry,
            collimator,
            table,
            full_image_path,
        )

        dicom_datasets.append((file_name, dicom_iview_image_dataset))

        progress_bar.progress(((i + 1) / total_rows))

    st.write("Adding DICOM files to zip...")

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
        for file_name, dataset in dicom_datasets:
            dataset_buffer = io.BytesIO()
            pydicom.dcmwrite(dataset_buffer, dataset, write_like_original=False)
            zip_file.writestr(file_name, dataset_buffer.getvalue())

    st.write("Done.")

    download("iView_DICOM_files.zip", zip_buffer.getvalue())


def bipolar_to_IEC(bipolar_angle):
    # TODO: Further thought here needed.

    iec_angle = bipolar_angle % 360
    return iec_angle


def _create_portal_image_dicom_dataset(
    patient_name,
    patient_id,
    datetime,
    gantry_angle,
    collimator_angle,
    table_angle,
    image_path,
):
    """Don't intend this DICOM file to be compliant to the spec.

    Instead, for now, just enough that software such as PIPs will
    happily accept the created file.
    """

    # Consider refactoring this so that for all pylinac calls a full
    # DICOM file is passed to it in the way that it expects. The image
    # wrapper around pylinac could instead call this first.

    # Image plane pixel spacing.
    # Exported DICOM files have an image plane pixel spacing of 0.405,
    # with SID of 1600 and SAD of 1000. This corresponds to an iso
    # centre pixel spacing of 0.2531 mm.
    #
    # Within the database, those same images have an isocentre pixel
    # spacing of either 0.2510 mm or 0.2488 mm. I suspect potentially
    # there might be some interesting datastore rounding going on here.
    # I was under the impression that the isocentre pixel spacing was
    # for these images was 0.25 mm.

    pixel_array = lljpeg.imread(image_path)
    pixels_per_mm = _pp_wlutz_iview.infer_pixels_per_mm_from_shape(pixel_array)

    SID = 1600.0
    SAD = 1000.0

    pixel_spacing = (1 / pixels_per_mm) * (SID / SAD)

    date = datetime.strftime("%Y%m%d")
    time = datetime.strftime("%H%M%S.%f")

    # Many of the below was input without a full understanding of the
    # implications of the choices being made.
    ds = _pp_dcm_create.dicom_dataset_from_dict(
        {
            "Modality": "RTIMAGE",
            "InstanceCreatorUID": uid.PYMEDPHYS_ROOT_UID,
            "SOPClassUID": "1.2.840.10008.5.1.4.1.1.481.1",
            "SOPInstanceUID": uid.generate_uid(),
            # From <https://dicom.innolitics.com/ciods/cr-image/general-image/00080008>
            #
            # * is the image an ORIGINAL Image; an image whose pixel
            #   values are based on original or source data
            # * is the image a SECONDARY Image; an image created after
            #   the initial patient examination
            "ImageType": ["ORIGINAL", "SECONDARY", "PORTAL"],
            # Purposefully avoided all concepts of 'Study' if possible
            # as this would require appropriately grouping the images
            # from each field. Certainly doable, and arguably it should
            # be done, but out of scope for the current task.
            "PatientID": patient_id,
            "PatientName": patient_name,
            "AcquisitionDate": date,
            "ContentDate": date,
            "AcquisitionTime": time,
            "ContentTime": time,
            "Rows": pixel_array.shape[0],
            "Columns": pixel_array.shape[1],
            "GantryAngle": gantry_angle,
            # Not correct, there may have been many images in this acquisition
            "ImagesInAcquisition": 1,
            "PatientOrientation": "",
            "SamplesPerPixel": 1,
            "PhotometricInterpretation": "MONOCHROME2",
            "BeamLimitingDeviceAngle": collimator_angle,
            # Can be implemented in general
            "BitsAllocated": 16,
            "BitsStored": 16,
            "HighBit": 15,
            "RTImageLabel": "",
            "RTImagePlane": "NORMAL",
            "PixelRepresentation": 0,
            "XRayImageReceptorAngle": 0.0,
            "RTImagePosition": None,
            "PatientSupportAngle": table_angle,
            "PixelData": pixel_array.tobytes(),
            "RadiationMachineSAD": SAD,
            "RTImageSID": SID,
            "PrimaryDosimeterUnit": "",
            "ImagePlanePixelSpacing": [pixel_spacing, pixel_spacing],
        }
    )
    ds.file_meta = pydicom.dataset.FileMetaDataset()

    return ds
