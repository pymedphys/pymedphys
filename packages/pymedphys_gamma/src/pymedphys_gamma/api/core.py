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

from pymedphys_dicom.dicom import axes_and_dose_from_dicom

from ..implementation import gamma_shell, gamma_filter_numpy
from ..utilities import calculate_pass_rate


def gamma_dicom(dicom_ref_filepath, dicom_eval_filepath,
                dose_percent_threshold, distance_mm_threshold,
                **kwargs):

    axes_reference, dose_reference = axes_and_dose_from_dicom(
        dicom_ref_filepath)
    axes_evaluation, dose_evaluation = axes_and_dose_from_dicom(
        dicom_eval_filepath)

    gamma = gamma_shell(
        axes_reference, dose_reference,
        axes_evaluation, dose_evaluation,
        dose_percent_threshold, distance_mm_threshold,
        **kwargs)

    return gamma


def gamma_percent_pass(dcm_ref_filepath, dcm_eval_filepath,
                       dose_percent_threshold, distance_mm_threshold,
                       method='shell', **kwargs):

    axes_reference, dose_reference = axes_and_dose_from_dicom(
        dcm_ref_filepath)
    axes_evaluation, dose_evaluation = axes_and_dose_from_dicom(
        dcm_eval_filepath)

    if method == 'shell':
        gamma = gamma_shell(
            axes_reference, dose_reference,
            axes_evaluation, dose_evaluation,
            dose_percent_threshold, distance_mm_threshold,
            **kwargs)

        percent_pass = calculate_pass_rate(gamma)

    elif method == 'filter':
        percent_pass = gamma_filter_numpy(
            axes_reference, dose_reference,
            axes_evaluation, dose_evaluation,
            dose_percent_threshold, distance_mm_threshold,
            **kwargs)
    else:
        raise ValueError('method should be either `shell` or `filter`')

    return percent_pass
