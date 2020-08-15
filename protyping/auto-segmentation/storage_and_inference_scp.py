# import threading
import time
from collections import deque

import matplotlib

# Need to use thread safe alternative
matplotlib.use("Agg")

import threading

import config
import os_helpers
import vacunet
from pynetdicom import AE, ALL_TRANSFER_SYNTAXES, AllStoragePresentationContexts, evt

lock = threading.Lock()


def handle_accepted(event):
    with lock:
        dicom_store[event.assoc] = []


def handle_store(event):
    """Handle EVT_C_STORE events."""

    ds = event.dataset
    ds.file_meta = event.file_meta

    # Path for the study
    study_path = config.SCP_STORAGE_PATH + "/" + ds.StudyInstanceUID
    os_helpers.make_directory(study_path)

    # Add study path to storage dictionary
    with lock:
        dicom_store[event.assoc].append(study_path)

    # Path for an imaging instance
    save_path = study_path + "/" + ds.SOPInstanceUID + ".dcm"
    ds.save_as(save_path, write_like_original=False)

    return 0x0000


def handle_release(event):
    """Handle EVT_RELEASE ."""
    with lock:
        # Sanity check
        assert len(set(dicom_store[event.assoc])) == 1

        # Add study path to queue for inference
        inference_queue.append(dicom_store[event.assoc][0])

        # Prevent memory leakage
        dicom_store.pop(event.assoc)

    # Show updated queue
    print_inference_queue()

    return 0x0000


def inference_loop():
    while True:
        time.sleep(1)

        if inference_queue:
            vacunet.vacunet(inference_queue[0], config.ROOT_UID)

            print("\n--------------------------")
            print("INFERENCE COMPLETED:")
            print(inference_queue[0])

            inference_queue.popleft()
            print_inference_queue()
            if not inference_queue:
                print_listening()


def print_inference_queue():
    print("\n--------------------------")
    print("INFERENCE QUEUE:", len(inference_queue))
    print("Unique elements:", len(set(inference_queue)))
    for index, path in enumerate(inference_queue):
        print("Position", index, "-", path)


def print_listening():
    print("\n==========================")
    print("Listening for association request on port:", config.SCP_PORT)


def main():

    global inference_queue
    inference_queue = deque()

    global dicom_store
    dicom_store = {}

    # Parent folder to all storage requests
    os_helpers.make_directory(config.SCP_STORAGE_PATH)

    ae = AE()
    ae.network_timeout = None
    ae.acse_timeout = None
    ae.dimse_timeout = None
    ae.maximum_pdu_size = 0
    ae.maximum_associations = 14  # Tested with 14 threads

    handlers = [
        (evt.EVT_ACCEPTED, handle_accepted),
        (evt.EVT_C_STORE, handle_store),
        (evt.EVT_RELEASED, handle_release),
    ]

    storage_sop_classes = [cx.abstract_syntax for cx in AllStoragePresentationContexts]

    for uid in storage_sop_classes:
        ae.add_supported_context(uid, ALL_TRANSFER_SYNTAXES)

    ae.start_server(
        (config.SCP_IP, config.SCP_PORT), block=False, evt_handlers=handlers
    )

    print_listening()

    inference_loop()


if __name__ == "__main__":
    main()
