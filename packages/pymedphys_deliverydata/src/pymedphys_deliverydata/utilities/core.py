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

from pymedphys_utilities.rtplan import find_relevant_control_points

from ..base import DeliveryDataBase


def get_delivery_parameters(delivery_data):
    mu = np.array(delivery_data.monitor_units)  # pylint: disable=C0103
    mlc = np.array(delivery_data.mlc)
    jaw = np.array(delivery_data.jaw)

    return mu, mlc, jaw


def extract_angle_from_delivery_data(delivery_data, gantry_angle,
                                     gantry_tolerance=0):
    moniter_units = np.array(delivery_data.monitor_units)
    relevant_control_points = find_relevant_control_points(moniter_units)

    mu = moniter_units[relevant_control_points]
    mlc = np.array(delivery_data.mlc)[relevant_control_points]
    jaw = np.array(delivery_data.jaw)[relevant_control_points]
    gantry_angles = np.array(delivery_data.gantry)[relevant_control_points]

    gantry_angle_within_tolerance = (
        np.abs(gantry_angles - gantry_angle) <= gantry_tolerance)
    diff_mu = np.concatenate([[0], np.diff(mu)])[gantry_angle_within_tolerance]
    mu = np.cumsum(diff_mu)

    mlc = mlc[gantry_angle_within_tolerance]
    jaw = jaw[gantry_angle_within_tolerance]

    return mu, mlc, jaw


def strip_delivery_data(delivery_data, skip_size):
    DeliveryDataObject = type(delivery_data)

    new_delivery_data = []
    for item in delivery_data:
        new_delivery_data.append(np.array(item)[::skip_size].tolist())

    return DeliveryDataObject(*new_delivery_data)


def filter_out_irrelevant_control_points(delivery_data: DeliveryDataBase) -> DeliveryDataBase:
    DeliveryDataObject = type(delivery_data)

    relevant_control_points = find_relevant_control_points(
        delivery_data.monitor_units)

    new_delivery_data = []
    for item in delivery_data:
        new_delivery_data.append(
            np.array(item)[relevant_control_points].tolist())

    return DeliveryDataObject(*new_delivery_data)
