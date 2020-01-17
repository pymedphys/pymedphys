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


# pylint: disable = protected-access

import pymedphys._wlutz.findbb

# def test_bb_at_bounds_check():
#     edge_lengths = [20, 24]
#     bb_diameter = 8

#     bb_bounds = pymedphys._wlutz.findbb.define_bb_bounds(bb_diameter, edge_lengths)
#     assert pymedphys._wlutz.findbb.check_if_at_bounds((0, -7.5), bb_bounds)
#     assert not pymedphys._wlutz.findbb.check_if_at_bounds((0, -5.5), bb_bounds)
#     assert pymedphys._wlutz.findbb.check_if_at_bounds((5.5, 0), bb_bounds)
