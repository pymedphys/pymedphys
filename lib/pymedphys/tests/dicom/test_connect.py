# Copyright (C) 2020 University of New South Wales & Ingham Institute

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# pylint: disable=redefined-outer-name

import pathlib
import shutil
import tempfile
import time
from unittest.mock import Mock

import pytest

import pydicom
from pynetdicom import AE, VerificationPresentationContexts
from pynetdicom.sop_class import RTPlanStorage  # pylint: disable=no-name-in-module

from pymedphys._dicom.connect.listen import DicomListener
from pymedphys._dicom.create import dicom_dataset_from_dict
from pymedphys._utilities.test import process

# TODO How to determine an appropriate port for testing?
TEST_PORT = 9988

METHOD_MOCK = Mock()


@pytest.fixture()
def listener():

    dicom_listener = DicomListener(
        port=TEST_PORT, on_released_callback=METHOD_MOCK.method
    )
    dicom_listener.start()

    yield dicom_listener

    dicom_listener.stop()


@pytest.mark.pydicom
def test_dicom_listener_echo(listener):
    """Test to ensure that running dicom listener responds to C-ECHO
    """

    # Send C-ECHO
    ae = AE()
    ae.requested_contexts = VerificationPresentationContexts

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
    """pytest fixture to returna a dummy DICOM dataset for testing

    Returns
    -------
    test_dataset : ``pydicom.dataset.Dataset``
        A dummy DICOM dataset
    """

    # Create a test DICOM object
    test_uid = pydicom.uid.generate_uid()
    test_series_uid = pydicom.uid.generate_uid()
    test_dataset = dicom_dataset_from_dict(
        {
            "SOPClassUID": RTPlanStorage,
            "SOPInstanceUID": test_uid,
            "SeriesInstanceUID": test_series_uid,
            "Modality": "RTPlan",
            "Manufacturer": "PyMedPhys",
            "BeamSequence": [{"Manufacturer": "PyMedPhys"}],
        }
    )

    file_meta = pydicom.dataset.FileMetaDataset(
        dicom_dataset_from_dict(
            {
                "FileMetaInformationVersion": "01",
                "MediaStorageSOPClassUID": RTPlanStorage,
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
def test_dicom_listener_send(listener, test_dataset):
    """Test to ensure that running DicomListener receives a stores a DICOM file
    """

    METHOD_MOCK.reset_mock()

    # Send the data to the listener
    ae = AE()
    ae.add_requested_context(RTPlanStorage)
    assoc = ae.associate(listener.host, listener.port, ae_title="PYMEDPHYSTEST")
    assert assoc.is_established
    status = assoc.send_c_store(test_dataset)
    assert status.Status == 0
    assoc.release()

    # Check that it was received
    METHOD_MOCK.method.assert_called_once()
    args, _ = METHOD_MOCK.method.call_args_list[0]
    storage_path = args[0]
    file_path = storage_path / f"RP.{test_dataset.SOPInstanceUID}.dcm"
    assert file_path.exists()

    read_dataset = pydicom.read_file(file_path)
    assert read_dataset.SeriesInstanceUID == test_dataset.SeriesInstanceUID

    # Clean up after ourselves
    shutil.rmtree(storage_path)


@pytest.mark.pydicom
def test_dicom_listener_send_conflicting_file(listener, test_dataset):
    """Test to ensure that running DicomListener handles conflicting DICOM files
    properly.
    """

    METHOD_MOCK.reset_mock()

    # Send the data to the listener
    ae = AE()
    ae.add_requested_context(RTPlanStorage)
    assoc = ae.associate(listener.host, listener.port, ae_title="PYMEDPHYSTEST")
    assert assoc.is_established
    status = assoc.send_c_store(test_dataset)
    assert status.Status == 0
    assoc.release()

    # Send again, should succeed without writing the same file again
    ae = AE()
    ae.add_requested_context(RTPlanStorage)
    assoc = ae.associate(listener.host, listener.port, ae_title="PYMEDPHYSTEST")
    assert assoc.is_established
    status = assoc.send_c_store(test_dataset)
    assert status.Status == 0
    assoc.release()

    # Modify the file to make it conflict
    args, _ = METHOD_MOCK.method.call_args_list[0]
    storage_path = args[0]
    file_path = storage_path.joinpath(f"RP.{test_dataset.SOPInstanceUID}.dcm")
    ds = pydicom.read_file(file_path)
    ds.Manufacturer = "PyMedPhysModified"
    ds.save_as(file_path, write_like_original=False)

    # Send again, should save the file in the orphan directory
    ae = AE()
    ae.add_requested_context(RTPlanStorage)
    assoc = ae.associate(listener.host, listener.port, ae_title="PYMEDPHYSTEST")
    assert assoc.is_established
    status = assoc.send_c_store(test_dataset)
    assert status.Status == 0
    assoc.release()

    # Check the original file is the same
    read_dataset = pydicom.read_file(file_path)
    assert read_dataset.Manufacturer == "PyMedPhysModified"

    # Check the other file was written to the orphan directory
    orphan_files = list(storage_path.joinpath("orphan").glob("*"))
    assert len(orphan_files) == 1
    orphan_dataset = pydicom.read_file(orphan_files[0])
    assert orphan_dataset.Manufacturer == "PyMedPhys"

    # Clean up after ourselves
    shutil.rmtree(storage_path)


@pytest.mark.pydicom
def test_dicom_listener_cli(test_dataset):
    """Test the command line interface to the DicomListener
    """

    scp_ae_title = "PYMEDPHYSTEST"

    with tempfile.TemporaryDirectory() as tmp_directory:

        test_directory = pathlib.Path(tmp_directory)

        with process(
            f"pymedphys dicom listen {TEST_PORT} -d {test_directory} -a {scp_ae_title}",
            shell=True,
        ) as _:

            # Send the data to the listener
            ae = AE()
            ae.add_requested_context(RTPlanStorage)
            assoc = ae.associate("127.0.0.1", TEST_PORT, ae_title=scp_ae_title)

            # Give the process a few seconds to start up
            elapsed = 0
            while not assoc.is_established:
                time.sleep(0.5)
                elapsed += 0.5
                if elapsed >= 3:  # Break if still not connecting after 3 seconds
                    break

                assoc = ae.associate("127.0.0.1", TEST_PORT, ae_title=scp_ae_title)
            assert assoc.is_established
            status = assoc.send_c_store(test_dataset)
            assert status.Status == 0
            assoc.release()

        series_dir = test_directory.joinpath(test_dataset.SeriesInstanceUID)
        file_path = series_dir.joinpath(f"RP.{test_dataset.SOPInstanceUID}.dcm")
        read_dataset = pydicom.read_file(file_path)
        assert read_dataset.SeriesInstanceUID == test_dataset.SeriesInstanceUID
