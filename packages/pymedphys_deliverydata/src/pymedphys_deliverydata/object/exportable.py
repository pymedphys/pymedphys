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


from ..base import DeliveryDataBase
from ..dicom import (
    delivery_data_to_dicom,
    dicom_to_delivery_data)
from ..utilities import (
    filter_out_irrelevant_control_points,
    get_all_masked_delivery_data)


class DeliveryData(DeliveryDataBase):
    @classmethod
    def from_delivery_data_base(cls, delivery_data_base):
        cls(**delivery_data_base)

    @classmethod
    def from_dicom(cls, dataset):
        return cls.from_delivery_data_base(
            dicom_to_delivery_data(dataset))

    def to_dicom(self, template):
        return delivery_data_to_dicom(self, template)

    def filter_cps(self):
        return type(self).from_delivery_data_base(self)

    def mask_by_gantry(self, angles, tolerance):
        base_masked = get_all_masked_delivery_data(self, angles, tolerance)
        reassigned_class = []
        for masked in base_masked:
            if type(masked) is not type(self):
                reassigned_class.append(
                    type(self).from_delivery_data_base(masked))
            else:
                reassigned_class.append(masked)

        return reassigned_class
