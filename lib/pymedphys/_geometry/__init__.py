# Copyright (C) 2026 Matthew Jennings

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Planar polygons, such as RT Structure Set contours, and their meeting
with pixel grids, in NumPy alone.

:mod:`~pymedphys._geometry.polygons` clips a polygon by half-spaces, groups
polygons by the plane they lie in, and joins pieces that tile a region back
into its rings; :mod:`~pymedphys._geometry.pixel_grids` finds a polygon's
part within chosen pixels of a grid, each pixel taken as the square of the
points nearest its centre. Their results are exact up to floating point: no
polygon is approximated by pixels. :mod:`~pymedphys._geometry.rasters`
fills polygons onto a grid of points instead, for a picture or a sampled
mask of the region that they bound.
"""
