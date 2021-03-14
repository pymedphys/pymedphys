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

import logging
import pathlib

from pymedphys._imports import pydicom, pynetdicom

from pymedphys._dicom.connect.base import DicomConnectBase


class DicomSender(DicomConnectBase):
    """Class which provides SCU functionality to send DICOM objects"""

    def verify(self):
        """Verify that we can connect to the DICOM endpoint using C_ECHO

        Returns
        -------
        bool
            True if the C_ECHO was successful, False otherwise.
        """

        ae = pynetdicom.AE(ae_title=self.ae_title)
        ae.requested_contexts = pynetdicom.VerificationPresentationContexts

        # Associate with a peer DICOM AE
        assoc = ae.associate(self.host, self.port, ae_title=self.ae_title)

        result = None

        if assoc.is_established:
            status = assoc.send_c_echo()

            if status:
                result = status.Status

            # Release the association
            assoc.release()

        return not result is None

    def send(self, dcm_files):
        """Send each DICOM object to the configured DICOM location

        Parameters
        ----------
        dcm_files : list
            list of str, pathlib.Path or pydicom.Dataset to send

        Returns
        -------
        list
            List containing status objects for each DICOM file sent

        Raises
        ------
        TypeError
            Raised if any of the dcm_files are not of type str, pathlib.Path or
            pydicom.Dataset
        """
        transfer_syntax = [pydicom.uid.ImplicitVRLittleEndian]

        ae = pynetdicom.AE()

        for context in pynetdicom.StoragePresentationContexts:
            ae.add_requested_context(context.abstract_syntax, transfer_syntax)

        assoc = ae.associate(self.host, self.port, ae_title=self.ae_title)

        statuses = []
        if assoc.is_established:

            for dataset in dcm_files:

                if not isinstance(dataset, (pydicom.Dataset, pathlib.Path, str)):
                    raise TypeError(
                        "dcm_files must be  str, pathlib.Path or pydicom.Dataset"
                    )

                if not isinstance(dataset, pydicom.Dataset):
                    dataset = pydicom.read_file(dataset)

                logging.debug(
                    "Sending DICOM object with SOPInstanceUID: %s",
                    dataset.SOPInstanceUID,
                )

                statuses.append(assoc.send_c_store(dataset))

            assoc.release()

        return statuses


def send_cli(args):
    """Send files from the command line to the DICOM location"""

    # Start the listener
    dicom_sender = DicomSender(host=args.host, port=args.port, ae_title=args.aetitle)

    # Check we can contact the listener
    if not dicom_sender.verify():
        logging.error("Unable to connect to DICOM host")
        return

    # Prepare the DICOM file (check that all files are valid DICOM)
    dcm_file_paths = []
    for dcm_file in args.dcmfiles:
        dcm_file_path = pathlib.Path(dcm_file)
        try:
            pydicom.read_file(dcm_file_path)
        except pydicom.errors.InvalidDicomError:
            logging.error("Invalid DICOM file provided: %s", dcm_file)
            return

        dcm_file_paths.append(dcm_file_path)

    # Send the files
    dicom_sender.send(dcm_file_paths)
