import threading
import time
import random
import images_storage_scu


def fuzz():
    time.sleep(random.random())


DATA_PATH_1 = (
    "/media/matthew/secondary/prostate_dataset_raw/000638/with_transfer_syntax"
)
DATA_PATH_2 = (
    "/media/matthew/secondary/prostate_dataset_raw/002487/with_transfer_syntax"
)
DATA_PATH_3 = (
    "/media/matthew/secondary/prostate_dataset_raw/003887/with_transfer_syntax"
)
DATA_PATH_4 = (
    "/media/matthew/secondary/prostate_dataset_raw/011821/with_transfer_syntax"
)
DATA_PATH_5 = (
    "/media/matthew/secondary/prostate_dataset_raw/012125/with_transfer_syntax"
)
DATA_PATH_6 = (
    "/media/matthew/secondary/prostate_dataset_raw/012600/with_transfer_syntax"
)
DATA_PATH_7 = (
    "/media/matthew/secondary/prostate_dataset_raw/013030/with_transfer_syntax"
)
DATA_PATH_8 = (
    "/media/matthew/secondary/prostate_dataset_raw/013604/with_transfer_syntax"
)
DATA_PATH_9 = (
    "/media/matthew/secondary/prostate_dataset_raw/013780/with_transfer_syntax"
)
DATA_PATH_10 = (
    "/media/matthew/secondary/prostate_dataset_raw/013872/with_transfer_syntax"
)
DATA_PATH_11 = (
    "/media/matthew/secondary/prostate_dataset_raw/013875/with_transfer_syntax"
)
DATA_PATH_12 = (
    "/media/matthew/secondary/prostate_dataset_raw/014072/with_transfer_syntax"
)
DATA_PATH_13 = (
    "/media/matthew/secondary/prostate_dataset_raw/014199/with_transfer_syntax"
)
DATA_PATH_14 = (
    "/media/matthew/secondary/prostate_dataset_raw/014362/with_transfer_syntax"
)

threading.Thread(target=images_storage_scu.main, args=(DATA_PATH_1,)).start()
fuzz()
threading.Thread(target=images_storage_scu.main, args=(DATA_PATH_2,)).start()
fuzz()
threading.Thread(target=images_storage_scu.main, args=(DATA_PATH_3,)).start()
fuzz()
threading.Thread(target=images_storage_scu.main, args=(DATA_PATH_4,)).start()
fuzz()
threading.Thread(target=images_storage_scu.main, args=(DATA_PATH_5,)).start()
fuzz()
threading.Thread(target=images_storage_scu.main, args=(DATA_PATH_6,)).start()
fuzz()
threading.Thread(target=images_storage_scu.main, args=(DATA_PATH_7,)).start()
fuzz()
threading.Thread(target=images_storage_scu.main, args=(DATA_PATH_8,)).start()
fuzz()
threading.Thread(target=images_storage_scu.main, args=(DATA_PATH_9,)).start()
fuzz()
threading.Thread(target=images_storage_scu.main, args=(DATA_PATH_10,)).start()
fuzz()
threading.Thread(target=images_storage_scu.main, args=(DATA_PATH_11,)).start()
fuzz()
threading.Thread(target=images_storage_scu.main, args=(DATA_PATH_12,)).start()
fuzz()
threading.Thread(target=images_storage_scu.main, args=(DATA_PATH_13,)).start()
fuzz()
threading.Thread(target=images_storage_scu.main, args=(DATA_PATH_14,)).start()
