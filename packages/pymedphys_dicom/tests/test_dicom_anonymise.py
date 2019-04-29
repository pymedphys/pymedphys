from copy import deepcopy
from os import makedirs, replace
from os.path import abspath, basename, dirname, join as pjoin
from uuid import uuid4

from pydicom.datadict import tag_for_keyword
from pydicom.dataset import Dataset, DataElement
import pytest

from pymedphys_dicom.dicom import (
    anonymise_dataset,
    anonymise_directory,
    anonymise_file,
    BaselineDicomDictionary,
    BASELINE_KEYWORD_VR_DICT,
    dicom_dataset_from_dict,
    get_anonymous_replacement_value,
    IDENTIFYING_KEYWORDS,
    is_anonymised_dataset,
    is_anonymised_directory,
    is_anonymised_file
)
from pymedphys_utilities.utilities import remove_file, remove_dir

HERE = dirname(abspath(__file__))
DATA_DIR = pjoin(HERE, 'data', 'anonymise')
dicom_test_filepath = pjoin(DATA_DIR, "RP.almost_anonymised.dcm")

VR_NON_ANONYMOUS_REPLACEMENT_VALUE_DICT = {
    'AS': "1Y",
    'CS': "SMITH",
    'DA': "20190429",
    'DT': "20190429000700.000000",
    'LO': "Smith",
    'PN': "Smith",
    'SH': "Smith",
    'SQ': [Dataset(), Dataset()],
    'ST': "Smith",
    'TM': "000700.000000",
    'UI': "11111118"}


def _get_non_anonymous_replacement_value(keyword):
    """Get an appropriate dummy anonymisation value for a DICOM element
    based on its value representation (VR)
    """
    vr = BASELINE_KEYWORD_VR_DICT[keyword]
    return VR_NON_ANONYMOUS_REPLACEMENT_VALUE_DICT[vr]


def test_anonymise_and_is_anonymised_dataset():

    # Create dict with one instance of every identifying keyword and
    # run basic anonymisation tests
    non_anon_dict = dict.fromkeys(IDENTIFYING_KEYWORDS)

    for key in non_anon_dict:
        non_anon_dict[key] = _get_non_anonymous_replacement_value(key)

    ds_non_anon = dicom_dataset_from_dict(non_anon_dict)
    assert not is_anonymised_dataset(ds_non_anon)

    ds_anon = anonymise_dataset(ds_non_anon)
    assert is_anonymised_dataset(ds_anon)

    # Test anonymisation (and check thereof) for each identifying
    # element individually.
    for elem in ds_anon.iterall():
        ds_single_non_anon_value = deepcopy(ds_anon)
        setattr(ds_single_non_anon_value,
                elem.keyword,
                _get_non_anonymous_replacement_value(elem.keyword))
        assert not is_anonymised_dataset(ds_single_non_anon_value)

        ds_single_anon = anonymise_dataset(ds_single_non_anon_value)
        assert is_anonymised_dataset(ds_single_anon)

    # Test correct handling of private tags
    ds_anon.add(DataElement(0x0043102b, 'SS', [4, 4, 0, 0]))
    assert not is_anonymised_dataset(ds_anon, ignore_private_tags=False)
    assert is_anonymised_dataset(ds_anon, ignore_private_tags=True)

    ds_anon.remove_private_tags()
    assert is_anonymised_dataset(ds_anon, ignore_private_tags=False)

    # Test blank anonymisation
    assert not is_anonymised_dataset(ds_non_anon)  # Sanity check
    ds_anon_blank = anonymise_dataset(ds_non_anon, replace_values=False)
    assert is_anonymised_dataset(ds_anon_blank)

    # Test handling of unknown tags by removing PatientName from
    # baseline dict
    patient_name_tag = tag_for_keyword('PatientName')
    patient_name = BaselineDicomDictionary.pop(patient_name_tag)

    with pytest.raises(ValueError) as e_info:
        anonymise_dataset(ds_non_anon)
    assert str(e_info).count("At least one of the non-private tags "
                             "within your DICOM file is not within "
                             "PyMedPhys's copy of the DICOM dictionary.")

    ds_anon_delete_unknown = anonymise_dataset(ds_non_anon,
                                               delete_unknown_tags=True)
    assert is_anonymised_dataset(ds_anon_delete_unknown)
    with pytest.raises(AttributeError) as e_info:
        ds_anon_delete_unknown.PatientName = ''
    assert str(e_info).count("'Dataset' object has no attribute "
                             "'PatientName'")

    ds_anon_ignore_unknown = anonymise_dataset(ds_non_anon,
                                               delete_unknown_tags=False)
    assert is_anonymised_dataset(ds_anon_ignore_unknown)
    assert patient_name_tag in ds_anon_ignore_unknown

    patient_name = BaselineDicomDictionary.setdefault(patient_name_tag,
                                                      patient_name)

    # Test copy_dataset=False:
    ds_anon_uncopied = anonymise_dataset(ds_non_anon, copy_dataset=False)
    assert is_anonymised_dataset(ds_anon_uncopied)
    assert is_anonymised_dataset(ds_non_anon)


def test_anonymise_and_is_anonymised_file():
    assert not is_anonymised_file(dicom_test_filepath)

    # anonymous_filepath = pjoin(DATA_DIR, "RP.almost_anonymised.dcm")

    dicom_anon_filepath = anonymise_file(dicom_test_filepath,
                                         delete_private_tags=False)

    assert not is_anonymised_file(dicom_anon_filepath,
                                  ignore_private_tags=False)
    assert is_anonymised_file(dicom_anon_filepath,
                              ignore_private_tags=True)

    dicom_anon_filepath = anonymise_file(dicom_test_filepath,
                                         delete_private_tags=True)
    assert is_anonymised_file(dicom_anon_filepath,
                              ignore_private_tags=False)


def test_anonymise_and_is_anonymised_directory():
    dirpath_expected_to_fail = DATA_DIR
    assert not is_anonymised_directory(dirpath_expected_to_fail)

    dirpath_expected_to_pass = pjoin(DATA_DIR, 'Anonymous_{}'.format(uuid4()))

    anonymous_filepath = anonymise_file(dicom_test_filepath)
    anonymous_filepath_copied = pjoin(dirpath_expected_to_pass,
                                      basename(anonymous_filepath))

    try:
        makedirs(dirpath_expected_to_pass, exist_ok=True)
        replace(anonymous_filepath, anonymous_filepath_copied)

        assert is_anonymised_directory(dirpath_expected_to_pass)

    finally:
        remove_file(anonymous_filepath)
        remove_file(anonymous_filepath_copied)
        remove_dir(dirpath_expected_to_pass)


def test_anonymise_directory_cli():
    pass


def test_tags_to_anonymise_in_dicom_dict_baseline():
    baseline_keywords = [val[4] for val in BaselineDicomDictionary.values()]
    assert set(IDENTIFYING_KEYWORDS).issubset(baseline_keywords)
