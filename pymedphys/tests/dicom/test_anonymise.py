import json
import os
import subprocess
from copy import deepcopy
from os.path import abspath, basename, dirname, exists
from os.path import join as pjoin
from shutil import copyfile
from uuid import uuid4

import pytest

import pydicom
import pydicom.datadict
import pydicom.dataset
import pydicom.filereader
import pydicom.tag

from pymedphys._dicom import create
from pymedphys._dicom.anonymise import (
    IDENTIFYING_KEYWORDS,
    IDENTIFYING_KEYWORDS_FILEPATH,
    anonymise_directory,
    anonymise_file,
    get_baseline_keyword_vr_dict,
    is_anonymised_dataset,
    is_anonymised_directory,
    is_anonymised_file,
    label_dicom_filepath_as_anonymised,
)
from pymedphys._dicom.constants import get_baseline_dicom_dict
from pymedphys._dicom.utilities import remove_file
from pymedphys.dicom import anonymise as anonymise_dataset

HERE = dirname(abspath(__file__))
DATA_DIR = pjoin(HERE, "data", "anonymise")
TEST_FILEPATH = pjoin(DATA_DIR, "RP.almost_anonymised.dcm")

# TODO: TEST_ANON_BASENAME will probably instead need to contain the
# PYMEDPHYS_ROOT_UID (or similar) when anonymisation of UIDS is
# implemented
TEST_ANON_BASENAME = (
    "RP.1.2.246.352.71.5.53598612033.430805.20190416135558_Anonymised.dcm"
)
TEST_FILE_META = pydicom.filereader.read_file_meta_info(TEST_FILEPATH)

VR_NON_ANONYMOUS_REPLACEMENT_VALUE_DICT = {
    "AE": "AnAETitle",
    "AS": "1Y",
    "CS": "SMITH",
    "DA": "20190429",
    "DS": "11111111.9",
    "DT": "20190429000700.000000",
    "LO": "Smith",
    "LT": "LongText",
    "OB": (2).to_bytes(2, "little"),
    "OB or OW": (2).to_bytes(2, "little"),
    "OW": (2).to_bytes(2, "little"),
    "PN": "Smith",
    "SH": "Smith",
    "SQ": [pydicom.dataset.Dataset(), pydicom.dataset.Dataset()],
    "ST": "Smith",
    "TM": "000700.000000",
    "UI": "1118",
    "US": 11111,
}


def _check_is_anonymised_dataset_file_and_dir(
    ds, tmp_path, anon_is_expected=True, ignore_private_tags=False
):
    temp_filepath = str(tmp_path / "test.dcm")

    try:
        create.set_default_transfer_syntax(ds)

        ds.file_meta = TEST_FILE_META
        ds.save_as(temp_filepath, write_like_original=False)

        if anon_is_expected:
            assert is_anonymised_dataset(ds, ignore_private_tags)
            assert is_anonymised_file(temp_filepath, ignore_private_tags)
            assert is_anonymised_directory(tmp_path, ignore_private_tags)
        else:
            assert not is_anonymised_dataset(ds, ignore_private_tags)
            assert not is_anonymised_file(temp_filepath, ignore_private_tags)
            assert not is_anonymised_directory(tmp_path, ignore_private_tags)
    finally:
        remove_file(temp_filepath)


def _get_non_anonymous_replacement_value(keyword):
    """Get an appropriate dummy non-anonymised value for a DICOM element based
    on its value representation (VR)"""
    vr = get_baseline_keyword_vr_dict()[keyword]
    return VR_NON_ANONYMOUS_REPLACEMENT_VALUE_DICT[vr]


