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

from ...libutils import get_imports

from .._level1.dicom_dict_baseline import BaselineDicomDictionary, BASELINE_KEYWORD_VR_DICT

IMPORTS = get_imports(globals())


IDENTIFYING_KEYWORDS = ("AccessionNumber",
                        "AcquisitionDate",
                        "AcquisitionDateTime",
                        "AcquisitionTime",
                        "ContentCreatorName",
                        "ContentDate",
                        "ContentTime",
                        "CountryOfResidence",
                        "CurrentPatientLocation",
                        "CurveDate",
                        "CurveTime",
                        "Date",
                        "DateTime",
                        "EthnicGroup",
                        "InstanceCreationDate",
                        "InstanceCreationTime",
                        "InstanceCreatorUID",
                        "InstitutionAddress",
                        "InstitutionalDepartmentName",
                        "InstitutionName",
                        "IssuerOfPatientID",
                        "NameOfPhysiciansReadingStudy",
                        "OperatorsName",
                        "OtherPatientIDs",
                        "OtherPatientNames",
                        "OverlayDate",
                        "OverlayTime",
                        "PatientAddress",
                        "PatientAge",
                        "PatientBirthDate",
                        "PatientBirthName",
                        "PatientBirthTime",
                        "PatientID",
                        "PatientInstitutionResidence",
                        "PatientMotherBirthName",
                        "PatientName",
                        "PatientSex",
                        "PatientTelephoneNumbers",
                        "PerformingPhysicianIdentificationSequence",
                        "PerformingPhysicianName",
                        "PersonName",
                        "PhysiciansOfRecord",
                        "PhysiciansOfRecordIdentificationSequence",
                        "PhysiciansReadingStudyIdentificationSequence",
                        "ReferringPhysicianAddress",
                        "ReferringPhysicianIdentificationSequence",
                        "ReferringPhysicianName",
                        "ReferringPhysicianTelephoneNumbers",
                        "RegionOfResidence",
                        "ReviewerName",
                        "SecondaryReviewerName",
                        "SeriesDate",
                        "SeriesTime",
                        "StationName",
                        "StudyDate",
                        "StudyID",
                        "StudyTime",
                        "Time",
                        "VerifyingObserverName")


VR_ANONYMOUS_REPLACEMENT_VALUE_DICT = {'AS': "100Y",
                                       'CS': "ANON",
                                       'DA': "20190303",
                                       'DT': "20190303000900.000000",
                                       'LO': "Anonymous",
                                       'PN': "Anonymous",
                                       'SH': "Anonymous",
                                       'SQ': ["Anonymous"],
                                       'ST': "Anonymous",
                                       'TM': "000900.000000",
                                       'UI': "12345678"}

def anonymise_dicom(ds, replace_values=True, delete_private_tags=True, keywords_to_keep=None,
                    ignore_unknown_tags=False):
    r"""A simple tool to anonymise a DICOM file.

    Parameters
    ----------
    ds
        The DICOM file to be anonymised. `ds` must represent a valid
        DICOM file in the form of a `pydicom Dataset` - ordinarily
        returned by `pydicom.dcmread()`.

    replace_values : bool, optional
        If set to `True`, anonymised tag values will be replaced with dummy
        "anonymous" values. This is often required for successful reading of 
        anonymised DICOM files in commercial software. If set to False,
        anonymised tags are simply given empty string values. Defaults to `True`.

    delete_private_tags : bool, optional
        A boolean to flag whether or not to remove all private
        (non-standard) DICOM tags from the DICOM file. These may
        also contain identifying information. Defaults to `True`.

    keywords_to_keep : sequence, optional
        A sequence of DICOM keywords (corresponding to tags) to exclude from
        anonymisation. Empty by default.

    ignore_unknown_tags : bool, optional
        If `pydicom` has updated its DICOM dictionary, this function will raise an
        error since a new identifying tag may have been introduced. Set to `True` to
        ignore this error. Defaults to `False`.

    Returns
    -------
    ds_anon
        An anonymised copy of the input DICOM file as a `pydicom Dataset`

    Raises
    ------
    ValueError
        Raised if `ignore_unknown_tags` is set to False and unrecognised,
        non-private DICOM tags are detected in `ds`
    """

    if keywords_to_keep is None:
        keywords_to_keep = []

    if not ignore_unknown_tags:
        tags_used = list(ds.keys())
        non_private_tags_used = np.array([
            tag for tag in tags_used if not tag.is_private
        ])
        are_tags_used_in_dict_copy = [
            key in BaselineDicomDictionary.keys()
            for key in non_private_tags_used]

        if not np.all(are_tags_used_in_dict_copy):
            unknown_tags = non_private_tags_used[
                np.invert(are_tags_used_in_dict_copy)]

            unknown_tag_names = [
                ds[tag].keyword
                for tag in unknown_tags]

            raise ValueError(
                "At least one of the non-private tags within your DICOM file "
                "is not within PyMedPhys's copy of the DICOM dictionary. It is "
                "possible that one or more of these tags contain identifying "
                "information. The unrecognised tags are:\n\n{}\n\n To ignore "
                "this error, pass `ignore_unknown_tags=True` to "
                "`anonymise_dicom()`. Please inform the creators of PyMedPhys "
                "that the baseline DICOM dictionary is obsolete."
                .format(unknown_tag_names))

    ds_anon = copy.deepcopy(ds)
    keywords_to_anonymise = list(IDENTIFYING_KEYWORDS)

    # Remove private tags from DICOM file unless requested not to.
    if delete_private_tags:
        ds_anon.remove_private_tags()

    # Exclude tags from anonymisation process that have been requested to remain as is
    for keyword in keywords_to_keep:
        try:
            keywords_to_anonymise.remove(keyword)
        except ValueError:
            # Value not in list. TODO: Warn?
            pass

    # Overwrite tags in anonymisation list with an empty string.
    for keyword in keywords_to_anonymise:
        if hasattr(ds_anon, keyword):
            if replace_values:
                replacement_value = _get_anonymous_replacement_value(keyword)
            else:
                replacement_value = ''
            setattr(ds_anon, keyword, replacement_value)

    return ds_anon

def _get_anonymous_replacement_value(keyword):
    vr = BASELINE_KEYWORD_VR_DICT[keyword]
    return VR_ANONYMOUS_REPLACEMENT_VALUE_DICT[vr]
