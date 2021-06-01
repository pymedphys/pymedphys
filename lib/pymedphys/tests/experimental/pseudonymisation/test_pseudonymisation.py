import logging
import os
import pathlib
import subprocess
import tempfile
from os.path import exists
from os.path import join as pjoin
from shutil import copyfile

from pymedphys._imports import pydicom, pytest

import pymedphys._utilities.test as pmp_test_utils
from pymedphys._dicom.anonymise import (
    anonymise_dataset,
    anonymise_file,
    is_anonymised_directory,
    is_anonymised_file,
)
from pymedphys._dicom.constants.core import DICOM_SOP_CLASS_NAMES_MODE_PREFIXES
from pymedphys._dicom.utilities import remove_file
from pymedphys.tests.dicom.test_anonymise import (
    dicom_dataset_from_dict,
    get_test_filepaths,
)

from pymedphys._experimental.pseudonymisation import api as pseudonymisation_api


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


def _assert_values_changed_and_not_hardcoded(test_file_path, pseudonymised_file_path):
    ds_input = pydicom.dcmread(test_file_path, force=True)
    ds_pseudo = pydicom.dcmread(pseudonymised_file_path, force=True)
    # simplistic stand-in to make sure *something* is happening
    assert ds_input["PatientID"].value != ds_pseudo["PatientID"].value
    # make sure that we are not accidentally using the hardcode replacement approach
    assert ds_pseudo["PatientID"].value not in ["", "Anonymous"]


@pytest.mark.pydicom
def test_pseudonymise_convenience_api():

    for test_file_path in get_test_filepaths():
        output_file = pseudonymisation_api.pseudonymise(test_file_path)  # using facade
        assert exists(output_file)
        os.remove(output_file)

    with pytest.raises(FileNotFoundError):
        output_file = pseudonymisation_api.pseudonymise("/tmp/bogus_non_existent_file")

    with tempfile.TemporaryDirectory() as input_directory:
        for test_file_path in get_test_filepaths():
            test_base_name = os.path.basename(test_file_path)
            input_path = pathlib.Path(input_directory).joinpath(test_base_name)
            copyfile(test_file_path, input_path)

        with tempfile.TemporaryDirectory() as output_directory:
            pseudo_file_list = pseudonymisation_api.pseudonymise(
                input_directory, output_path=output_directory
            )
            assert pseudo_file_list is not None

            # just making sure that the values have changed and aren't
            # the hardcode values.
            for input_file, pseudo_file in zip(get_test_filepaths(), pseudo_file_list):
                _assert_values_changed_and_not_hardcoded(input_file, pseudo_file)


@pytest.mark.pydicom
def test_identifier_with_DS_vr():
    # PatientWeight is of type DS
    # Because the strategy is only applied when the identifier is found
    # in the dataset, the defect only surfaced in that circumstance
    replacement_strategy = pseudonymisation_api.pseudonymisation_dispatch
    logging.info("Using pseudonymisation strategy")
    identifying_keywords = ["PatientID", "PatientWeight"]
    ds_input = pydicom.Dataset()
    ds_input.PatientID = "ABC123"
    ds_input.PatientWeight = "73.2"
    # not expected to cause problems
    ds_pseudo = anonymise_dataset(
        ds_input,
        replacement_strategy=replacement_strategy,
        identifying_keywords=identifying_keywords,
    )
    assert ds_pseudo is not None
    assert ds_pseudo.PatientWeight != ds_input.PatientWeight
    assert ds_pseudo.PatientWeight <= (ds_input.PatientWeight * 10.0)
    assert ds_pseudo.PatientWeight >= (ds_input.PatientWeight * 0.1)


