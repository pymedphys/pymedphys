import os
from glob import glob

import numpy as np
import matplotlib.pyplot as plt

from pymedphys.gamma import gamma_dicom


input_dir = 'input'
output_dir = 'output'

reference_tag = "original"
evaluation_tag = "logfile"

gamma_options = {
    'dose_percent_threshold': 2,
    'distance_mm_threshold': 2,
    'lower_percent_dose_cutoff': 20,
    'interp_fraction': 10,  # Should be about 10 for more accurate results
    'max_gamma': 2,
    'random_subset': None,
    'local_gamma': True,
    'ram_available': 2**29  # 1/2 GB
}

first_reference_dicom_file = glob(os.path.join(
    input_dir, '{}*.dcm'.format(reference_tag)))[0]
first_evaluation_dicom_file = glob(os.path.join(
    input_dir, '{}*.dcm'.format(evaluation_tag)))[0]


gamma = gamma_dicom(
    first_reference_dicom_file, first_evaluation_dicom_file, **gamma_options)

valid_gamma = gamma[~np.isnan(gamma)]

plt.figure()
num_bins = (
    gamma_options['interp_fraction'] * gamma_options['max_gamma'])  # type: ignore
bins = np.linspace(0, gamma_options['max_gamma'], num_bins + 1)

plt.hist(valid_gamma, bins, density=True)
plt.xlim([0, gamma_options['max_gamma']])

pass_ratio = np.sum(valid_gamma <= 1) / len(valid_gamma)

plt.title("Gamma Percent Pass: {0:.2f} %".format(pass_ratio*100))

plt.show()
