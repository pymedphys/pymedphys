# Copyright (C) 2020 Matthew Cooper

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import glob

import config
import dicom_helpers
from pynetdicom import AE, debug_logger
from pynetdicom.sop_class import CTImageStorage, RTStructureSetStorage


def export_files(dicom_paths, directory=False):
    print("\n--------------------------")
    print("Structure storage SCU:")
    if directory:
        dicom_paths = glob.glob(dicom_paths + "/*.dcm")
        print("dicom_paths", len(dicom_paths))

    dicom_files = dicom_helpers.read_dicom_paths(dicom_paths)
    print("dicom_files", len(dicom_files))

    # Initialise the Application Entity
    ae = AE()

    # Add a requested presentation context
    ae.add_requested_context(CTImageStorage)
    ae.add_requested_context(RTStructureSetStorage)

    # Associate with peer AE
    assoc = ae.associate(config.SCU_IP, config.SCU_PORT, ae_title=config.SCU_AE_TITLE)
    if assoc.is_established:
        # Use the C-STORE service to send the dataset
        # returns the response status as a pydicom Dataset
        for ds in dicom_files:
            status = assoc.send_c_store(ds)

            # Check the status of the storage request
            if status:
                # If the storage request succeeded this will be 0x0000
                print("C-STORE request status: 0x{0:04x}".format(status.Status))
            else:
                print("Connection timed out, was aborted or received invalid response")

        # Release the association
        assoc.release()
    else:
        print("Structure storage SCU association rejected, aborted or never connected")
