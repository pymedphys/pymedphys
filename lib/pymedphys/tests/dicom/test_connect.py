# Copyright (C) 2020 University of New South Wales & Ingham Institute
# Copyright (C) 2020 Stuart Swerdloff and Simon Biggs

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# pylint: disable=redefined-outer-name, no-member

import pathlib
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from unittest.mock import Mock

from pymedphys._imports import psutil, pydicom, pynetdicom, pytest

import pymedphys._utilities.test as pmp_test_utils
from pymedphys._dicom.connect.listen import (
    DicomListener,
    hierarchical_dicom_storage_directory,
)
from pymedphys._dicom.connect.send import DicomSender
from pymedphys._dicom.create import dicom_dataset_from_dict

# TODO How to determine an appropriate port for testing?
TEST_PORT = 9988

METHOD_MOCK = Mock()


def _build_hierarchical_path_to_plan(
    storage_path: pathlib.Path, test_dataset: "pydicom.dataset.Dataset"
) -> pathlib.Path:
    file_path = hierarchical_dicom_storage_directory(
        storage_path, test_dataset
    ).joinpath(f"RP.{test_dataset.SOPInstanceUID}.dcm")
    return file_path


def check_dicom_agrees(ds1, ds2):
    """Asserts that the two DICOM datasets are identical on certain fields."""

    assert ds1.SOPInstanceUID == ds2.SOPInstanceUID
    assert ds1.SeriesInstanceUID == ds2.SeriesInstanceUID
    assert ds1.StudyInstanceUID == ds2.StudyInstanceUID
    assert ds1.PatientID == ds2.PatientID
    assert ds1.Modality == ds2.Modality
    assert ds1.Manufacturer == ds2.Manufacturer

    assert len(ds1.BeamSequence) == len(ds2.BeamSequence)
    assert ds1.BeamSequence[0].Manufacturer == ds2.BeamSequence[0].Manufacturer


def prepare_listen_command(port, receive_directory, ae_title):

    return [
        pmp_test_utils.get_executable_even_when_embedded(),
        "-m",
        "pymedphys",
        "--verbose",
        "dicom",
        "listen",
        str(port),
        "-d",
        str(receive_directory),
        "-a",
        str(ae_title),
    ]


def prepare_send_command(port, ae_title, send_file):

    return [
        pmp_test_utils.get_executable_even_when_embedded(),
        "-m",
        "pymedphys",
        "--verbose",
        "dicom",
        "send",
        "-a",
        str(ae_title),
        "localhost",
        str(port),
        str(send_file),
    ]


@contextmanager
def listener_process(port, receive_directory, ae_title):

    listener_command = prepare_listen_command(port, receive_directory, ae_title)
    proc = subprocess.Popen(
        listener_command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    )

    try:
        stream_output = b""
        for b in iter(lambda: proc.stdout.read(1), b""):
            stream_output += b
            if b"Listener Ready" in stream_output:
                break

        yield proc

    finally:
        for child in psutil.Process(proc.pid).children(recursive=True):
            child.kill()
        proc.kill()


@pytest.fixture()
def listener():
    """Initiate the DICOM SCP, and prime the mocking method
    so that whatever is done in the on_association_released handler
    is in the mock

    Yields
    -------
    pymedphys._dicom.connect.listen.DicomListener
        reference to the DICOM SCP object
    """
    dicom_listener = DicomListener(
        port=TEST_PORT, on_released_callback=METHOD_MOCK.method
    )
    dicom_listener.start()

    yield dicom_listener

    dicom_listener.stop()


@pytest.mark.pydicom
def test_dicom_listener_echo(listener):
    """Test to ensure that running dicom listener responds to C-ECHO"""

    # Send C-ECHO
    ae = pynetdicom.AE()
    ae.requested_contexts = pynetdicom.VerificationPresentationContexts

    assoc = ae.associate(listener.host, listener.port, ae_title=listener.ae_title)

    result = None
    if assoc.is_established:
        status = assoc.send_c_echo()

        if status:
            result = status.Status

        assoc.release()

    # Check we got a valid result
    assert result == 0


