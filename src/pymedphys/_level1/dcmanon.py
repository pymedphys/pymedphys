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

import os, time
import copy
import pydicom
from pydicom.misc import is_dicom

import tkinter as tk
from tkinter import filedialog as fd, messagebox as mb, simpledialog as sd
    
from .._level0.libutils import get_imports
IMPORTS = get_imports(globals())

def dicom_anon(dcm, tags_to_keep = []):
    r"""A simple tool to anonymise a DICOM file.

    Parameters
    ----------
    dcm : pydicom.dataset.FileDataset
        The DICOM file to be anonymised. `dcm` must be an instance of 
        pydicom.dataset.FileDataset - ordinarily returned by pydicom.dcmread().
        `dcm` must represent a valid DICOM file.

    tags_to_keep : array_like
        A sequence of DICOM tags to exclude from anonymisation. Empty by default.

    Returns
    -------
    dcm_out : pydicom.dataset.FileDataset
        The anonymised copy of the input DICOM file

    Raises
    ------
    TypeError
        If `dcm` is not an instance of pydicom.dataset.FileDataset
    """

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

    for tag in tags_to_keep:
        try:
            tags_to_anonymise.remove(tag)
        except ValueError:
            # Value not in list. TODO: Warn?
            pass            
                         
    dcm_out = copy.deepcopy(dcm)
    
    for tag in tags_to_anonymise:
        if hasattr(dcm_out, tag):
            setattr(dcm_out, tag, "")

    return dcm_out

if __name__ == '__main__':

    PROGRAM_NAME = "Dicom Anonymiser"
    window = tk.Tk()
    window.withdraw()

    dcm_path = fd.askopenfilename(title = "Open DICOM file to anonymise",                                     
                                  filetypes = [("DICOM files", "*.dcm")])
    if not is_dicom(dcm_path):
        mb.showerror(title=PROGRAM_NAME,
                     message="The selected file is not a DICOM file.")
        window.destroy()
        sys.exit()

    try:
        dcm = pydicom.dcmread(dcm_path)
    except:
        mb.showerror(title=PROGRAM_NAME,
                     message="Could not read DICOM file.")
        window.destroy()
        sys.exit()

    dcm_out = dicom_anon(dcm)

    dcm_out_default_basename = os.path.basename(dcm_path)[:-4] + "_anon.dcm"
    dcm_out_path = fd.asksaveasfilename(title = "Save anonymised DICOM file",
                                        initialdir = os.path.dirname(dcm_path),
                                        filetypes = [("DICOM files", "*.dcm")],
                                        initialfile = dcm_out_default_basename)

    try:
        pydicom.dcmwrite(dcm_out_path, dcm_out)
    except:
        mb.showerror(title="PROGRAM_NAME",
                     message="Could not save anonymised DICOM file.")
        window.destroy()
        sys.exit()