@pytest.mark.slow
@pytest.mark.pydicom
def test_anonymise_dataset_and_all_is_anonymised_functions(tmp_path):

    # Create dataset with one instance of every identifying keyword and
    # run basic anonymisation tests
    ds = pydicom.dataset.Dataset()
    for keyword in IDENTIFYING_KEYWORDS:
        # Ignore file meta elements for now
        tag = hex(pydicom.datadict.tag_for_keyword(keyword))
        if pydicom.tag.Tag(tag).group == 0x0002:
            continue

        value = _get_non_anonymous_replacement_value(keyword)
        setattr(ds, keyword, value)

    _check_is_anonymised_dataset_file_and_dir(ds, tmp_path, anon_is_expected=False)

    ds_anon = anonymise_dataset(ds)
    _check_is_anonymised_dataset_file_and_dir(ds_anon, tmp_path, anon_is_expected=True)

    # Test the anonymisation and check functions for each identifying
    # element individually.
    for elem in ds_anon.iterall():

        # TODO: AffectedSOPInstanceUID and RequestedSOPInstanceUID
        # are not writing to file. Investigate when UID anonymisation is
        # implemented.
        if elem.keyword in ("AffectedSOPInstanceUID", "RequestedSOPInstanceUID"):
            continue

        ds_single_non_anon_value = deepcopy(ds_anon)
        setattr(
            ds_single_non_anon_value,
            elem.keyword,
            _get_non_anonymous_replacement_value(elem.keyword),
        )
        _check_is_anonymised_dataset_file_and_dir(
            ds_single_non_anon_value, tmp_path, anon_is_expected=False
        )
        ds_single_anon = anonymise_dataset(ds_single_non_anon_value)
        _check_is_anonymised_dataset_file_and_dir(
            ds_single_anon, tmp_path, anon_is_expected=True
        )

    # Test correct handling of private tags
    ds_anon.add(pydicom.dataset.DataElement(0x0043102B, "SS", [4, 4, 0, 0]))
    _check_is_anonymised_dataset_file_and_dir(
        ds_anon, tmp_path, anon_is_expected=False, ignore_private_tags=False
    )
    _check_is_anonymised_dataset_file_and_dir(
        ds_anon, tmp_path, anon_is_expected=True, ignore_private_tags=True
    )

    ds_anon.remove_private_tags()
    _check_is_anonymised_dataset_file_and_dir(
        ds_anon, tmp_path, anon_is_expected=True, ignore_private_tags=False
    )

    # Test blank anonymisation
    # # Sanity check
    _check_is_anonymised_dataset_file_and_dir(ds, tmp_path, anon_is_expected=False)

    ds_anon_blank = anonymise_dataset(ds, replace_values=False)
    _check_is_anonymised_dataset_file_and_dir(
        ds_anon_blank, tmp_path, anon_is_expected=True
    )

    # Test handling of unknown tags by removing PatientName from
    # baseline dict
    patient_name_tag = pydicom.datadict.tag_for_keyword("PatientName")

    try:
        patient_name = get_baseline_dicom_dict().pop(patient_name_tag)

        with pytest.raises(ValueError) as e_info:
            anonymise_dataset(ds)
        assert str(e_info.value).count(
            "At least one of the non-private tags "
            "within your DICOM file is not within "
            "PyMedPhys's copy of the DICOM dictionary."
        )

        ds_anon_delete_unknown = anonymise_dataset(ds, delete_unknown_tags=True)
        _check_is_anonymised_dataset_file_and_dir(
            ds_anon_delete_unknown, tmp_path, anon_is_expected=True
        )
        with pytest.raises(AttributeError) as e_info:
            ds_anon_delete_unknown.PatientName  # pylint: disable = pointless-statement
        assert str(e_info.value).count(
            "'Dataset' object has no attribute " "'PatientName'"
        )

        ds_anon_ignore_unknown = anonymise_dataset(ds, delete_unknown_tags=False)
        _check_is_anonymised_dataset_file_and_dir(
            ds_anon_ignore_unknown, tmp_path, anon_is_expected=True
        )
        assert patient_name_tag in ds_anon_ignore_unknown

    finally:
        get_baseline_dicom_dict().setdefault(patient_name_tag, patient_name)

    # Test copy_dataset=False:
    anonymise_dataset(ds, copy_dataset=False)
    assert is_anonymised_dataset(ds)


