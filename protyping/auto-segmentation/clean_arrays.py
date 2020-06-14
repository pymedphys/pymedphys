import glob
import os
import sys

import numpy as np

from matplotlib import pyplot as plt

import paths as paths

PATH = "./prostate_dataset_cleaned/"
SAVE_DIR = "./prostate_dataset_figures/"

patient_paths = paths.get_patient_paths(PATH)
patient_paths.sort()

img_paths = [glob.glob(path + "/img/*") for path in patient_paths]
mask_paths = [glob.glob(path + "/mask/*") for path in patient_paths]

img_paths = paths.flatten_list(img_paths)
mask_paths = paths.flatten_list(mask_paths)

img_paths.sort()
mask_paths.sort()

deleted = []

i = 0
for img_path, mask_path in zip(img_paths, mask_paths):
    try:
        print(img_path)
        img = np.load(img_path)
        mask = np.load(mask_path)
        print("img:", img.shape)
        print("mask:", mask.shape)

        fig, axs = plt.subplots(nrows=1, ncols=4)
        axs[0].imshow(img[..., 0])
        axs[1].imshow(mask[..., 0])
        axs[2].imshow(mask[..., 1])
        axs[3].imshow(mask[..., 2])

        title = f"{img_path}.png"
        fig.suptitle(title)
        plt.savefig(SAVE_DIR + str(i))
        i = i + 1
        plt.close()
    except:
        print("DELETING!!")
        os.remove(img_path)
        os.remove(mask_path)
        deleted.append(img_path)

print("DELETED")
for i in deleted:
    print(i)
