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


from pymedphys_mudensity.mudensity import calc_mu_density

from ..base import DeliveryDataBase
from ..dicom import (
    delivery_data_to_dicom,
    dicom_to_delivery_data)
from ..utilities import (
    filter_out_irrelevant_control_points,
    get_all_masked_delivery_data,
    get_metersets_from_delivery_data,
    to_tuple)


class DeliveryData(DeliveryDataBase):
    def __new__(cls, *args):
        new_args = (
            to_tuple(arg)
            for arg in args
        )
        return super().__new__(cls, *new_args)

    @classmethod
    def from_delivery_data_base(cls, delivery_data_base):
        if type(delivery_data_base) is type(cls):
            return delivery_data_base

        return cls(**delivery_data_base)

    @classmethod
    def from_dicom(cls, dataset):
        return cls.from_delivery_data_base(
            dicom_to_delivery_data(dataset))

    @classmethod
    def empty(cls):
        return cls(
            tuple(),
            tuple(),
            tuple(),
            tuple(
                (tuple(), tuple())
            ),
            tuple(
                (tuple(), tuple())))

    def to_dicom(self, template):
        return delivery_data_to_dicom(self, template)

    def filter_cps(self):
        return filter_out_irrelevant_control_points(self)

    @functools.lru_cache()
    def mask_by_gantry(self, angles: Union[tuple, float, int], tolerance=3):
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

    def mudensity(self, gantry_angles, gantry_tolerance=0, grid_resolution=1):
        masked_by_gantry = self.mask_by_gantry(gantry_angles, gantry_tolerance)

        mudensities = []
        for delivery_data in masked_by_gantry:
            mudensities.append(calc_mu_density(
                delivery_data.monitor_units,
                delivery_data.mlc,
                delivery_data.jaw,
                grid_resolution=grid_resolution))

        return mudensities
