# Copyright (C) 2018 Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from pymedphys._imports import numpy as np


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
