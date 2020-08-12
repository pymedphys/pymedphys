import config
import dicom_helpers
import os_helpers
import structure_storage_scu
import vacunet
from pynetdicom import (
    AE,
    ALL_TRANSFER_SYNTAXES,
    AllStoragePresentationContexts,
    debug_logger,
    evt,
)

debug_logger()


def handle_store(event):
    """Handle EVT_C_STORE events."""
    global study_path

    ds = event.dataset
    ds.file_meta = event.file_meta

    # Parent folder to all storage requests
    export_path = config.SCP_STORAGE_PATH
    # For the entire study
    study_path = export_path + "/" + ds.StudyInstanceUID

    os_helpers.make_directory(export_path)
    os_helpers.make_directory(study_path)

    # For an imaging instance
    save_path = study_path + "/" + ds.SOPInstanceUID + ".dcm"
    ds.save_as(save_path, write_like_original=False)

    return 0x0000


def handle_release(event):
    """Handle EVT_C_STORE events."""
    # Return RT structure file
    dicom_structure_file = vacunet.vacunet(study_path, config.ROOT_UID)

    # For RT structure file instance
    save_path = study_path + "/" + dicom_structure_file.SOPInstanceUID + ".dcm"
    dicom_structure_file.save_as(save_path, write_like_original=False)

    # Print file contents
    dicom_helpers.print_dicom_file(dicom_structure_file)
    print("\nSTORED:", save_path)

    try:
        # SEND TO STORAGE_STRUCTURES_SCU
        structure_storage_scu.export_files([save_path], directory=False)
        # structure_storage_scu.export_files(study_path, directory=True)
        print("Storage association request failed")
    except:
        print("Storage association request failed")

    print("RELEASED")
    print("\nListening for association request on port:", config.SCP_PORT)

    return 0x0000


handlers = [(evt.EVT_C_STORE, handle_store), (evt.EVT_RELEASED, handle_release)]

ae = AE()
ae.network_timeout = None
ae.acse_timeout = None
ae.dimse_timeout = None
ae.maximum_pdu_size = 0
ae.maximum_associations = 1  # TODO Handle more than one

storage_sop_classes = [cx.abstract_syntax for cx in AllStoragePresentationContexts]

for uid in storage_sop_classes:
    ae.add_supported_context(uid, ALL_TRANSFER_SYNTAXES)

print("\nListening for association request on port:", config.SCP_PORT)

ae.start_server((config.SCP_IP, config.SCP_PORT), block=True, evt_handlers=handlers)

# ae.start_server(("", config.SCP_PORT),
#                 block=True,
#                 evt_handlers=handlers)
