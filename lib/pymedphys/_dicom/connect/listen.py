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
import signal
import sys
import tempfile
import uuid

from pymedphys._imports import pydicom, pynetdicom

from pymedphys._dicom.connect.base import DicomConnectBase
from pymedphys._dicom.constants.core import DICOM_SOP_CLASS_NAMES_MODE_PREFIXES


def hierarchical_dicom_storage_directory(
    storage_directory, ds: "pydicom.dataset.Dataset"
) -> pathlib.Path:
    series_path = pathlib.Path(storage_directory).joinpath(
        ds.PatientID, ds.StudyInstanceUID, ds.SeriesInstanceUID
    )
    return series_path


class DicomListener(DicomConnectBase):
    """Class which provides SCP functionality to listen for incoming DICOM objects"""

    def __init__(self, storage_directory=None, on_released_callback=None, **kwargs):
        """Create and instance of a DICOM Listener

        Parameters
        ----------
        storage_directory : pathlib.Path or str, optional
            The directory in which to store incoming DICOM objects, by default a
            temporary directory will be created
        on_released_callback : function, optional
            Called when an association is released, the directory in which the incoming
            data was stored is returned, by default None
        """
        super().__init__(**kwargs)

        # If no storage directory is set, create a temporary directory
        if storage_directory is None:
            storage_directory = tempfile.mkdtemp()

        # The directory where incoming data will be stored
        self.storage_directory = pathlib.Path(storage_directory)

        # Callback when association is released called with path to the directory where
        # data from that association was stored
        self.on_released_callback = on_released_callback

        # Keep track of the directory where data for the current association is stored
        self.association_directory = None

        # The application entity
        self.ae = None

        logging.debug("Will store files received in: %s", self.storage_directory)

    def start(self):
        """Start the DICOM listener"""

        # Initialise the Application Entity
        self.ae = pynetdicom.AE(ae_title=self.ae_title)

        # Add the supported presentation context
        self.ae.add_supported_context(
            pynetdicom.sop_class.VerificationSOPClass  # pylint: disable = no-member
        )
        for context in pynetdicom.StoragePresentationContexts:
            self.ae.add_supported_context(context.abstract_syntax)

        handlers = [
            (pynetdicom.evt.EVT_C_STORE, self.on_c_store),
            (pynetdicom.evt.EVT_C_ECHO, self.on_c_echo),
            (pynetdicom.evt.EVT_ACCEPTED, self.on_association_accepted),
            (pynetdicom.evt.EVT_RELEASED, self.on_association_released),
        ]

        # Start listening for incoming association requests
        self.ae.start_server((self.host, self.port), evt_handlers=handlers, block=False)

    def stop(self):
        """Stop the DICOM listener"""

        if self.ae:
            self.ae.shutdown()

    def on_c_echo(self, _):  # pylint: disable = no-self-use
        """Respond to a C-ECHO service request."""
        logging.debug("C-ECHO!")
        return 0x0000

    def on_association_accepted(self, _):
        self.association_directory = None

    def on_association_released(self, _):
        if self.on_released_callback:
            self.on_released_callback(self.association_directory)

    def on_c_store(self, event):

        dataset = event.dataset

        try:
            mode_prefix = DICOM_SOP_CLASS_NAMES_MODE_PREFIXES[dataset.SOPClassUID.name]
        except KeyError:
            mode_prefix = "UN"

        series_dir = hierarchical_dicom_storage_directory(
            self.storage_directory, dataset
        )
        series_dir.mkdir(parents=True, exist_ok=True)
        self.association_directory = series_dir

        filename = pathlib.Path(
            "{0!s}.{1!s}.dcm".format(mode_prefix, dataset.SOPInstanceUID)
        )
        filepath = series_dir.joinpath(filename)

        status_ds = pydicom.Dataset()
        status_ds.Status = 0x0000

        if filepath.exists():

            # If the file already exists, open it up and compare the contents
            # (converting to JSON string to perform comparison)
            existing_ds = pydicom.read_file(filepath)

            if not existing_ds.to_json() == dataset.to_json():
                # If the contents don't match, save conflicting incoming file in an
                # "orphan" sub-directory.

                # Just give the file a unique name in the orphan directory
                filename = str(uuid.uuid4())
                filepath = series_dir.joinpath("orphan", filename)
                filepath.parent.mkdir(exist_ok=True)

                logging.warning(
                    "DICOM file exists, storing in orphan directory: %s", filename
                )

        context = event.context
        meta = pydicom.Dataset()
        meta.MediaStorageSOPClassUID = dataset.SOPClassUID
        meta.MediaStorageSOPInstanceUID = dataset.SOPInstanceUID
        meta.ImplementationClassUID = pynetdicom.PYNETDICOM_IMPLEMENTATION_UID
        meta.TransferSyntaxUID = context.transfer_syntax

        # The following is not mandatory, set for convenience
        meta.ImplementationVersionName = pynetdicom.PYNETDICOM_IMPLEMENTATION_VERSION
        file_ds = pydicom.FileDataset(
            filepath, {}, file_meta=meta, preamble=b"\0" * 128
        )
        file_ds.update(dataset)
        file_ds.is_little_endian = context.transfer_syntax.is_little_endian
        file_ds.is_implicit_VR = context.transfer_syntax.is_implicit_VR

        try:
            # We use `write_like_original=False` to ensure that a compliant
            # File Meta Information Header is written
            file_ds.save_as(filepath, write_like_original=False)
            status_ds.Status = 0x0000  # Success

            logging.info("DICOM object received: %s", filepath)
        except IOError:
            logging.error("Could not write file to specified directory:")
            logging.error("    %s", filepath)
            logging.error(
                "Directory may not exist or you may not have write permission"
            )

            status_ds.ErrorComment = "SCP internal error - Unable to write file"
            status_ds.Status = 0xA700  # Failed - Out of Resources - IOError

        return status_ds


def listen_cli(args):
    """Start a DICOM listener from the command line interface"""

    # Start the listener
    dicom_listener = DicomListener(
        host=args.host,
        port=args.port,
        ae_title=args.aetitle,
        storage_directory=args.storage_directory,
    )

    logging.info("Starting DICOM listener")
    logging.info("IP: %s", args.host)
    logging.info("Port: %s", args.port)
    logging.info("AE Title: %s", args.aetitle)
    dicom_listener.start()
    logging.info("Listener Ready")

    # Run until the process is stopped
    def handler_stop_signals(*_):
        logging.info("Shutting down listener")
        dicom_listener.stop()
        sys.exit()

    signal.signal(signal.SIGINT, handler_stop_signals)
    signal.signal(signal.SIGTERM, handler_stop_signals)

    while True:
        pass
