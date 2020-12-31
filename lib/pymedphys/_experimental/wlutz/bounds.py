# Copyright (C) Simon Biggs

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


def check_if_at_bounds(centre, bounds):
    x_at_bounds = np.any(np.array(centre[0]) == np.array(bounds[0]))
    y_at_bounds = np.any(np.array(centre[1]) == np.array(bounds[1]))

    any_at_bounds = x_at_bounds or y_at_bounds
    return any_at_bounds
