# Copyright (C) 2019 Cancer Care Associates

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


import functools
from typing import Union, Tuple

import numpy as np

from pymedphys_base.deliverydata import DeliveryDataBase
from pymedphys_mudensity.mudensity import calc_mu_density

from pymedphys_dicom.rtplan import (
    get_gantry_angles_from_dicom,
    get_fraction_group_beam_sequence_and_meterset,
    convert_to_one_fraction_group)

from ..dicom import (
    delivery_data_to_dicom,
    delivery_data_from_dicom,
    gantry_tol_from_gantry_angles)
from ..utilities import (
    filter_out_irrelevant_control_points,
    get_all_masked_delivery_data,
    get_metersets_from_delivery_data)
from ..logfile import delivery_data_from_logfile


class DeliveryData(DeliveryDataBase):
    def __new__(cls, *args, **kwargs):
        return super().__new__(cls, *args, **kwargs)

    @classmethod
    def from_delivery_data_base(cls, delivery_data_base):
        if type(delivery_data_base) is type(cls):
            return delivery_data_base

        return cls(*delivery_data_base)

    @classmethod
    def from_dicom(cls, dataset, fraction_group_number):
        return cls.from_delivery_data_base(
            delivery_data_from_dicom(dataset, fraction_group_number))

    def to_dicom(self, template, fraction_group_number=None):
        filtered = self.filter_cps()
        if fraction_group_number is None:
            fraction_group_number = self.fraction_group_number(template)

        return delivery_data_to_dicom(
            filtered, template, fraction_group_number)

    @classmethod
    def from_logfile(cls, filepath):
        return cls.from_delivery_data_base(
            delivery_data_from_logfile(filepath))

    @functools.lru_cache()
    def filter_cps(self):
        return filter_out_irrelevant_control_points(self)

    @functools.lru_cache()
    def mask_by_gantry(self, angles: Union[Tuple, float, int], tolerance=3):
        iterable_angles: tuple

        try:
            _ = iter(angles)  # type: ignore
            iterable_angles = tuple(angles)  # type: ignore
        except TypeError:
            # Not iterable, assume just one angle provided
            iterable_angles = (angles,)

        return get_all_masked_delivery_data(self, iterable_angles, tolerance)

    @functools.lru_cache()
    def metersets(self, gantry_angles, gantry_tolerance):
        self.mask_by_gantry(gantry_angles, gantry_tolerance)
        return get_metersets_from_delivery_data(
            self.mask_by_gantry(gantry_angles, gantry_tolerance))

    def mudensity(self, gantry_angles=None, gantry_tolerance=None,
                  grid_resolution=1, output_always_list=False):
        if gantry_angles is None:
            gantry_angles = 0
            gantry_tolerance = 500
        elif gantry_tolerance is None:
            gantry_tolerance = gantry_tol_from_gantry_angles(gantry_angles)

        masked_by_gantry = self.mask_by_gantry(gantry_angles, gantry_tolerance)

        mudensities = []
        for delivery_data in masked_by_gantry:
            mudensities.append(calc_mu_density(
                delivery_data.monitor_units,
                delivery_data.mlc,
                delivery_data.jaw,
                grid_resolution=grid_resolution))

        if not output_always_list:
            if len(mudensities) == 1:
                return mudensities[0]

        return mudensities

    def fraction_group_number(self, dicom_template, gantry_tol=3,
                              meterset_tol=0.5):
        filtered = self.filter_cps()
        fraction_groups = dicom_template.FractionGroupSequence

        if len(fraction_groups) == 1:
            return fraction_groups[0].FractionGroupNumber

        fraction_group_numbers = [
            fraction_group.FractionGroupNumber
            for fraction_group in fraction_groups
        ]

        dicom_metersets_by_fraction_group = [
            get_fraction_group_beam_sequence_and_meterset(
                dicom_template, fraction_group_number)[1]
            for fraction_group_number in fraction_group_numbers
        ]

        split_by_fraction_group = [
            convert_to_one_fraction_group(
                dicom_template, fraction_group_number)
            for fraction_group_number in fraction_group_numbers
        ]

        gantry_angles_by_fraction_group = [
            get_gantry_angles_from_dicom(dataset)
            for dataset in split_by_fraction_group]

        masked_delivery_data_by_fraction_group = []
        for gantry_angles in gantry_angles_by_fraction_group:
            try:
                masked = get_all_masked_delivery_data(
                    filtered, gantry_angles, gantry_tol, quiet=True)
            except AssertionError:
                masked = [DeliveryDataBase.empty()]

            masked_delivery_data_by_fraction_group.append(masked)

        deliver_data_metersets_by_fraction_group = [
            get_metersets_from_delivery_data(masked_delivery_data)
            for masked_delivery_data in masked_delivery_data_by_fraction_group
        ]

        maximum_deviations = []
        for dicom_metersets, delivery_data_metersets in zip(
                dicom_metersets_by_fraction_group,  # nopep8
                deliver_data_metersets_by_fraction_group):  # nopep8

            try:
                maximmum_diff = np.max(np.abs(
                    np.array(dicom_metersets) -
                    np.array(delivery_data_metersets)))
            except ValueError:
                maximmum_diff = np.inf

            maximum_deviations.append(maximmum_diff)

        deviations_within_tol = np.array(maximum_deviations) <= meterset_tol

        if np.sum(deviations_within_tol) < 1:
            raise ValueError(
                "A fraction group was not able to be found with the metersets "
                "and gantry angles defined by the tolerances provided. "
                "Please manually define the fraction group number.")

        if np.sum(deviations_within_tol) > 1:
            raise ValueError(
                "More than one fraction group was found that had metersets "
                "and gantry angles within the tolerances provided. "
                "Please manually define the fraction group number.")

        fraction_group_number = np.array(
            fraction_group_numbers)[deviations_within_tol]

        return fraction_group_number
