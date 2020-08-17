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
import sys

if sys.platform == "win32" or sys.platform == "cygwin":
    # Windows
    SCP_STORAGE_PATH = "C:/Users/Public/Documents/vacunet/scp_output"
    MODEL_WEIGHTS = (
        "C:/Users/Public/Documents/vacunet/unet_vacbag_512_dsc_epoch_120.hdf5"
    )
else:
    # Linux
    SCP_STORAGE_PATH = "/home/matthew/storage_request"
    MODEL_WEIGHTS = "/media/matthew/secondary/unet_vacbag_512_dsc_epoch_120.hdf5"
