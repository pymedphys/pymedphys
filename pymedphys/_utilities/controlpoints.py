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


def find_relevant_control_points(mu):
    """Returns that control points that had an MU difference either side.
    """
    mu_diff = np.diff(mu)
    no_change = mu_diff == 0
    try:
        start = no_change[0]
        end = no_change[-1]
    except IndexError:
        all_true = np.empty_like(mu).astype(bool)
        all_true.fill(True)
        return all_true

    no_change_before = no_change[0:-1]
    no_change_after = no_change[1::]

    no_change_before_and_after = no_change_before & no_change_after

    irrelevant_control_point = np.hstack([start, no_change_before_and_after, end])
    relevant_control_points = np.invert(irrelevant_control_point)

    return relevant_control_points


def remove_irrelevant_control_points(monitor_units, *args):
    relevant_control_points = find_relevant_control_points(monitor_units)

    provided_values = tuple((monitor_units, *args))

    result = tuple(np.array(item)[relevant_control_points] for item in provided_values)

    return result


def to_tuple(a):
    # https://stackoverflow.com/a/10016613/3912576
    try:
        return tuple(to_tuple(i) for i in a)
    except TypeError:
        return a
