# Copyright (C) 2018 Cancer Care Associates

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


import numpy as np

from pymedphys_base.deliverydata import DeliveryDataBase


def get_all_masked_delivery_data(delivery_data: DeliveryDataBase,
                                 template_gantry_angles, gantry_tol,
                                 quiet=False):
    masks = get_gantry_angle_masks(
        delivery_data, template_gantry_angles, gantry_tol, quiet=quiet)

    all_masked_delivery_data = tuple(
        apply_mask_to_delivery_data(delivery_data, mask)
        for mask in masks
    )

    return all_masked_delivery_data


def get_gantry_angle_masks(delivery_data: DeliveryDataBase, gantry_angles,
                           gantry_tol, quiet=False):
    masks = [
        gantry_angle_mask(delivery_data, gantry_angle, gantry_tol)
        for gantry_angle in gantry_angles
    ]

    for mask in masks:
        if np.all(mask == 0):
            continue

        # TODO: Apply mask by more than just gantry angle to appropriately
        # extract beam index even when multiple beams have the same gantry
        # angle
        is_duplicate_gantry_angles = not np.sum(
            np.abs(np.diff(np.concatenate([[0], mask, [0]])))) == 2

        if is_duplicate_gantry_angles:
            raise ValueError("Duplicate gantry angles not yet supported")

    try:
        assert np.all(np.sum(masks, axis=0) == 1), (
            "Not all beams were captured by the gantry tolerance of "
            " {}".format(gantry_tol)
        )
    except AssertionError:
        if not quiet:
            print("Allowable gantry angles = {}".format(gantry_angles))
            gantry = np.array(delivery_data.gantry, copy=False)
            out_of_tolerance = np.unique(
                gantry[np.sum(masks, axis=0) == 0]).tolist()
            print("The gantry angles out of tolerance were {}".format(
                out_of_tolerance))

        raise

    return masks


def gantry_angle_mask(delivery_data, gantry_angle, gantry_angle_tol):
    near_angle = np.abs(
        np.array(delivery_data.gantry) - gantry_angle) <= gantry_angle_tol
    assert np.all(np.diff(np.where(near_angle)[0]) == 1)

    return near_angle


def apply_mask_to_delivery_data(delivery_data: DeliveryDataBase, mask):
    DeliveryDataObject = type(delivery_data)

    new_delivery_data = []
    for item in delivery_data:
        new_delivery_data.append(np.array(item)[mask].tolist())

    new_monitor_units = new_delivery_data[0]
    try:
        first_monitor_unit_item = new_monitor_units[0]
    except IndexError:
        return DeliveryDataObject(*new_delivery_data)

    new_delivery_data[0] = np.round(
        np.array(new_delivery_data[0], copy=False)
        - first_monitor_unit_item, decimals=7
    ).tolist()

    return DeliveryDataObject(*new_delivery_data)


def extract_one_gantry_angle(delivery_data, gantry_angle, gantry_angle_tol=3):
    near_angle = gantry_angle_mask(
        delivery_data, gantry_angle, gantry_angle_tol)

    return apply_mask_to_delivery_data(delivery_data, near_angle)


def get_metersets_from_delivery_data(all_masked_delivery_data):
    metersets = []
    for delivery_data in all_masked_delivery_data:
        try:
            metersets.append(delivery_data.monitor_units[-1])
        except IndexError:
            continue

    return tuple(metersets)