@pytest.mark.pydicom
def test_identifier_with_utc_DT_vr():
    # in the dataset, the defect only surfaced in that circumstance
    replacement_strategy = pseudonymisation_api.pseudonymisation_dispatch
    logging.info("Using pseudonymisation strategy")
    identifying_keywords = ["PatientID", "AcquisitionDateTime"]
    ds_input = pydicom.Dataset()
    ds_input.PatientID = "ABC123"
    ds_input.AcquisitionDateTime = "20161117094353+1100"
    # not expected to cause problems
    ds_pseudo = anonymise_dataset(
        ds_input,
        replacement_strategy=replacement_strategy,
        identifying_keywords=identifying_keywords,
    )
    assert ds_pseudo is not None


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

    # test the new "is_valid_strategy_for_keywords", which should indicate
    # that for the keywords supplied, the strategy will fail should it find
    # the keyword in the data (there is a VR it doesn't support)
    assert not pseudonymisation_api.is_valid_strategy_for_keywords(
        identifying_keywords_with_vr_unknown_to_strategy
    )
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


@pytest.mark.pydicom
def test_identifier_is_sequence_vr():
    replacement_strategy = pseudonymisation_api.pseudonymisation_dispatch
    logging.info("Using pseudonymisation strategy")
    identifying_keywords_no_SQ = ["PatientID", "RequestedProcedureID"]
    identifying_keywords_with_SQ_vr = [
        "PatientID",
        "RequestedProcedureID",
        "RequestAttributesSequence",
    ]

    identifying_requested_procedure_id = "Tumour Identification"
    non_identifying_scheduled_procedure_step_id = "Tumour ID with Dual Energy"
    ds_input = dicom_dataset_from_dict(
        {
            "PatientID": "ABC123",
            "RequestAttributesSequence": [
                {
                    "RequestedProcedureID": identifying_requested_procedure_id,
                    "ScheduledProcedureStepID": non_identifying_scheduled_procedure_step_id,
                }
            ],
        }
    )
    # reality check.  earlier attempt at the input
    # was flawed based on a misunderstanding of dicom_dataset_from_dict
    assert ds_input.RequestAttributesSequence[0].RequestedProcedureID is not None

    ds_anon = anonymise_dataset(
        ds_input,
        replacement_strategy=replacement_strategy,
        identifying_keywords=identifying_keywords_with_SQ_vr,
    )
    # demonstrate that the entire sequence is emptied out
    # even though that might make the data fail compliance (if the sequence has type 1
    # or type 2)
    assert "RequestedProcedureID" not in ds_anon.RequestAttributesSequence[0]

    ds_anon = anonymise_dataset(
        ds_input,
        replacement_strategy=replacement_strategy,
        identifying_keywords=identifying_keywords_no_SQ,
    )
    # The sequence is not emptied out
    assert ds_anon.RequestAttributesSequence is not None
    assert ds_anon.RequestAttributesSequence[0] is not None

    assert ds_anon.RequestAttributesSequence[0].RequestedProcedureID is not None
    assert ds_anon.RequestAttributesSequence[0].ScheduledProcedureStepID is not None
    # but an element in the sequence that is an identifier has been pseudonymised
    assert (
        ds_anon.RequestAttributesSequence[0].RequestedProcedureID
        != identifying_requested_procedure_id
    )
    # and an element in the sequence that is not an identifier has been left as is
    assert (
        ds_anon.RequestAttributesSequence[0].ScheduledProcedureStepID
        == non_identifying_scheduled_procedure_step_id
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
@pytest.mark.skip(reason="Pseudonymise CLI is not currently being exposed.")
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

        anon_file_command = (
            [pmp_test_utils.get_executable_even_when_embedded(), "-m"]
            + "pymedphys --verbose experimental dicom anonymise --pseudo".split()
            + [temp_filepath]
        )
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

        anon_dir_command = (
            [pmp_test_utils.get_executable_even_when_embedded(), "-m"]
            + "pymedphys --verbose experimental dicom anonymise --pseudo".split()
            + [str(tmp_path)]
        )
        try:
            subprocess.check_call(anon_dir_command)
            # assert is_anonymised_file(temp_anon_filepath)
            assert exists(temp_filepath)
        finally:
            remove_file(temp_anon_filepath)
    finally:
        remove_file(temp_filepath)
