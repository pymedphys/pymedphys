"""A DICOM toolbox.
"""

# pylint: disable = unused-import

from ._dicom.anonymise import anonymise_dataset as anonymise
from ._dicom.dose import (
    depth_dose,
    dicom_dose_interpolate,
    profile,
    zyx_and_dose_from_dataset,
)
from ._dicom.structure.merge import merge_contours
