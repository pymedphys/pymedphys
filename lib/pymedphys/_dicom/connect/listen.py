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

import logging
import signal
import sys
import tempfile
from pathlib import Path

from pymedphys._imports import pydicom, pynetdicom
from pymedphys._dicom.connect.base import DicomConnectBase


class DicomListener(DicomConnectBase):
    def __init__(
        self, storage_directory=tempfile.mkdtemp(), on_released_callback=None, **kwargs
    ):
        super().__init__(**kwargs)

        # The directory where incoming data will be stored
        self.storage_directory = storage_directory
        if not isinstance(self.storage_directory, Path):
            self.storage_directory = Path(self.storage_directory)

        # Callback when association is released called with path to the directory where
        # data from that association was stored
        self.on_released_callback = on_released_callback

        # Keep track of the directory where data for the current association is stored
        self.association_directory = None

        # The application entity
        self.ae = None

    def start(self):

        # Initialise the Application Entity
        self.ae = pynetdicom.AE(ae_title=self.ae_title)

        # Add the supported presentation context
        self.ae.add_supported_context(
            pynetdicom.sop_class.VerificationSOPClass  # pylint: disable = no-member
        )
        for context in pynetdicom.StoragePresentationContexts:
            self.ae.add_supported_context(context.abstract_syntax)

        handlers = [
            (pynetdicom.evt.EVT_C_MOVE, self.on_c_store),
            (pynetdicom.evt.EVT_C_STORE, self.on_c_store),
            (pynetdicom.evt.EVT_C_ECHO, self.on_c_echo),
            (pynetdicom.evt.EVT_ACCEPTED, self.on_association_accepted),
            (pynetdicom.evt.EVT_RELEASED, self.on_association_released),
        ]

        # Start listening for incoming association requests
        self.ae.start_server((self.host, self.port), evt_handlers=handlers, block=False)

    def stop(self):

        if self.ae:
            self.ae.shutdown()

    def on_c_echo(self, _):  # pylint: disable = no-self-use
        """Respond to a C-ECHO service request.
        """
        logging.debug("C-ECHO!")
        return 0x0000

    def on_association_accepted(self, _):
        self.association_directory = None

    def on_association_released(self, _):

        if self.on_released_callback:
            self.on_released_callback(self.association_directory)

    def on_c_store(self, event):

        dataset = event.dataset

        # TODO: Should these be place in a config file?
        mode_prefixes = {
            "CT Image Storage": "CT",
            "Enhanced CT Image Storage": "CTE",
            "MR Image Storage": "MR",
            "Enhanced MR Image Storage": "MRE",
            "Positron Emission Tomography Image Storage": "PT",
            "Enhanced PET Image Storage": "PTE",
            "RT Image Storage": "RI",
            "RT Dose Storage": "RD",
            "RT Plan Storage": "RP",
            "RT Structure Set Storage": "RS",
            "Computed Radiography Image Storage": "CR",
            "Ultrasound Image Storage": "US",
            "Enhanced Ultrasound Image Storage": "USE",
            "X-Ray Angiographic Image Storage": "XA",
            "Enhanced XA Image Storage": "XAE",
            "Nuclear Medicine Image Storage": "NM",
            "Secondary Capture Image Storage": "SC",
        }

        try:
            mode_prefix = mode_prefixes[dataset.SOPClassUID.name]
        except KeyError:
            mode_prefix = "UN"

        suid = dataset.SeriesInstanceUID
        series_dir = self.storage_directory / suid
        series_dir.mkdir(exist_ok=True)

        filename = "{0!s}.{1!s}".format(mode_prefix, dataset.SOPInstanceUID)
        filepath = series_dir / filename

        if filepath.exists:
            # TODO Currently just logging this, since I'm unsure of the desired
            # behaviour if the file has already been received.
            logging.debug("DICOM file already exists, overwriting")

        context = event.context
        meta = pydicom.Dataset()
        meta.MediaStorageSOPClassUID = dataset.SOPClassUID
        meta.MediaStorageSOPInstanceUID = dataset.SOPInstanceUID
        meta.ImplementationClassUID = pynetdicom.PYNETDICOM_IMPLEMENTATION_UID
        meta.TransferSyntaxUID = context.transfer_syntax

        # The following is not mandatory, set for convenience
        meta.ImplementationVersionName = pynetdicom.PYNETDICOM_IMPLEMENTATION_VERSION
        file_ds = pydicom.FileDataset(
            filepath.as_posix(), {}, file_meta=meta, preamble=b"\0" * 128
        )
        file_ds.update(dataset)
        file_ds.is_little_endian = context.transfer_syntax.is_little_endian
        file_ds.is_implicit_VR = context.transfer_syntax.is_implicit_VR

        status_ds = pydicom.Dataset()
        status_ds.Status = 0x0000

        try:
            # We use `write_like_original=False` to ensure that a compliant
            #   File Meta Information Header is written
            file_ds.save_as(filepath.as_posix(), write_like_original=False)
            status_ds.Status = 0x0000  # Success
        except IOError:
            logging.warning("Could not write file to specified directory:")
            logging.warning("    %s", filepath)
            logging.warning(
                "Directory may not exist or you may not have write " "permission"
            )
            # Failed - Out of Resources - IOError
            status_ds.Status = 0xA700
        except Exception as exception:  # pylint: disable = broad-except
            logging.warning("An error occurred saving the Dicom file:")
            logging.warning("    %s", filepath)
            logging.warning(exception)
            # Failed - Out of Resources - Miscellaneous error
            status_ds.Status = 0xA701

        self.association_directory = series_dir

        return status_ds


def listen_cli(args):
    """Starts a Dicom listener from the command line interface
    """

    # Set log level to debug
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # Start the listener
    dicom_listener = DicomListener(
        port=args.port, ae_title=args.aetitle, storage_directory=args.storage_directory
    )
    dicom_listener.start()

    # Run until the process is stopped
    def handler_stop_signals(*_):
        logging.info("Shutting down listener")
        dicom_listener.stop()
        sys.exit()

    signal.signal(signal.SIGINT, handler_stop_signals)
    signal.signal(signal.SIGTERM, handler_stop_signals)

    while True:
        pass
