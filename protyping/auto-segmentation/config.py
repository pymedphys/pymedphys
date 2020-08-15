import sys

# ------------------------------------------------------------
ROOT_UID = "1.2.826.0.1.3680043.8.498."  # Pydicom root uid

# ------------------------------------------------------------
SCP_IP = "127.0.0.1"  # localhost
SCP_PORT = 34567
SCP_AE_TITLE = "vacunet"
FORWARD_IMAGES = True

SCU_IP = "127.0.0.1"  # localhost
SCU_PORT = 34104
SCU_AE_TITLE = "CMS_SCU"

# ------------------------------------------------------------
# DEVICE = "GPU"
DEVICE = "CPU"

# ------------------------------------------------------------
TRAINING_DATA_MEAN = 168.3172158554484
TRAINING_DATA_STD = 340.21625683608994
MODEL_OUTPUT_CHANNELS = 1
BATCH_SIZE = 1

# ------------------------------------------------------------
if sys.platform == "win32" or sys.platform == "cygwin":
    # Windows
    SCP_STORAGE_PATH = "C:/Users/Public/Documents/vacunet/scp_output"
    MODEL_WEIGHTS = (
        "C:/Users/Public/Documents/vacunet/unet_vacbag_512_dsc_epoch_120.hdf5"
    )
    # TEST_DATASET = (
    #     "C:/Users/Public/Documents/vacunet/test_data/160563_images/with_transfer_syntax"
    # )
else:
    # Linux
    SCP_STORAGE_PATH = "/home/matthew/storage_request"
    MODEL_WEIGHTS = "/media/matthew/secondary/unet_vacbag_512_dsc_epoch_120.hdf5"
    # TEST_DATASET = "/media/matthew/secondary/dicom_prostate_images"
