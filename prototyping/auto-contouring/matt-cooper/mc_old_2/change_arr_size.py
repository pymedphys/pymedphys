import glob
import os
import sys

import numpy as np

from matplotlib import pyplot as plt

import paths as paths

path = "./prostate_dataset_cleaned/"

patient_paths = paths.get_patient_paths(path)
patient_paths.sort()

img_paths = [glob.glob(path + "/img/*") for path in patient_paths]

img_paths = paths.flatten_list(img_paths)

img_paths.sort()

for img_path in img_paths:
    print(img_path)
    img = np.load(img_path)

    if img.shape is not (512, 512, 1):
        img = img[..., np.newaxis]
    np.save(img_path, img)
