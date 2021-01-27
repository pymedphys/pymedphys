# Copyright (C) 2019 Simon Biggs

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


from pymedphys._base.delivery import DeliveryBase
from pymedphys._vendor.deprecated import deprecated as _deprecated

from ..metersetmap import calc_metersetmap


class DeliveryMetersetMap(DeliveryBase):
    def metersetmap(
        self,
        gantry_angles=None,
        gantry_tolerance=3,
        grid_resolution=None,
        max_leaf_gap=None,
        leaf_pair_widths=None,
        min_step_per_pixel=None,
        output_always_list=False,
    ):
        if gantry_angles is None:
            gantry_angles = 0
            gantry_tolerance = 500
        else:
            gantry_angles = tuple(gantry_angles)

        filtered_delivery = self._filter_cps()

        masked_by_gantry = (
            filtered_delivery._mask_by_gantry(  # pylint: disable = protected-access
                gantry_angles, gantry_tolerance
            )
        )

        metersetmaps = []
        for delivery_data in masked_by_gantry:
            metersetmaps.append(
                calc_metersetmap(
                    delivery_data.monitor_units,
                    delivery_data.mlc,
                    delivery_data.jaw,
                    grid_resolution=grid_resolution,
                    max_leaf_gap=max_leaf_gap,
                    leaf_pair_widths=leaf_pair_widths,
                    min_step_per_pixel=min_step_per_pixel,
                )
            )

        if not output_always_list:
            if len(metersetmaps) == 1:
                return metersetmaps[0]

        return metersetmaps

    @_deprecated(
        reason=(
            "pymedphys.Delivery.mudensity has been replaced by "
            "pymedphys.Delivery.metersetmap"
        )
    )
    def mudensity(
        self,
        gantry_angles=None,
        gantry_tolerance=3,
        grid_resolution=None,
        max_leaf_gap=None,
        leaf_pair_widths=None,
        min_step_per_pixel=None,
        output_always_list=False,
    ):
        return self.metersetmap(
            gantry_angles=gantry_angles,
            gantry_tolerance=gantry_tolerance,
            grid_resolution=grid_resolution,
            max_leaf_gap=max_leaf_gap,
            leaf_pair_widths=leaf_pair_widths,
            min_step_per_pixel=min_step_per_pixel,
            output_always_list=output_always_list,
        )