@pytest.mark.pydicom
def test_anonymise_file():
    assert not is_anonymised_file(TEST_FILEPATH)
    temp_basename = "{}_{}.dcm".format(".".join(TEST_FILEPATH.split(".")[:-1]), uuid4())

    temp_filepath = pjoin(dirname(TEST_FILEPATH), temp_basename)
    anon_private_filepath = ""
    anon_filepath_orig = ""
    anon_filepath_pres = ""

    try:
        # Private tag handling
        anon_private_filepath = anonymise_file(TEST_FILEPATH, delete_private_tags=False)
        assert not is_anonymised_file(anon_private_filepath, ignore_private_tags=False)
        assert is_anonymised_file(anon_private_filepath, ignore_private_tags=True)

        anon_private_filepath = anonymise_file(TEST_FILEPATH, delete_private_tags=True)
        assert is_anonymised_file(anon_private_filepath, ignore_private_tags=False)

        # Filename is anonymised?
        assert basename(anon_private_filepath) == TEST_ANON_BASENAME

        # Deletion of original file
        copyfile(TEST_FILEPATH, temp_filepath)

        anon_filepath_orig = anonymise_file(temp_filepath, delete_original_file=True)
        assert is_anonymised_file(anon_filepath_orig)
        assert not exists(temp_filepath)

        # Preservation of filename if desired
        expected_filepath = "{}_Anonymised.dcm".format(
            ".".join(TEST_FILEPATH.split(".")[:-1])
        )
        anon_filepath_pres = anonymise_file(TEST_FILEPATH, anonymise_filename=False)
        assert anon_filepath_pres == expected_filepath

    finally:
        remove_file(temp_filepath)
        remove_file(anon_private_filepath)
        remove_file(anon_filepath_orig)
        remove_file(anon_filepath_pres)


@pytest.mark.pydicom
def test_anonymise_directory(tmp_path):
    temp_filepath = tmp_path / "test.dcm"
    temp_anon_filepath = label_dicom_filepath_as_anonymised(temp_filepath)
    try:
        copyfile(TEST_FILEPATH, temp_filepath)
        assert not is_anonymised_directory(tmp_path)

        # Test file deletion
        anonymise_directory(
            tmp_path, delete_original_files=False, anonymise_filenames=False
        )
        # # File should be anonymised but not dir, since original file
        # # is still present.
        assert is_anonymised_file(temp_anon_filepath)
        assert exists(temp_filepath)
        assert not is_anonymised_directory(tmp_path)

        remove_file(temp_anon_filepath)
        anonymise_directory(
            tmp_path, delete_original_files=True, anonymise_filenames=False
        )
        # # File and dir should be anonymised since original file should
        # # have been deleted.
        assert is_anonymised_file(temp_anon_filepath)
        assert not exists(temp_filepath)
        assert is_anonymised_directory(tmp_path)

    finally:
        remove_file(temp_anon_filepath)


