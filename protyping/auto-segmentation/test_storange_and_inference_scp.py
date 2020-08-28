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


import random
import threading
import time

import images_storage_scu


def fuzz():
    time.sleep(random.random())


root_path = "/media/matthew/secondary/prostate_dataset_raw/"

series_paths = [
    "000638/with_transfer_syntax",
    "002487/with_transfer_syntax",
    "003887/with_transfer_syntax",
    "011821/with_transfer_syntax",
    "012125/with_transfer_syntax",
    "012600/with_transfer_syntax",
    "013030/with_transfer_syntax",
    "013604/with_transfer_syntax",
    "013780/with_transfer_syntax",
    "013872/with_transfer_syntax",
    "013875/with_transfer_syntax",
    "014072/with_transfer_syntax",
    "014199/with_transfer_syntax",
    "014362/with_transfer_syntax",
]

for series_path in series_paths:
    threading.Thread(
        target=images_storage_scu.main, args=(root_path + series_path,)
    ).start()
    fuzz()
