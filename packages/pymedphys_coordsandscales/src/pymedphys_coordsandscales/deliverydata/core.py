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

"""Working with delivery data from either logfiles or Mosaiq.
"""

from collections import namedtuple

import numpy as np

# Make the creation of DeliveryData look a bit like this...
# Or a bit like the dataclass ...
DeliveryData = namedtuple(
    'DeliveryData',
    ['monitor_units', 'gantry', 'collimator', 'mlc', 'jaw'])


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


def find_relevant_control_points(mu):
    """Returns that control points that had an MU difference either side.
    """
    mu_diff = np.diff(mu)
    no_change = mu_diff == 0
    no_change_before = no_change[0:-1]
    no_change_after = no_change[1::]

    no_change_before_and_after = no_change_before & no_change_after
    irrelevant_control_point = np.hstack(
        [no_change[0], no_change_before_and_after, no_change[-1]])
    relevant_control_points = np.invert(irrelevant_control_point)

    return relevant_control_points


def remove_irrelevant_control_points(mu, mlc, jaw):
    """Removes control points that don't have MU delivery
    """
    assert len(mu) > 0, "No control points found"

    mu = np.array(mu)
    mlc = np.array(mlc)
    jaw = np.array(jaw)

    control_points_to_use = find_relevant_control_points(mu)

    mu = mu[control_points_to_use]
    mlc = mlc[control_points_to_use, :, :]
    jaw = jaw[control_points_to_use, :]

    return mu, mlc, jaw