@pytest.mark.slow
@pytest.mark.pydicom
@pytest.mark.skipif(
    "SUBPACKAGE" in os.environ, reason="Need to extract CLI out of subpackages"
)
def test_anonymise_cli(tmp_path):

    temp_filepath = str(tmp_path / "test.dcm")
    try:
        copyfile(TEST_FILEPATH, temp_filepath)
        temp_anon_filepath = str(tmp_path / TEST_ANON_BASENAME)
        # Basic file anonymisation
        assert not is_anonymised_file(temp_filepath)
        assert not exists(temp_anon_filepath)

        anon_file_command = "pymedphys dicom anonymise".split() + [temp_filepath]
        try:
            subprocess.check_call(anon_file_command)
            assert is_anonymised_file(temp_anon_filepath)
            assert exists(temp_filepath)
        finally:
            remove_file(temp_anon_filepath)

        # File anonymisation - preserve filenames
        assert not is_anonymised_file(temp_filepath)

        expected_anon_filepath = label_dicom_filepath_as_anonymised(temp_filepath)
        assert not exists(expected_anon_filepath)

        anon_file_pres_command = "pymedphys dicom anonymise -f".split() + [
            temp_filepath
        ]
        try:
            subprocess.check_call(anon_file_pres_command)
            assert is_anonymised_file(expected_anon_filepath)
            assert exists(temp_filepath)
        finally:
            remove_file(expected_anon_filepath)

        # File anonymisation - clear values
        assert not is_anonymised_file(temp_filepath)
        assert not exists(temp_anon_filepath)

        temp_cleared_anon_filepath = str(tmp_path / TEST_ANON_BASENAME)

        anon_file_clear_command = "pymedphys dicom anonymise -c".split() + [
            temp_filepath
        ]
        try:
            subprocess.check_call(anon_file_clear_command)
            assert is_anonymised_file(temp_cleared_anon_filepath)
            assert pydicom.dcmread(temp_cleared_anon_filepath).PatientName == ""
            assert exists(temp_filepath)
        finally:
            remove_file(temp_cleared_anon_filepath)

        # File anonymisation - leave keywords unchanged
        assert not is_anonymised_file(temp_filepath)
        assert not exists(temp_anon_filepath)

        anon_file_keep_command = (
            "pymedphys dicom anonymise".split()
            + [temp_filepath]
            + "-k PatientName".split()
        )
        try:
            subprocess.check_call(anon_file_keep_command)
            assert not is_anonymised_file(temp_anon_filepath)
            ds = pydicom.dcmread(temp_anon_filepath)
            ds.PatientName = "Anonymous"
            assert is_anonymised_dataset(ds)
            assert exists(temp_filepath)
        finally:
            remove_file(temp_anon_filepath)

        # File anonymisation - private tag handling
        assert not is_anonymised_file(temp_filepath)
        assert not exists(temp_anon_filepath)

        anon_file_private_command = "pymedphys dicom anonymise -p".split() + [
            temp_filepath
        ]
        try:
            subprocess.check_call(anon_file_private_command)
            assert not is_anonymised_file(temp_anon_filepath)
            assert is_anonymised_file(temp_anon_filepath, ignore_private_tags=True)
            assert exists(temp_filepath)
        finally:
            remove_file(temp_anon_filepath)

        # TODO: File anonymisation - unknown tag handling
        # # Calling a subprocess reloads BASELINE_DICOM_DICT...

        # Basic dir anonymisation
        assert not is_anonymised_directory(tmp_path)
        assert not exists(temp_anon_filepath)

        anon_dir_command = "pymedphys dicom anonymise".split() + [str(tmp_path)]
        try:
            subprocess.check_call(anon_dir_command)
            assert is_anonymised_file(temp_anon_filepath)
            assert exists(temp_filepath)
        finally:
            remove_file(temp_anon_filepath)
    finally:
        remove_file(temp_filepath)


@pytest.mark.pydicom
def test_tags_to_anonymise_in_dicom_dict_baseline(save_new_identifying_keywords=False):
    baseline_keywords = [val[4] for val in get_baseline_dicom_dict().values()]
    assert set(IDENTIFYING_KEYWORDS).issubset(baseline_keywords)

    if save_new_identifying_keywords:
        with open(IDENTIFYING_KEYWORDS_FILEPATH, "w") as outfile:
            json.dump(IDENTIFYING_KEYWORDS, outfile, indent=2, sort_keys=True)

        # TODO: Keywords to add if/when anonymisation of UIDs is implemented:
        # "AffectedSOPInstanceUID",
        # "ConcatenationUID",
        # "ContextGroupExtensionCreatorUID",
        # "CreatorVersionUID",
        # "DeviceUID",
        # "DigitalSignatureUID",
        # "DimensionOrganizationUID",
        # "DoseReferenceUID",
        # "FailedSOPInstanceUIDList",
        # "FiducialUID",
        # "FrameOfReferenceUID",
        # "InstanceCreatorUID",
        # "IrradiationEventUID",
        # "LargePaletteColorLookupTableUID",
        # "MediaStorageSOPInstanceUID",
        # "PaletteColorLookupTableUID",
        # "ReferencedFrameOfReferenceUID",
        # "ReferencedGeneralPurposeScheduledProcedureStepTransactionUID",
        # "ReferencedSOPInstanceUID",
        # "ReferencedSOPInstanceUIDInFile",
        # "RelatedFrameOfReferenceUID",
        # "RequestedSOPInstanceUID",
        # "SeriesInstanceUID",
        # "SOPInstanceUID",
        # "StorageMediaFileSetUID",
        # "StudyInstanceUID",
        # "SynchronizationFrameOfReferenceUID",
        # "TemplateExtensionCreatorUID",
        # "TemplateExtensionOrganizationUID",
        # "TransactionUID",
        # "UID",
