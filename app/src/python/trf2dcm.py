# pylint: disable=import-error

import os
from glob import glob

import numpy as np
import matplotlib.pyplot as plt

import pydicom

from js import window, Promise

from pymedphys_fileformats.trf import (
    trf2pandas, delivery_data_from_pandas)

from pymedphys_core.deliverydata import (
    delivery_data_to_dicom, extract_angle_from_delivery_data,
    dicom_to_delivery_data)
from pymedphys_core.mudensity import (
    calc_mu_density_bygantry, get_grid)


def trf2csv(filepath, output_directory):
    filename = os.path.basename(filepath)
    new_filename = os.path.join(output_directory, filename)

    header_csv_filepath = "{}.header.csv".format(new_filename)
    table_csv_filepath = "{}.table.csv".format(new_filename)

    print("Converting {}".format(filepath))

    header, table = trf2pandas(filepath)
    header.to_csv(header_csv_filepath)
    table.to_csv(table_csv_filepath)

    return header, table


def plot_and_save_mudensity_diff(mu_density_logfile, mu_density_dicom):
    mu_density_diff = mu_density_logfile - mu_density_dicom

    max_diff = np.max(np.abs(mu_density_diff))

    plt.figure(figsize=(6, 5.25))

    grid = get_grid()

    plt.pcolormesh(
        grid['mlc'][-1::-1], grid['jaw'],
        mu_density_diff, vmin=-max_diff, vmax=max_diff, cmap='bwr')
    cbar = plt.colorbar()
    cbar.set_label('MU Density Difference')
    plt.xlabel('MLCX direction (mm)')
    plt.ylabel('ASYMY travel direction (mm)')

    plt.axis('equal')
    plt.title('MU Density Difference (Logfile - Original)')

    plt.savefig('/output/mudensity_diff.png')


def run_trf2dcm():
    def run_promise(resolve, reject):
        try:
            input_dir = '/input'
            output_dir = '/output'
            gantry_angle = window['pythonData'].getValue()['gantryAngle']
            dcm_template_filepath = glob(os.path.join(input_dir, '*.dcm'))[0]

            trf_filepath = glob(os.path.join(input_dir, '*.trf'))[0]
            trf_filename = os.path.basename(trf_filepath)

            _, table = trf2csv(trf_filepath, output_dir)
            print("Decoding to CSV complete")

            logfile_delivery_data = delivery_data_from_pandas(table)
            print(extract_angle_from_delivery_data(
                logfile_delivery_data, gantry_angle, gantry_tolerance=3))

            print("Creating new DICOM file")
            dicom_template = pydicom.read_file(
                dcm_template_filepath, force=True)
            logfile_dicom = delivery_data_to_dicom(
                logfile_delivery_data, dicom_template, gantry_angle)

            logfile_dicom.save_as(os.path.join(
                output_dir, "{}.dcm".format(trf_filename)))
            print("DICOM file creation complete")

            dicom_delivery_data = dicom_to_delivery_data(
                dicom_template, gantry_angle)

            print(extract_angle_from_delivery_data(
                dicom_delivery_data, gantry_angle, gantry_tolerance=3))

            print("Determining MU Density of original DICOM file")
            mu_density_dicom = calc_mu_density_bygantry(
                dicom_delivery_data, gantry_angle, gantry_tolerance=3)

            print("Determining MU Density of logfile")
            mu_density_logfile = calc_mu_density_bygantry(
                logfile_delivery_data, gantry_angle, gantry_tolerance=3)

            print("Plotting MU Density diff")
            plot_and_save_mudensity_diff(
                mu_density_logfile, mu_density_dicom)

            print("Complete")

            resolve()
        except Exception as e:
            reject(e)
            raise

    return Promise.new(run_promise)


run_trf2dcm()
