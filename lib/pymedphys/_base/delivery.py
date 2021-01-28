# Copyright (C) 2019 Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import functools
from collections import namedtuple
from typing import Dict, List, Tuple, Type, TypeVar, Union

from pymedphys._imports import numpy as np

from pymedphys._utilities.controlpoints import (
    remove_irrelevant_control_points,
    to_tuple,
)

# https://stackoverflow.com/a/44644576/3912576
# Create a generic variable that can be 'Parent', or any subclass.
DeliveryGeneric = TypeVar("DeliveryGeneric", bound="DeliveryBase")


DeliveryNamedTuple = namedtuple(
    "Delivery", ["monitor_units", "gantry", "collimator", "mlc", "jaw"]
)


class DeliveryBase(DeliveryNamedTuple):
    @property
    def mu(self):
        return self.monitor_units

    @classmethod
    def combine(cls, *args):
        first = cls(*args[0])

        if len(args) == 1:
            return first

        return first.merge(*args[1::])

    def merge(self: DeliveryGeneric, *args: DeliveryGeneric) -> DeliveryGeneric:
        cls = type(self)
        separate: List[DeliveryGeneric] = [self] + [*args]
        collection: Dict[str, Tuple] = {}

        for delivery_data in separate:
            for field in delivery_data._fields:  # pylint: disable=no-member
                try:
                    collection[field] = np.concatenate(
                        [collection[field], getattr(delivery_data, field)], axis=0
                    )
                except KeyError:
                    collection[field] = getattr(delivery_data, field)

        mu = np.concatenate([[0], np.diff(collection["monitor_units"])])
        mu[mu < 0] = 0
        collection["monitor_units"] = np.cumsum(mu)

        merged = cls(**collection)

        return merged

    def __new__(cls, *args, **kwargs):
        new_args = (to_tuple(arg) for arg in args)
        new_kwargs = {key: to_tuple(item) for key, item in kwargs.items()}
        return super().__new__(cls, *new_args, **new_kwargs)

    @classmethod
    def _empty(cls: Type[DeliveryGeneric]) -> DeliveryGeneric:
        return cls(
            tuple(),
            tuple(),
            tuple(),
            tuple((tuple((tuple(), tuple())),)),
            tuple((tuple(), tuple())),
        )

    @functools.lru_cache()
    def _filter_cps(self):
        cls = type(self)
        return cls(*remove_irrelevant_control_points(*self))

    @functools.lru_cache()
    def _mask_by_gantry(
        self,
        angles: Union[Tuple, float, int],
        gantry_tolerance=3,
        allow_missing_angles=False,
    ):

        try:
            _ = iter(angles)  # type: ignore
            iterable_angles = tuple(angles)  # type: ignore
        except TypeError:
            # Not iterable, assume just one angle provided
            iterable_angles = tuple((angles,))

        masks = self._gantry_angle_masks(
            iterable_angles, gantry_tolerance, allow_missing_angles=allow_missing_angles
        )

        all_masked_delivery_data = tuple(
            self._apply_mask_to_delivery_data(mask) for mask in masks
        )

        return all_masked_delivery_data

    @functools.lru_cache()
    def _metersets(self, gantry_angles, gantry_tolerance):
        all_masked_delivery_data = self._mask_by_gantry(
            gantry_angles, gantry_tolerance, allow_missing_angles=True
        )

        metersets = []
        for delivery_data in all_masked_delivery_data:
            try:
                metersets.append(delivery_data.monitor_units[-1])
            except IndexError:
                continue

        return tuple(metersets)

    def _extract_one_gantry_angle(
        self: DeliveryGeneric, gantry_angle, gantry_tolerance=3
    ) -> DeliveryGeneric:
        near_angle = self._gantry_angle_mask(gantry_angle, gantry_tolerance)

        return self._apply_mask_to_delivery_data(near_angle)

    def _gantry_angle_masks(
        self, gantry_angles, gantry_tol, allow_missing_angles=False
    ):
        masks = [
            self._gantry_angle_mask(gantry_angle, gantry_tol)
            for gantry_angle in gantry_angles
        ]

        for mask in masks:
            if np.all(mask == 0):
                continue

            # TODO: Apply mask by more than just gantry angle to appropriately
            # extract beam index even when multiple beams have the same gantry
            # angle
            is_duplicate_gantry_angles = (
                np.sum(np.abs(np.diff(np.concatenate([[0], mask, [0]])))) != 2
            )

            if is_duplicate_gantry_angles:
                raise ValueError("Duplicate gantry angles not yet supported")

        try:
            assert np.all(
                np.sum(masks, axis=0) == 1
            ), "Not all beams were captured by the gantry tolerance of " " {}".format(
                gantry_tol
            )
        except AssertionError:
            if not allow_missing_angles:
                print("Allowable gantry angles = {}".format(gantry_angles))
                gantry = np.array(self.gantry, copy=False)
                out_of_tolerance = np.unique(
                    gantry[np.sum(masks, axis=0) == 0]
                ).tolist()
                print(
                    "The gantry angles out of tolerance were {}".format(
                        out_of_tolerance
                    )
                )

                raise

        return masks

    def _gantry_angle_mask(self, gantry_angle, gantry_angle_tol):
        near_angle = np.abs(np.array(self.gantry) - gantry_angle) <= gantry_angle_tol
        assert np.all(np.diff(np.where(near_angle)[0]) == 1)

        return near_angle

    def _apply_mask_to_delivery_data(self: DeliveryGeneric, mask) -> DeliveryGeneric:
        cls = type(self)

        new_delivery_data = []
        for item in self:
            new_delivery_data.append(np.array(item)[mask])

        new_monitor_units = new_delivery_data[0]
        try:
            first_monitor_unit_item = new_monitor_units[0]
        except IndexError:
            return cls(*new_delivery_data)

        new_delivery_data[0] = np.round(
            np.array(new_delivery_data[0], copy=False) - first_monitor_unit_item,
            decimals=7,
        )

        return cls(*new_delivery_data)

    def _strip_delivery_data(self: DeliveryGeneric, skip_size) -> DeliveryGeneric:
        cls = type(self)

        new_delivery_data = []
        for item in self:
            new_delivery_data.append(np.array(item)[::skip_size])

        return cls(*new_delivery_data)
