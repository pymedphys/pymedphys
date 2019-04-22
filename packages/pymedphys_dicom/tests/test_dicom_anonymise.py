from os import makedirs, replace
from os.path import abspath, basename, dirname, join as pjoin
from uuid import uuid4

import pydicom
from pymedphys_dicom.dicom import (
    anonymise_dataset,
    anonymise_directory,
    anonymise_file,
    BaselineDicomDictionary,
    IDENTIFYING_KEYWORDS,
    is_anonymised_dataset,
    is_anonymised_directory,
    is_anonymised_file
)
from pymedphys_utilities.utilities import remove_file, remove_dir

HERE = dirname(abspath(__file__))
DATA_DIR = pjoin(HERE, 'data', 'anonymise')
dicom_test_filepath = pjoin(DATA_DIR, "RP.almost_anonymised.dcm")


def test_is_anonymised_dataset():
    ds = pydicom.dcmread(dicom_test_filepath)

    assert not is_anonymised_dataset(ds)

    ds_anon_manual = ds
    ds_anon_manual.PatientName = "Anonymous"


    ds_anon_func = anonymise_dataset(ds, delete_private_tags=False,
                                     copy_dataset=True)

    elems_anon_manual = sorted(list(ds_anon_manual.iterall()), key = lambda x: x.tag)
    elems_anon_func = sorted(list(ds_anon_func.iterall()), key = lambda x: x.tag)
    assert elems_anon_manual == elems_anon_func

    assert not is_anonymised_dataset(ds_anon_manual, ignore_private_tags=False)
    assert not is_anonymised_dataset(ds_anon_func, ignore_private_tags=False)
    assert is_anonymised_dataset(ds_anon_manual, ignore_private_tags=True)
    assert is_anonymised_dataset(ds_anon_func, ignore_private_tags=True)

    ds_anon_func_full = anonymise_dataset(ds, delete_private_tags=True)
    assert is_anonymised_dataset(ds_anon_func_full, ignore_private_tags=False)


def test_is_anonymised_file():
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


def test_is_anonymised_directory():
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


def test_tags_to_anonymise_in_dicom_dict_baseline():
    baseline_keywords = [val[4] for val in BaselineDicomDictionary.values()]
    assert set(IDENTIFYING_KEYWORDS).issubset(baseline_keywords)
