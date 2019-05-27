import os
from typing import Dict
from glob import glob

import numpy as np
import matplotlib.pyplot as plt

import pydicom

from pymedphys import DeliveryData
from pymedphys.mudensity import get_grid, display_mu_density

input_directory = 'input'
output_directory = 'output'
grid_resolution = 5

trf_filepaths = glob(os.path.join(input_directory, '*.trf'))
dicom_filepaths = glob(os.path.join(input_directory, '*.dcm'))

filepath_mu_density_map: Dict[str, np.ndarray] = {}
filepath_mu_density_diff_map: Dict[str, np.ndarray] = {}

for trf_filepath in trf_filepaths:
    trf_delivery = DeliveryData.from_logfile(trf_filepath)
    trf_mudensity = trf_delivery.mudensity(grid_resolution=grid_resolution)

    filepath_mu_density_map[
        '{}.mudensity.png'.format(trf_filepath)] = trf_mudensity

    for dicom_filepath in dicom_filepaths:
        try:
            dicom_deliveries = DeliveryData.load_all_fractions_from_file(
                dicom_filepath)
        except AttributeError:
            print(
                "{} does not appear to be an RT DICOM plan, "
                "skipping...".format(dicom_filepath))
            continue

        for dicom_delivery in dicom_deliveries:
            dicom_mudensity = dicom_delivery.mudensity(
                grid_resolution=grid_resolution)

            filepath_mu_density_map[
                '{}.mudensity.png'.format(dicom_filepath)] = dicom_mudensity

            filepath_mu_density_diff_map[
                '{}-{}.mudensity_diff.png'.format(trf_filepath, dicom_filepath)
            ] = trf_mudensity - dicom_mudensity


maximum_mudensity = np.max([
    mudensity
    for _, mudensity in filepath_mu_density_map.items()
])

grid = get_grid(grid_resolution=grid_resolution)

for filepath, mudensity in filepath_mu_density_map.items():
    plt.figure()
    display_mu_density(grid, mudensity, vmin=0, vmax=maximum_mudensity)
    plt.savefig(filepath)

maximum_diff = np.max(np.abs([
    mudensity_diff
    for _, mudensity_diff in filepath_mu_density_diff_map.items()
]))

for filepath, mudensity_diff in filepath_mu_density_diff_map.items():
    plt.figure()
    display_mu_density(
        grid, mudensity, vmin=-maximum_diff, vmax=maximum_diff, cmap='seismic')
    plt.savefig(filepath)
