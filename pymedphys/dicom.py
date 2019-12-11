"""A DICOM toolbox.
"""

# pylint: disable = unused-import

import apipkg

apipkg.initpkg(
    __name__,
    {
        "anonymise": "._dicom.anonymise:anonymise_dataset",
        "depth_dose": "._dicom.dose:depth_dose",
        "dicom_dose_interpolate": "._dicom.dose:dicom_dose_interpolate",
        "profile": "._dicom.dose:profile",
        "zyx_and_dose_from_dataset": "._dicom.dose:zyx_and_dose_from_dataset",
    },
)
