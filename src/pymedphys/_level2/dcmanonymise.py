# Copyright (C) 2018 Matthew Jennings, Simon Biggs

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version (the "AGPL-3.0+").

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License and the additional terms for more
# details.

# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

# ADDITIONAL TERMS are also included as allowed by Section 7 of the GNU
# Affero General Public License. These additional terms are Sections 1, 5,
# 6, 7, 8, and 9 from the Apache License, Version 2.0 (the "Apache-2.0")
# where all references to the definition "License" are instead defined to
# mean the AGPL-3.0+.

# You should have received a copy of the Apache-2.0 along with this
# program. If not, see <http://www.apache.org/licenses/LICENSE-2.0>.

import copy
import numpy as np
import pydicom
from .._level1._dcmdictbaseline import DicomDictionary
from .._level0.libutils import get_imports
IMPORTS = get_imports(globals())


def anonymise_dicom(dcm, delete_private_tags=True, tags_to_keep=None,
                    ignore_unknown_tags=False):
    r"""A simple tool to anonymise a DICOM file.

    Parameters
    ----------
    dcm
        The DICOM file to be anonymised. `dcm` must represent a valid
        DICOM file in the form of a `pydicom FileDataset` - ordinarily
        returned by `pydicom.dcmread()`.

    delete_private_tags
        A boolean to flag whether or not to remove all private
        (non-standard) DICOM tags from the DICOM file. These may
        also contain identifying information. Defaults to `True`.

    tags_to_keep
        A sequence of DICOM tags to exclude from anonymisation. Empty by
        default.

    ignore_unknown_tags
        If `pydicom` has updated its DICOM dictionary, this function will raise an
        error since a new identifying tag may have been introduced. Set to `True` to
        ignore this error. Defaults to `False`.

    Returns
    -------
    dcm_out
        An anonymised copy of the input DICOM file as a `pydicom FileDataset`

    Raises
    ------
    TypeError
        If `dcm` is not an instance of `pydicom.dataset.FileDataset`
    """

    if tags_to_keep is None:
        tags_to_keep = []

    if not isinstance(dcm, pydicom.dataset.FileDataset):
        raise TypeError("The input argument is a member of {}. "
                        "It must be a pydicom FileDataset.".format(type(dcm)))

    if not ignore_unknown_tags:
        tags_used = list(dcm.keys())
        non_private_tags_used = np.array([
            tag for tag in tags_used if not tag.is_private
        ])
        are_tags_used_in_dict_copy = [
            key in DicomDictionary.keys() for key in non_private_tags_used]

        if not np.all(are_tags_used_in_dict_copy):
            unknown_tags = non_private_tags_used[
                np.invert(are_tags_used_in_dict_copy)]

            unknown_tag_names = [
                dcm[tag].keyword
                for tag in unknown_tags]

            raise AssertionError(
                "At least one of the non-private tags within your DICOM file "
                "is not "
                "within PyMedPhys's copy of the DICOM dictionary. If this is "
                "the case there is a small chance an introduced tag might be "
                "identifying. The unrecognised tags are:\n\n{}\n\n"
                "To ignore this error, pass a value of True to "
                "`ignore_unknown_tags` within "
                "`anonymise_dicom`. Please inform the creators of PyMedPhys "
                "that the baseline DICOM dictionary is out of date.".format(
                    unknown_tag_names))

    tags_to_anonymise = ["StudyDate",
                         "SeriesDate",
                         "AcquisitionDate",
                         "ContentDate",
                         "OverlayDate",
                         "CurveDate",
                         "AcquisitionDatetime",
                         "StudyTime",
                         "SeriesTime",
                         "AcquisitionTime",
                         "ContentTime",
                         "OverlayTime",
                         "CurveTime",
                         "AccessionNumber",
                         "InstitutionName",
                         "InstitutionAddress",
                         "ReferringPhysicianName",
                         "ReferringPhysicianAddress",
                         "ReferringPhysicianTelephoneNumber",
                         "ReferringPhysicianIdentificationSequence",
                         "InstitutionalDepartmentName",
                         "PhysiciansOfRecord",
                         "PhysiciansOfRecordIdentificationSequence",
                         "PerformingPhysicianName",
                         "PerformingPhysicianIdentificationSequence",
                         "NameOfPhysiciansReadingStudy",
                         "PhysiciansReadingStudyIdentificationSequence",
                         "OperatorsName",
                         "PatientName",
                         "PatientID",
                         "IssuerOfPatientID",
                         "PatientBirthDate",
                         "PatientBirthTime",
                         "PatientSex",
                         "OtherPatientIDs",
                         "OtherPatientNames",
                         "PatientBirthName",
                         "PatientAge",
                         "PatientAddress",
                         "PatientMotherBirthName",
                         "CountryOfResidence",
                         "RegionOfResidence",
                         "PatientTelephoneNumbers",
                         "StudyID",
                         "CurrentPatientLocation",
                         "PatientInstitutionResidence",
                         "DateTime",
                         "Date",
                         "Time",
                         "PersonName",
                         "EthnicGroup",
                         "StationName",
                         "InstanceCreationDate",
                         "InstanceCreationTime",
                         "InstanceCreatorUID"]

    dcm_out = copy.deepcopy(dcm)

    # Remove private tags from DICOM file unless requested not to.
    if delete_private_tags:
        dcm_out.remove_private_tags()

    # Exclude tags from anonymisation process that have been requested to remain as is
    for tag in tags_to_keep:
        try:
            tags_to_anonymise.remove(tag)
        except ValueError:
            # Value not in list. TODO: Warn?
            pass

    # Overwrite tags in anonymisation list with an empty string.
    # TODO: Provide alternative overwrite values?
    for tag in tags_to_anonymise:
        if hasattr(dcm_out, tag):
            setattr(dcm_out, tag, "")

    return dcm_out
