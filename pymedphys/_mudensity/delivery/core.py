# Copyright (C) 2019 Simon Biggs

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


from pymedphys._base.delivery import DeliveryBase

from ..mudensity import calc_mu_density


class DeliveryMuDensity(DeliveryBase):
    def mudensity(
        self,
        gantry_angles=None,
        gantry_tolerance=3,
        grid_resolution=1,
        output_always_list=False,
    ):
        if gantry_angles is None:
            gantry_angles = 0
            gantry_tolerance = 500

        masked_by_gantry = self._mask_by_gantry(gantry_angles, gantry_tolerance)

        mudensities = []
        for delivery_data in masked_by_gantry:
            mudensities.append(
                calc_mu_density(
                    delivery_data.monitor_units,
                    delivery_data.mlc,
                    delivery_data.jaw,
                    grid_resolution=grid_resolution,
                )
            )

        if not output_always_list:
            if len(mudensities) == 1:
                return mudensities[0]

        return mudensities
