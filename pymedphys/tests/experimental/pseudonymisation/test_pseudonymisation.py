import logging
import os
import subprocess
import tempfile
from os.path import exists
from os.path import join as pjoin
from shutil import copyfile

import pytest

import pydicom

from pymedphys._dicom.anonymise import (
    anonymise_dataset,
    anonymise_file,
    is_anonymised_directory,
    is_anonymised_file,
)
from pymedphys._dicom.constants.core import DICOM_SOP_CLASS_NAMES_MODE_PREFIXES
from pymedphys._dicom.utilities import remove_file
from pymedphys.experimental import pseudonymisation as pseudonymisation_api
from pymedphys.tests.dicom.test_anonymise import get_test_filepaths


@pytest.mark.pydicom
def test_pseudonymise_file():
    identifying_keywords_for_pseudo = (
        pseudonymisation_api.get_default_pseudonymisation_keywords()
    )
    logging.info("Using pseudonymisation keywords")
    replacement_strategy = pseudonymisation_api.pseudonymisation_dispatch
    logging.info("Using pseudonymisation strategy")
    for test_file_path in get_test_filepaths():
        _test_pseudonymise_file_at_path(
            test_file_path,
            test_identifying_keywords=identifying_keywords_for_pseudo,
            test_replacement_strategy=replacement_strategy,
        )


@pytest.mark.pydicom
def test_identifier_with_unknown_vr():
    # The fundamental feature being tested is behaviour in
    # response to a programmer error.
    # The programmer error is specification of an identifier that has a VR
    # that has not been addressed in the strategy.
    # However, because the strategy is only applied when the identifier is found
    # in the dataset, the error will only surface in that circumstance
    replacement_strategy = pseudonymisation_api.pseudonymisation_dispatch
    logging.info("Using pseudonymisation strategy")
    identifying_keywords_with_vr_unknown_to_strategy = ["CodingSchemeURL", "PatientID"]
    logging.info("Using keyword with VR = UR")

    ds_input = pydicom.Dataset()
    ds_input.PatientID = "ABC123"
    # not expected to cause problems if the identifier with unknown VR is not in the data
    assert (
        anonymise_dataset(
            ds_input,
            replacement_strategy=replacement_strategy,
            identifying_keywords=identifying_keywords_with_vr_unknown_to_strategy,
        )
        is not None
    )

    # should raise the error if the identifier with unknown VR is in the data
    with pytest.raises(KeyError):
        ds_input.CodingSchemeURL = "https://scheming.coders.co.nz"
        anonymise_dataset(
            ds_input,
            replacement_strategy=replacement_strategy,
            identifying_keywords=identifying_keywords_with_vr_unknown_to_strategy,
        )


def _test_pseudonymise_file_at_path(
    test_file_path, test_identifying_keywords=None, test_replacement_strategy=None
):
    assert not is_anonymised_file(test_file_path)
    if test_identifying_keywords is None:
        identifying_keywords_for_pseudo = (
            pseudonymisation_api.get_default_pseudonymisation_keywords()
        )
        logging.info("Using pseudonymisation keywords")
    else:
        identifying_keywords_for_pseudo = test_identifying_keywords
    if test_replacement_strategy is None:
        replacement_strategy = pseudonymisation_api.pseudonymisation_dispatch
        logging.info("Using pseudonymisation strategy")
    else:
        replacement_strategy = test_replacement_strategy

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
        # debug print + Assert to force the print
        # print("Pseudonymised file at: ", pseudonymised_file_path)
        # assert False
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

        # Basic file pseudonymisation
        # Initially, just make sure it exits with zero and doesn't fail to generate output
        assert not is_anonymised_file(temp_filepath)

        # need the SOP Instance UID and SOP Class name to figure out the destination file name
        # but will also be using the dataset to do some comparisons.
        ds_input: pydicom.FileDataset = pydicom.dcmread(temp_filepath, force=True)

        pseudo_sop_instance_uid = pseudonymisation_api.pseudonymisation_dispatch["UI"](
            ds_input.SOPInstanceUID
        )

        sop_class_uid: pydicom.dataelem.DataElement = ds_input.SOPClassUID

        mode_prefix = DICOM_SOP_CLASS_NAMES_MODE_PREFIXES[
            sop_class_uid.name  # pylint: disable = no-member
        ]
        temp_anon_filepath = pjoin(
            tmp_path,
            "{}.{}_Anonymised.dcm".format(mode_prefix, pseudo_sop_instance_uid),
        )
        assert not exists(temp_anon_filepath)

        anon_file_command = "pymedphys --verbose experimental dicom anonymise --pseudo".split() + [
            temp_filepath
        ]
        logging.info("Command line: %s", anon_file_command)
        try:
            subprocess.check_call(anon_file_command)
            assert exists(temp_anon_filepath)
            # assert is_anonymised_file(temp_anon_filepath)
            assert exists(temp_filepath)

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
