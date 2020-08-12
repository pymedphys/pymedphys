import logging
import os
import subprocess
import tempfile
from os.path import basename, exists
from os.path import join as pjoin
from shutil import copyfile

import pytest

import pydicom

from pymedphys._dicom.anonymise import (
    anonymise_file,
    is_anonymised_directory,
    is_anonymised_file,
)
from pymedphys._dicom.utilities import remove_file
from pymedphys._experimental.pseudonymisation import (
    get_default_pseudonymisation_keywords,
    strategy,
)
from pymedphys.tests.dicom.test_anonymise import (
    TEST_ANON_BASENAME_DICT,
    get_test_filepaths,
)


@pytest.mark.pydicom
def test_pseudonymise_file():
    for test_file_path in get_test_filepaths():
        _test_pseudonymise_file_at_path(test_file_path)


def _test_pseudonymise_file_at_path(test_file_path):
    assert not is_anonymised_file(test_file_path)
    identifying_keywords_for_pseudo = get_default_pseudonymisation_keywords()
    logging.info("Using pseudonymisation keywords")
    replacement_strategy = strategy.pseudonymisation_dispatch
    logging.info("Using pseudonymisation strategy")

    with tempfile.TemporaryDirectory() as output_directory:
        pseudonymised_file_path = anonymise_file(
            dicom_filepath=test_file_path,
            output_filepath=output_directory,
            delete_original_file=False,
            anonymise_filename=True,
            replace_values=True,
            # keywords_to_leave_unchanged=None,
            delete_private_tags=True,
            delete_unknown_tags=True,
            replacement_strategy=replacement_strategy,
            identifying_keywords=identifying_keywords_for_pseudo,
        )

        assert exists(pseudonymised_file_path)
        ds_input = pydicom.dcmread(test_file_path, force=True)
        ds_pseudo = pydicom.dcmread(pseudonymised_file_path, force=True)
        # simplistic stand-in to make sure *something* is happening
        assert ds_input["PatientID"].value != ds_pseudo["PatientID"].value
        # make sure that we are not accidentally using the hardcode replacement approach
        assert ds_pseudo["PatientID"].value not in ["", "Anonymous"]


@pytest.mark.slow
@pytest.mark.pydicom
@pytest.mark.skipif(
    "SUBPACKAGE" in os.environ, reason="Need to extract CLI out of subpackages"
)
def test_pseudonymise_cli(tmp_path):
    for test_file_path in get_test_filepaths():
        _test_pseudonymise_cli_for_file(tmp_path, test_file_path)


def _test_pseudonymise_cli_for_file(tmp_path, test_file_path):

    temp_filepath = pjoin(tmp_path, "test.dcm")
    try:
        logging.info("CLI test on %s", test_file_path)

        copyfile(test_file_path, temp_filepath)
        test_anon_basename = TEST_ANON_BASENAME_DICT[basename(test_file_path)]
        temp_anon_filepath = pjoin(tmp_path, test_anon_basename)
        # Basic file pseudonymisation
        # Initially, just make sure it exits with zero and doesn't fail to generate output
        assert not is_anonymised_file(temp_filepath)
        assert not exists(temp_anon_filepath)

        anon_file_command = "pymedphys --verbose experimental dicom anonymise --pseudo".split() + [
            temp_filepath
        ]
        logging.info("Command line: %s", anon_file_command)
        try:
            subprocess.check_call(anon_file_command)
            # assert is_anonymised_file(temp_anon_filepath)
            assert exists(temp_filepath)
            ds_input = pydicom.dcmread(temp_filepath, force=True)
            ds_pseudo = pydicom.dcmread(temp_anon_filepath, force=True)
            assert ds_input["PatientID"].value != ds_pseudo["PatientID"].value
        finally:
            remove_file(temp_anon_filepath)

        # Basic dir anonymisation
        assert not is_anonymised_directory(tmp_path)
        assert not exists(temp_anon_filepath)

        anon_dir_command = "pymedphys --verbose experimental dicom anonymise --pseudo".split() + [
            str(tmp_path)
        ]
        try:
            subprocess.check_call(anon_dir_command)
            # assert is_anonymised_file(temp_anon_filepath)
            assert exists(temp_filepath)
        finally:
            remove_file(temp_anon_filepath)
    finally:
        remove_file(temp_filepath)
