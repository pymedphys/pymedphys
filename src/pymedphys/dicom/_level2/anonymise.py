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

from glob import glob
from os.path import basename, dirname, join as pjoin
from copy import deepcopy

import numpy as np
import pydicom

from ...libutils import get_imports
from .._level1.dict_baseline import BaselineDicomDictionary, BASELINE_KEYWORD_VR_DICT

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


def anonymise_dicom_dataset(ds, replace_values=True, keywords_to_leave_unchanged=None,
                            delete_private_tags=True, delete_unknown_tags=None,
                            copy_dataset=True):
    r"""A simple tool to anonymise a DICOM file.

    Parameters
    ----------
    ds : pydicom.dataset.Dataset
        The DICOM dataset to be anonymised.

    replace_values : bool, optional
        If set to `True`, anonymised tag values will be replaced with dummy
        "anonymous" values. This is often required for the successful reading of
        anonymised DICOM files in commercial software. If set to `False`,
        anonymised tags are simply given empty string values. Defaults to `True`.

    keywords_to_leave_unchanged : sequence, optional
        A sequence of DICOM keywords (corresponding to tags) to exclude from
        anonymisation. Private and unknown tags can be supplied. Empty by default.

    delete_private_tags : bool, optional
        A boolean to flag whether or not to remove all private
        (non-standard) DICOM tags from the DICOM file. These may
        also contain identifying information. Defaults to `True`.

    delete_unknown_tags : bool, pseudo-optional
        If left as the default value of `None` and `ds` contains tags that are not present in
        PyMedPhys` copy of `pydicom`'s DICOM dictionary, `anonymise_dicom_dataset()` will raise an
        error. The user must then either pass `True` or `False` to proceed. If set to `True`, all
        unrecognised tags that haven't been listed in `keywords_to_leave_unchanged` will be deleted.
        If set to `False`, these tags are simply ignored. Pass `False` with caution, since
        unrecognised tags may contain identifying information.

    copy_dataset : bool, optional
        If True, then a copy of `ds` is returned.

    Returns
    -------
    ds_anon : pydicom.dataset.Dataset
        An anonymised version of the input DICOM dataset.
    """

    if keywords_to_leave_unchanged is None:
        keywords_to_leave_unchanged = []

    if copy_dataset:
        ds_anon = deepcopy(ds)
    else:
        ds_anon = ds

    unknown_tags = unknown_tags_in_dicom_dataset(ds_anon)

    if delete_unknown_tags is None and unknown_tags:
        unknown_keywords = [ds_anon[tag].keyword for tag in unknown_tags]

        raise ValueError(
            "At least one of the non-private tags within your DICOM file is not within "
            "PyMedPhys's copy of the DICOM dictionary. It is possible that one or more of "
            "these tags contain identifying information. The unrecognised tags are:\n\n{}\n\n "
            "To exclude these unknown tags from the anonymised DICOM dataset, pass "
            "`delete_unknown_tags=True` to this function. Any unknown tags passed to "
            "`tags_to_leave_unchanged` will not be deleted. If you'd like to ignore this error "
            "and keep all unknown tags in the anonymised DICOM dataset, pass "
            "`delete_unknown_tags=False` to `anonymise_dicom_dataset()`. Finally, if you "
            "believe the PyMedPhys DICOM dictionary is out of date, please raise an issue on "
            "GitHub at https://github.com/pymedphys/pymedphys/issues."
            .format(unknown_keywords))

    elif delete_unknown_tags:
        unwanted_unknown_tags = []

        for tag in unknown_tags:
            if ds_anon[tag].keyword not in keywords_to_leave_unchanged:
                unwanted_unknown_tags.append(tag)
                del ds_anon[tag]

        for tag in unwanted_unknown_tags:
            if tag in ds_anon:
                raise AssertionError("Could not delete all unwanted, unknown tags.")

    keywords_to_anonymise = list(IDENTIFYING_KEYWORDS)

    if delete_private_tags:
        ds_anon.remove_private_tags()

    # Exclude tags from anonymisation process that have been requested to remain as is
    for keyword in keywords_to_leave_unchanged:
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


def anonymise_dicom_file(dicom_filepath, overwrite_file=False, replace_values=True,
                         keywords_to_leave_unchanged=None, delete_private_tags=True,
                         delete_unknown_tags=None):

    ds = pydicom.dcmread(dicom_filepath)

    if overwrite_file:
        dicom_anon_filepath = dicom_filepath
    else:
        dicom_anon_filepath = pjoin(dirname(dicom_filepath),
                                    "{}.{}_Anonymised".format(basename(dicom_filepath)[0:2],
                                                              ds.SOPInstanceUID))

    ds_anon = anonymise_dicom_dataset(ds=ds,
                                      replace_values=replace_values,
                                      keywords_to_leave_unchanged=keywords_to_leave_unchanged,
                                      delete_private_tags=delete_private_tags,
                                      delete_unknown_tags=delete_unknown_tags,
                                      copy_dataset=False)

    ds_anon.save_as(dicom_anon_filepath)


def anonymise_dicom_files_in_folder(folder, overwrite_files=False, replace_values=True,
                                    keywords_to_leave_unchanged=None, delete_private_tags=True,
                                    delete_unknown_tags=None):

    for dicom_filepath in glob(folder + '/**/*.dcm', recursive=True):
        anonymise_dicom_file(dicom_filepath,
                             overwrite_file=overwrite_files,
                             replace_values=replace_values,
                             keywords_to_leave_unchanged=keywords_to_leave_unchanged,
                             delete_private_tags=delete_private_tags,
                             delete_unknown_tags=delete_unknown_tags)


# def anonymise_dicom_files_cli(args):


def non_private_tags_in_dicom_dataset(ds):
    non_private_tags = [tag for tag in ds if tag.is_private]
    return non_private_tags


def unknown_tags_in_dicom_dataset(ds):

    non_private_tags_in_dataset = non_private_tags_in_dicom_dataset(ds)
    are_non_private_tags_in_dict_baseline = [tag in BaselineDicomDictionary.keys()
                                             for tag in non_private_tags_in_dataset]
    unknown_tags = non_private_tags_in_dataset[np.invert(are_non_private_tags_in_dict_baseline)]

    return unknown_tags


def _get_anonymous_replacement_value(keyword):
    vr = BASELINE_KEYWORD_VR_DICT[keyword]
    return VR_ANONYMOUS_REPLACEMENT_VALUE_DICT[vr]
