# Copyright (C) 2018 Matthew Jennings

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
import pydicom
    
from .._level0.libutils import get_imports
IMPORTS = get_imports(globals())

def dicom_anon(dcm, delete_private_tags = True, tags_to_keep = []):
    r"""A simple tool to anonymise a DICOM file.

    Parameters
    ----------
    dcm
        The DICOM file to be anonymised. `dcm` must represent a valid 
        DICOM file in the form of a pydicom FileDataset - ordinarily 
        returned by pydicom.dcmread().
        
    delete_private_tags
        A boolean to flag whether or not to remove all private 
        (non-standard) DICOM tags from the DICOM file. These may 
        also contain identifying information. Defaults to True. 

    tags_to_keep
        A sequence of DICOM tags to exclude from anonymisation. Empty by default.

    Returns
    -------
    dcm_out
        An anonymised copy of the input DICOM file as a pydicom FileDataset

    Raises
    ------
    TypeError
        If `dcm` is not an instance of pydicom.dataset.FileDataset
    """

    # Is this a pydicom FileDataset?
    if not isinstance(dcm, pydicom.dataset.FileDataset):
        raise TypeError("The input argument is a member of {}. " + 
                        "It must be a pydicom FileDataset.".format(type(dcm)))

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