import os
from glob import glob

import numpy as np
import matplotlib.pyplot as plt

import pydicom

from pymedphys.gamma import gamma_dicom
from pymedphys.dicom import zyx_and_dose_from_dataset


input_dir = "input"
output_dir = "output"

reference_tag = "original"
evaluation_tag = "logfile"

gamma_options = {
    "dose_percent_threshold": 1,
    "distance_mm_threshold": 1,
    "lower_percent_dose_cutoff": 20,
    "interp_fraction": 10,  # Should be about 10 for more accurate results
    "max_gamma": 2,
    "random_subset": None,
    "local_gamma": False,
    "ram_available": 2 ** 29,  # 1/2 GB
}

threshold_string = "{}%/{}mm".format(
    gamma_options["dose_percent_threshold"], gamma_options["distance_mm_threshold"]
)

first_reference_dicom_file = glob(
    os.path.join(input_dir, "{}*.dcm".format(reference_tag))
)[0]
first_evaluation_dicom_file = glob(
    os.path.join(input_dir, "{}*.dcm".format(evaluation_tag))
)[0]


reference = pydicom.dcmread(first_reference_dicom_file, force=True)
evaluation = pydicom.dcmread(first_evaluation_dicom_file, force=True)

gamma = gamma_dicom(reference, evaluation, **gamma_options)

valid_gamma = gamma[~np.isnan(gamma)]

plt.figure()
num_bins = gamma_options["interp_fraction"] * gamma_options["max_gamma"]  # type: ignore
bins = np.linspace(0, gamma_options["max_gamma"], num_bins + 1)

plt.hist(valid_gamma, bins, density=True)
plt.xlim([0, gamma_options["max_gamma"]])

pass_ratio = np.sum(valid_gamma <= 1) / len(valid_gamma)

plt.title(
    "Gamma ({0}) | Percent Pass: {1:.2f} %".format(threshold_string, pass_ratio * 100)
)

plt.savefig(os.path.join(output_dir, "gamma_histogram.png"))


(z_ref, y_ref, x_ref), dose_reference = zyx_and_dose_from_dataset(reference)
(z_eval, y_eval, x_eval), dose_evaluation = zyx_and_dose_from_dataset(evaluation)


lower_dose_cutoff = (
    gamma_options["lower_percent_dose_cutoff"]
    / 100  # type: ignore
    * np.max(dose_reference)
)

relevant_slice = np.max(dose_reference, axis=(1, 2)) > lower_dose_cutoff
slice_start = np.max([np.where(relevant_slice)[0][0], 0])
slice_end = np.min([np.where(relevant_slice)[0][-1], len(z_ref)])


max_ref_dose = np.max(dose_reference)

z_vals = z_ref[slice(slice_start, slice_end, 1)]

eval_slices = [dose_evaluation[np.where(z_i == z_eval)[0][0], :, :] for z_i in z_vals]

ref_slices = [dose_reference[np.where(z_i == z_ref)[0][0], :, :] for z_i in z_vals]

gamma_slices = [gamma[np.where(z_i == z_ref)[0][0], :, :] for z_i in z_vals]

diffs = [
    eval_slice - ref_slice for eval_slice, ref_slice in zip(eval_slices, ref_slices)
]

max_diff = np.max(np.abs(diffs))


for z_val, eval_slice, ref_slice, diff, gamma_slice in zip(
    z_vals, eval_slices, ref_slices, diffs, gamma_slices
):
    fig, ax = plt.subplots(figsize=(13, 10), nrows=2, ncols=2)

    c00 = ax[0, 0].contourf(
        x_eval,
        y_eval,
        eval_slice,
        100,
        vmin=0,
        vmax=max_ref_dose,
        cmap=plt.get_cmap("viridis"),
    )
    ax[0, 0].set_title("Evaluation")
    fig.colorbar(c00, ax=ax[0, 0], label="Dose (Gy)")
    ax[0, 0].invert_yaxis()
    ax[0, 0].set_xlabel("x (mm)")
    ax[0, 0].set_ylabel("z (mm)")

    c01 = ax[0, 1].contourf(
        x_ref,
        y_ref,
        ref_slice,
        100,
        vmin=0,
        vmax=max_ref_dose,
        cmap=plt.get_cmap("viridis"),
    )
    ax[0, 1].set_title("Reference")
    fig.colorbar(c01, ax=ax[0, 1], label="Dose (Gy)")
    ax[0, 1].invert_yaxis()
    ax[0, 1].set_xlabel("x (mm)")
    ax[0, 1].set_ylabel("z (mm)")

    c10 = ax[1, 0].contourf(
        x_ref,
        y_ref,
        diff,
        100,
        vmin=-max_diff,
        vmax=max_diff,
        cmap=plt.get_cmap("seismic"),
    )
    ax[1, 0].set_title("Dose difference")
    fig.colorbar(c10, ax=ax[1, 0], label="[Dose Eval] - [Dose Ref] (Gy)")
    ax[1, 0].invert_yaxis()
    ax[1, 0].set_xlabel("x (mm)")
    ax[1, 0].set_ylabel("z (mm)")

    c11 = ax[1, 1].contourf(
        x_ref, y_ref, gamma_slice, 100, vmin=0, vmax=2, cmap=plt.get_cmap("coolwarm")
    )
    ax[1, 1].set_title("Local Gamma ({})".format(threshold_string))
    fig.colorbar(c11, ax=ax[1, 1], label="Gamma Value")
    ax[1, 1].invert_yaxis()
    ax[1, 1].set_xlabel("x (mm)")
    ax[1, 1].set_ylabel("z (mm)")

    fig.savefig(os.path.join(output_dir, "slice_{:+06.1f}.gamma.png".format(z_val)))
