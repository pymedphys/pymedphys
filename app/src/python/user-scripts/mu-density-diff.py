import os
from typing import Dict
from glob import glob

import numpy as np
import matplotlib.pyplot as plt

import pydicom

from pymedphys import DeliveryData
from pymedphys.mudensity import get_grid, display_mu_density
from pymedphys.dicom import get_gantry_angles_from_dicom


input_directory = 'input'
output_directory = 'output'
grid_resolution = 5
gantry_angle_tolerance = 3

trf_filepaths = glob(os.path.join(input_directory, '*.trf'))
dicom_filepaths = glob(os.path.join(input_directory, '*.dcm'))

filepath_mu_density_map: Dict[str, np.ndarray] = {}
filepath_mu_density_diff_map: Dict[str, np.ndarray] = {}

for trf_filepath in trf_filepaths:
    trf_delivery = DeliveryData.from_logfile(trf_filepath).filter_cps()
    trf_filename = os.path.basename(trf_filepath)

    for dicom_filepath in dicom_filepaths:
        try:
            dicom_deliveries = DeliveryData.load_all_fractions_from_file(
                dicom_filepath)
        except AttributeError:
            print(
                "{} does not appear to be an RT DICOM plan, "
                "skipping...".format(dicom_filepath))
            continue

        for fraction_number, dicom_delivery_raw in dicom_deliveries.items():
            dicom_delivery = dicom_delivery_raw.filter_cps()

            gantry_angles = tuple(
                np.unique(dicom_delivery.gantry).tolist())

            all_within_tol = True
            for gantry_angle in set(trf_delivery.gantry):
                smallest_diff = np.min(np.abs(gantry_angles - gantry_angle))

                if not smallest_diff < gantry_angle_tolerance:
                    all_within_tol = False
                    break

            if not all_within_tol:
                print(
                    "The gantry angles within {} do not does not agree with "
                    "the gantry angles within a tolerance of {} "
                    "for fraction number {} within {}. "
                    "Skipping this fraction..."
                    "".format(
                        trf_filepath, gantry_angle_tolerance, fraction_number,
                        dicom_filepath))
                continue

            dicom_filename = os.path.basename(dicom_filepath)

            trf_mudensity = trf_delivery.mudensity(
                gantry_angles=gantry_angles,
                gantry_tolerance=gantry_angle_tolerance,
                grid_resolution=5, output_always_list=True)

            dicom_mudensity = dicom_delivery.mudensity(
                gantry_angles=gantry_angles,
                gantry_tolerance=gantry_angle_tolerance,
                grid_resolution=5, output_always_list=True)

            for i, gantry_angle in enumerate(gantry_angles):
                prepend_string = '{}/Fraction_{}_Gantry_{}_'.format(
                    output_directory, fraction_number, gantry_angle)

                trf = trf_mudensity[i]
                dicom = dicom_mudensity[i]
                diff = trf - dicom

                trf_out_filepath = '{}{}.mudensity.png'.format(
                    prepend_string, trf_filename)
                filepath_mu_density_map[trf_out_filepath] = trf

                dicom_out_filepath = '{}{}.mudensity.png'.format(
                    prepend_string, dicom_filename)
                filepath_mu_density_map[dicom_out_filepath] = dicom

                diff_filepath = '{}[{}]-[{}].mudensity_diff.png'.format(
                    prepend_string, trf_filename, dicom_filename)
                filepath_mu_density_diff_map[diff_filepath] = diff


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
