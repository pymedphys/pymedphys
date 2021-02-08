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

from pymedphys._imports import streamlit as st

import pymedphys._dicom.create as _pp_dcm_create
from pymedphys import _losslessjpeg as lljpeg
from pymedphys._streamlit import categories
from pymedphys._streamlit.utilities import config as st_config

import pymedphys._experimental.wlutz.iview as _pp_wlutz_iview
from pymedphys._experimental.streamlit.utilities.iview import ui as iview_ui

CATEGORY = categories.PLANNING
TITLE = "iView to DICOM"


def main():
    config = st_config.get_config()

    (
        database_table,
        database_directory,
        qa_directory,
        selected_date,
    ) = iview_ui.iview_and_icom_filter_and_align(
        config, advanced_mode=False, filter_angles_by_default=True
    )


def _create_portal_image_dicom_dataset(
    gantry_angle, collimator_angle, table_angle, image_path
):
    """Don't intend this DICOM file to be compliant to the spec.

    Instead, for now, just enough that software such as PIPs will
    happily accept the created file.
    """

    # TODO: Refactor this so that for all pylinac calls a full DICOM
    # file is passed to it in the way that it expects. The image wrapper
    # around pylinac could instead call this first.

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

    sid = 1600.0
    sad = 1000.0

    pixel_spacing = 1 / pixels_per_mm * sid / sad

    ds = _pp_dcm_create.dicom_dataset_from_dict(
        {
            "ImageType": ["ORIGINAL", "PRIMARY", "PORTAL"],
            "Rows": pixel_array.shape[0],
            "Columns": pixel_array.shape[1],
            "GantryAngle": gantry_angle,
            "BeamLimitingDeviceAngle ": collimator_angle,
            "PatientSupportAngle ": table_angle,
            "PixelData": pixel_array,
            "RadiationMachineSAD": sad,
            "RTImageSID": sid,
            "ImagePlanePixelSpacing": [pixel_spacing, pixel_spacing],
        }
    )

    return ds