@pytest.fixture()
def test_dataset():
    """pytest fixture to returns a dummy DICOM dataset for testing

    Returns
    -------
    test_dataset : ``pydicom.dataset.Dataset``
        A dummy DICOM dataset
    """

    # Create a test DICOM object
    test_uid = pydicom.uid.generate_uid()
    test_series_uid = pydicom.uid.generate_uid()
    test_study_uid = pydicom.uid.generate_uid()
    patient_id = "987654321PyMedPhysID"
    test_dataset = dicom_dataset_from_dict(
        {
            "SOPClassUID": pynetdicom.sop_class.RTPlanStorage,
            "SOPInstanceUID": test_uid,
            "SeriesInstanceUID": test_series_uid,
            "StudyInstanceUID": test_study_uid,
            "PatientID": patient_id,
            "Modality": "RTPlan",
            "Manufacturer": "PyMedPhys",
            "BeamSequence": [{"Manufacturer": "PyMedPhys"}],
        }
    )

    file_meta = pydicom.dataset.FileMetaDataset(
        dicom_dataset_from_dict(
            {
                "FileMetaInformationVersion": bytes([0, 1]),
                "MediaStorageSOPClassUID": pynetdicom.sop_class.RTPlanStorage,
                "MediaStorageSOPInstanceUID": test_uid,
                "TransferSyntaxUID": pydicom.uid.ImplicitVRLittleEndian,
                "ImplementationClassUID": pydicom.uid.PYDICOM_IMPLEMENTATION_UID,
                "ImplementationVersionName": "PYMEDPHYSDCM",
            }
        )
    )

    test_dataset.file_meta = file_meta
    test_dataset.is_implicit_VR = True
    test_dataset.is_little_endian = True
    test_dataset.fix_meta_info(enforce_standard=True)

    return test_dataset


@pytest.mark.pydicom
def test_hierarchical_dicom_storage_directory(test_dataset):
    """Test to ensure the constructed directory for storing a DICOM object
    is in the Patient/Study/Series hierarchy that aligns with DICOM Query
    """
    test_dir = pathlib.Path(tempfile.mkdtemp())
    expected_directory = test_dir.joinpath(
        test_dataset.PatientID,
        test_dataset.StudyInstanceUID,
        test_dataset.SeriesInstanceUID,
    )
    created_directory = hierarchical_dicom_storage_directory(test_dir, test_dataset)
    assert created_directory == expected_directory


@pytest.mark.pydicom
def test_dicom_listener_send(listener, test_dataset):
    """Test to ensure that running DicomListener receives a stores a DICOM file"""

    METHOD_MOCK.reset_mock()

    # Send the data to the listener
    ae = pynetdicom.AE()
    ae.add_requested_context(pynetdicom.sop_class.RTPlanStorage)
    assoc = ae.associate(listener.host, listener.port, ae_title="PYMEDPHYSTEST")
    assert assoc.is_established
    status = assoc.send_c_store(test_dataset)
    assert status.Status == 0
    assoc.release()

    # Check that it was received
    METHOD_MOCK.method.assert_called_once()
    # The mocked method was on_association_release (see fixture above)
    # on_association_release assigns the ultimate directory in which data was stored
    # which is at the series level, rather than the top level directory above the patient level
    args, _ = METHOD_MOCK.method.call_args_list[0]
    association_storage_path = args[0]
    assert association_storage_path.exists()
    file_path = pathlib.Path(association_storage_path).joinpath(
        f"RP.{test_dataset.SOPInstanceUID}.dcm"
    )
    assert file_path.exists()

    read_dataset = pydicom.read_file(file_path)
    assert read_dataset.SeriesInstanceUID == test_dataset.SeriesInstanceUID

    # Clean up after ourselves
    shutil.rmtree(association_storage_path)


