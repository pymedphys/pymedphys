# Copyright 2020 University of New South Wales, Ingham Institute

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


class DicomConnectBase:
    """Base class for Dicom connect module
    """

    def __init__(self, host="127.0.0.1", port=8888, ae_title="PYMEDPHYSCONNECT"):
        """Create instance of the DicomConnect class

        Args:
            host (str, optional): The host to connect to. Defaults to "127.0.0.1".
            port (int, optional): The port to connect to/listen on. Defaults to 0.
            ae_title (str, optional): The AETitle of the calling/called application.
                                      Defaults to "PYMEDPHYSCONNECT".
        """

        self.host = host
        self.port = port
        self.ae_title = ae_title

        logging.debug(
            "DicomConnect host: %s, port: %d, AE Title: %s",
            self.host,
            self.port,
            self.ae_title,
        )
