import os

from pydicom.uid import UID, generate_uid
from pynetdicom import (
    AE,
    ALL_TRANSFER_SYNTAXES,
    AllStoragePresentationContexts,
    debug_logger,
    evt,
)

import os_helpers
import vacunet
import config

debug_logger()

# TODO Get clinic specific prefix
ROOT_UID = "1.2.826.0.1.3680043.8.498."  # Pydicom root uid

# uid =UID(ORG_ROOT + "." + org_suffix)
# assert uid.is_little_endian
# assert uid.is_implicit_VR


def handle_store(event):
    """Handle EVT_C_STORE events."""
    global study_path

    ds = event.dataset
    ds.file_meta = event.file_meta

    # Parent folder to all storage requests
    storage_dir = os.getcwd() + "/storage_requests/"
    # For the entire study
    study_path = storage_dir + ds.StudyInstanceUID

    os_helpers.make_directory(storage_dir)
    os_helpers.make_directory(study_path)

    # For an imaging instance
    save_path = study_path + "/" + ds.SOPInstanceUID + ".dcm"
    ds.save_as(save_path, write_like_original=False)

    return 0x0000


def handle_release(event):
    """Handle EVT_C_STORE events."""
    vacunet.vacunet(study_path, ROOT_UID)
    print("RELEASED")

    return 0x0000


handlers = [(evt.EVT_C_STORE, handle_store), (evt.EVT_RELEASED, handle_release)]

ae = AE()
storage_sop_classes = [cx.abstract_syntax for cx in AllStoragePresentationContexts]

for uid in storage_sop_classes:
    ae.add_supported_context(uid, ALL_TRANSFER_SYNTAXES)

ae.start_server((config.HOST, config.PORT), block=True, evt_handlers=handlers)