@pytest.mark.pydicom
def test_dicom_listener_send_conflicting_file(listener, test_dataset):
    """Test to ensure that running DicomListener handles conflicting DICOM files
    properly.
    """

    METHOD_MOCK.reset_mock()

    # Send the data to the listener
    ae = pynetdicom.AE()
    ae.add_requested_context(pynetdicom.sop_class.RTPlanStorage)
    assoc = ae.associate(listener.host, listener.port, ae_title="PYMEDPHYSTEST")
    assert assoc.is_established
    status = assoc.send_c_store(test_dataset)
    assert status.Status == 0
    assoc.release()

    # Send again, should succeed without writing the same file again
    ae = pynetdicom.AE()
    ae.add_requested_context(pynetdicom.sop_class.RTPlanStorage)
    assoc = ae.associate(listener.host, listener.port, ae_title="PYMEDPHYSTEST")
    assert assoc.is_established
    status = assoc.send_c_store(test_dataset)
    assert status.Status == 0
    assoc.release()

    # Modify the file to make it conflict
    args, _ = METHOD_MOCK.method.call_args_list[0]
    association_storage_path = args[0]
    file_path = pathlib.Path(association_storage_path).joinpath(
        f"RP.{test_dataset.SOPInstanceUID}.dcm"
    )
    ds = pydicom.read_file(file_path)
    ds.Manufacturer = "PyMedPhysModified"
    ds.save_as(file_path, write_like_original=False)

    # Send again, should save the file in the orphan directory
    ae = pynetdicom.AE()
    ae.add_requested_context(pynetdicom.sop_class.RTPlanStorage)
    assoc = ae.associate(listener.host, listener.port, ae_title="PYMEDPHYSTEST")
    assert assoc.is_established
    status = assoc.send_c_store(test_dataset)
    assert status.Status == 0
    assoc.release()

    # Check the original file is the same
    read_dataset = pydicom.read_file(file_path)
    assert read_dataset.Manufacturer == "PyMedPhysModified"

    # Check the other file was written to the orphan directory
    orphan_files = list(association_storage_path.joinpath("orphan").glob("*"))
    assert len(orphan_files) == 1
    orphan_dataset = pydicom.read_file(orphan_files[0])
    assert orphan_dataset.Manufacturer == "PyMedPhys"

    # Clean up after ourselves
    shutil.rmtree(association_storage_path)


@pytest.mark.pydicom
def test_dicom_listener_cli(test_dataset):
    """Test the command line interface to the DicomListener"""

    scp_ae_title = "PYMEDPHYSTEST"

    with tempfile.TemporaryDirectory() as tmp_directory:

        test_directory = pathlib.Path(tmp_directory)

        with listener_process(TEST_PORT, test_directory, scp_ae_title):

            # Send the data to the listener
            ae = pynetdicom.AE()
            ae.add_requested_context(pynetdicom.sop_class.RTPlanStorage)
            assoc = ae.associate("127.0.0.1", TEST_PORT, ae_title=scp_ae_title)
            assert assoc.is_established
            status = assoc.send_c_store(test_dataset)
            assert status.Status == 0
            assoc.release()

        file_path = _build_hierarchical_path_to_plan(test_directory, test_dataset)
        read_dataset = pydicom.read_file(file_path)
        assert read_dataset.SeriesInstanceUID == test_dataset.SeriesInstanceUID


@pytest.mark.pydicom
def test_dicom_sender(test_dataset):
    """Test sending DICOM objects using the DicomSender"""

    scp_ae_title = "PYMEDPHYSTEST"

    with tempfile.TemporaryDirectory() as tmp_directory:

        test_directory = pathlib.Path(tmp_directory)
        receive_directory = test_directory.joinpath("receive")
        receive_directory.mkdir()

        with listener_process(TEST_PORT, receive_directory, scp_ae_title):

            dicom_sender = DicomSender(
                host="127.0.0.1", port=TEST_PORT, ae_title=scp_ae_title
            )

            assert dicom_sender.verify()
            dicom_sender.send([test_dataset])

        dcm_files = receive_directory.glob("**/*.dcm")
        dcm_file = next(dcm_files)
        ds = pydicom.read_file(dcm_file)
        check_dicom_agrees(ds, test_dataset)


@pytest.mark.pydicom
def test_dicom_sender_cli(test_dataset):
    """Test the command line interface to the DicomSender"""

    scp_ae_title = "PYMEDPHYSTEST"

    with tempfile.TemporaryDirectory() as tmp_directory:

        test_directory = pathlib.Path(tmp_directory)
        send_directory = test_directory.joinpath("send")
        send_directory.mkdir()
        send_file = send_directory.joinpath("test.dcm")
        test_dataset.save_as(send_file, write_like_original=False)

        receive_directory = test_directory.joinpath("receive")
        receive_directory.mkdir()

        sender_command = prepare_send_command(TEST_PORT, scp_ae_title, send_file)

        with listener_process(TEST_PORT, receive_directory, scp_ae_title) as lp:

            subprocess.call(sender_command)

            stream_output = b""
            for b in iter(lambda: lp.stdout.read(1), b""):
                stream_output += b
                if b"DICOM object received" in stream_output:
                    break

        dcm_files = receive_directory.glob("**/*.dcm")
        dcm_file = next(dcm_files)
        ds = pydicom.read_file(dcm_file)
        check_dicom_agrees(ds, test_dataset)
