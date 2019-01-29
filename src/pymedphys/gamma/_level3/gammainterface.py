# Copyright (C) 2018 Simon Biggs
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version (the "AGPL-3.0+").

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License and the additional terms for more
# details.

# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

# ADDITIONAL TERMS are also included as allowed by Section 7 of the GNU
# Affero General Public License. These additional terms are Sections 1, 5,
# 6, 7, 8, and 9 from the Apache License, Version 2.0 (the "Apache-2.0")
# where all references to the definition "License" are instead defined to
# mean the AGPL-3.0+.

# You should have received a copy of the Apache-2.0 along with this
# program. If not, see <http://www.apache.org/licenses/LICENSE-2.0>.

# import numpy as np
# import matplotlib.pyplot as plt

from ...libutils import get_imports
from ...dcm import coords_and_dose_from_dcm

from .._level1.gammafilter import gamma_filter_numpy, convert_to_percent_pass
from .._level2.gammashell import gamma_shell

IMPORTS = get_imports(globals())


def gamma_dcm(dcm_ref_filepath, dcm_eval_filepath,
              dose_percent_threshold, distance_mm_threshold,
              **kwargs):

    coords_reference, dose_reference = coords_and_dose_from_dcm(
        dcm_ref_filepath)
    coords_evaluation, dose_evaluation = coords_and_dose_from_dcm(
        dcm_eval_filepath)

    gamma = gamma_shell(
        coords_reference, dose_reference,
        coords_evaluation, dose_evaluation,
        dose_percent_threshold, distance_mm_threshold,
        **kwargs)

    return gamma


# def gamma_with_reports(dcm_ref_filepath, dcm_eval_filepath,
#                        dose_percent_threshold, distance_mm_threshold,
#                        **kwargs):
#     """Prototype reporting of gamma. Needs to be reworked before merge.
#     """
#     coords_reference, dose_reference = coords_and_dose_from_dcm(
#         dcm_ref_filepath)
#     coords_evaluation, dose_evaluation = coords_and_dose_from_dcm(
#         dcm_eval_filepath)

#     gamma = gamma_shell(
#         coords_reference, dose_reference,
#         coords_evaluation, dose_evaluation,
#         dose_percent_threshold, distance_mm_threshold,
#         **kwargs)

#     valid_gamma = gamma[~np.isnan(gamma)]
#     valid_gamma[valid_gamma > 2] = 2

#     plt.hist(valid_gamma, 30)
#     plt.xlim([0, 2])

#     plt.show()

#     print(np.sum(valid_gamma <= 1) / len(valid_gamma))

#     x_reference, y_reference, z_reference = coords_reference
#     x_evaluation, y_evaluation, z_evaluation = coords_evaluation

#     relevant_slice = (
#         np.max(dose_evaluation, axis=(0, 1)) > 0)  # TODO fix hacky prototyping
#     slice_start = np.max([
#         np.where(relevant_slice)[0][0],
#         0])
#     slice_end = np.min([
#         np.where(relevant_slice)[0][-1],
#         len(z_evaluation)])

#     max_ref_dose = np.max(dose_reference)

#     cut_off_gamma = gamma.copy()
#     greater_than_2_ref = (cut_off_gamma > 2) & ~np.isnan(cut_off_gamma)
#     cut_off_gamma[greater_than_2_ref] = 2

#     for z_i in z_evaluation[slice_start:slice_end:5]:
#         i = np.where(z_i == z_evaluation)[0][0]
#         j = np.where(z_i == z_reference)[0][0]
#         print("======================================================================")
#         print("Slice = {0}".format(z_i))

#         plt.contourf(
#             x_evaluation, y_evaluation, dose_evaluation[:, :, j], 30,
#             vmin=0, vmax=max_ref_dose, cmap=plt.get_cmap('viridis'))
#         plt.title("Evaluation")
#         plt.colorbar()
#         plt.show()

#         plt.contourf(
#             x_reference, y_reference, dose_reference[:, :, j], 30,
#             vmin=0, vmax=max_ref_dose, cmap=plt.get_cmap('viridis'))
#         plt.title("Reference")
#         plt.colorbar()
#         plt.show()

#         plt.contourf(
#             x_evaluation, y_evaluation, cut_off_gamma[:, :, i], 30,
#             vmin=0, vmax=2, cmap=plt.get_cmap('bwr'))
#         plt.title("Gamma")
#         plt.colorbar()
#         plt.show()

#         print("\n")


def gamma_percent_pass(dcm_ref_filepath, dcm_eval_filepath,
                       dose_percent_threshold, distance_mm_threshold,
                       method='shell', **kwargs):

    coords_reference, dose_reference = coords_and_dose_from_dcm(
        dcm_ref_filepath)
    coords_evaluation, dose_evaluation = coords_and_dose_from_dcm(
        dcm_eval_filepath)

    if method == 'shell':
        gamma = gamma_shell(
            coords_reference, dose_reference,
            coords_evaluation, dose_evaluation,
            dose_percent_threshold, distance_mm_threshold,
            **kwargs)

        percent_pass = convert_to_percent_pass(gamma)

    elif method == 'filter':
        percent_pass = gamma_filter_numpy(
            coords_reference, dose_reference,
            coords_evaluation, dose_evaluation,
            dose_percent_threshold, distance_mm_threshold,
            **kwargs)
    else:
        raise ValueError('method should be either `shell` or `filter`')

    return percent_pass
