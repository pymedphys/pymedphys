# # Copyright (C) 2020 Cancer Care Associates

# # Licensed under the Apache License, Version 2.0 (the "License");
# # you may not use this file except in compliance with the License.
# # You may obtain a copy of the License at

# #     http://www.apache.org/licenses/LICENSE-2.0

# # Unless required by applicable law or agreed to in writing, software
# # distributed under the License is distributed on an "AS IS" BASIS,
# # WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# # See the License for the specific language governing permissions and
# # limitations under the License.


# import os  # pylint: disable = unused-import
# from typing import (  # pylint: disable = unused-import
#     Any,
#     Callable,
#     Dict,
#     Literal,
#     Union,
#     cast,
# )

# from pymedphys._imports import numpy as np
# from pymedphys._imports import pylinac

# from pymedphys import _losslessjpeg as lljpeg
# from pymedphys._vendor.pylinac import winstonlutz as _pylinac_wlutz

# from . import findbb, findfield, imginterp, iview, utilities

# PathOrNumpyArray = Union["np.ndarray", "os.PathLike[Any]", str]
# PathTypes = Union["os.PathLike[Any]", str]
# Algorithms = Literal[
#     "pymedphys", "pylinac-installed", "pylinac-v2.2.6", "pylinac-v2.2.7"
# ]


# class _FunctionResultDictionary:
#     def __init__(self, functions: Dict[Any, Callable] = None):
#         if functions is None:
#             functions = {}

#         self.functions = functions
#         self._results_cache: Dict[Any, Any] = {}

#     def __getitem__(self, item):
#         try:
#             return self._results_cache[item]
#         except KeyError:
#             self._results_cache[item] = self.functions[item]()

#         return self._results_cache[item]


# class LosslessIViewWinstonLutz:
#     def __init__(
#         self,
#         image: PathOrNumpyArray,
#         edge_lengths,
#         penumbra,
#         bb_diameter,
#         pylinac_interpolated_pixel_size=0.05,
#     ):
#         raw_image = _load_lossless_image(image)
#         self._x, self._y, self._image = iview.iview_image_transform(raw_image)
#         self._edge_lengths = edge_lengths
#         self._penumbra = penumbra
#         self._bb_diameter = bb_diameter
#         self._pylinac_interpolated_pixel_size = pylinac_interpolated_pixel_size

#         self._image_interpolator = None
#         self._field_rotation = None

#         self._field_centre = None
#         self._bb_centre = None

#         self._pylinac_wl_images = None
#         self._pylinac_wl_image_classes = _pylinac_wlutz.get_version_to_class_map()

#     def _reset(self):
#         self._field_centre = None
#         self._bb_centre = None

#     @property
#     def x(self):
#         return self._x

#     @property
#     def y(self):
#         return self._y

#     @property
#     def image(self):
#         return self._image

#     @property
#     def image_interpolator(self):
#         if self._image_interpolator is None:
#             self._image_interpolator = imginterp.create_interpolated_field(
#                 self.x, self.y, self.image
#             )

#         return self._image_interpolator

#     def pylinac_wl_images(self):
#         if self._pylinac_wl_images is None:
#             wl_image_creation_functions = {}
#             for key, PyLinacWLImage in VERSION_TO_CLASS_MAP.items():
#                 def f():
#                     image = _centralised_straight_image(
#                         self.image_interpolator,
#                         self.field_centre["pymedphys"],
#                         self.field_rotation,
#                         self.edge_lengths,
#                         self.penumbra,
#                         self.interpolated_pixel_size,
#                     )

#                     return PyLinacWLImage(image)

#                 wl_image_creation_functions[key] = f

#             self._pylinac_wl_images = _FunctionResultDictionary(wl_image_creation_functions)

#         return self._pylinac_wl_images


#     def _get_field_centre_algorithms_map(self):


#         return {
#             "pymedphys":
#         }

#     def _get_pylinac_field_centre_function(self, pylinac_version_key):
#         pylinac_version = _version_key_to_version(pylinac_version_key)


#     @property
#     def field_centre(self):
#         if self._field_centre is None:
#             self._field_centre =

#             self._find_field()

#         return self._field_centre

#     @property
#     def field_rotation(self):
#         if self._field_rotation is None:
#             if self._algorithm == "pymedphys":
#                 self._field_centre, self._field_rotation = self._find_field()
#             else:
#                 raise ValueError(
#                     "Field rotation can only be determined if the "
#                     'algorithm is set to "pymedphys"'
#                 )

#         return self._field_rotation

#     def _find_field_pymedphys(self):
#         if self._field_centre is None:
#             initial_centre = findfield.get_centre_of_mass(self.x, self.y, self.image)
#         else:
#             initial_centre = self._field_centre

#         field_centre, field_rotation = findfield.field_centre_and_rotation_refining(
#             self.image_interpolator, self._edge_lengths, self._penumbra, initial_centre
#         )

#         return field_centre, field_rotation

#     @property
#     def pylinac_wl_image(self):
#         if not self._algorithm.startswith("pylinac"):
#             raise ValueError("Need to be using a pylinac algorithm.")

#         if self._pylinac_wl_image is None:
#             pylinac_version = self._algorithm.split("-")[1]
#             if pylinac_version == "installed":
#                 pylinac_version = pylinac.__version__

#             VERSION_TO_CLASS_MAP = _pylinac_wlutz.get_version_to_class_map()

#             pymedphys_field_centre, pymedphys_field_rotation = _find_field_pymedphys(
#                 self
#             )

#             pylinac_image = _centralised_straight_image()

#             self._pylinac_wl_image = VERSION_TO_CLASS_MAP[pylinac_version]()

#         return self._pylinac_wl_image

#     def _find_field(self):
#         # if self._algorithm.startswith("pylinac"):
#         #     self.pylinac_wl_image

#         algorithm_map = {"pymedphys": self._find_field_pymedphys}
#         return algorithm_map[self._algorithm]()

#     @property
#     def bb_centre(self):
#         if self._bb_centre is None:
#             self._bb_centre = self._find_bb()

#         return self._bb_centre

#     def _find_bb_pymedphys(self):
#         return findbb.optimise_bb_centre(
#             self.image_interpolator,
#             self._bb_diameter,
#             self._edge_lengths,
#             self._penumbra,
#             self.field_centre,
#             self.field_rotation,
#         )

#     def _find_bb(self):
#         algorithm_map = {"pymedphys": self._find_bb_pymedphys}
#         return algorithm_map[self._algorithm]()


# def _load_lossless_image(image: PathOrNumpyArray) -> "np.ndarray":
#     if isinstance(PathOrNumpyArray, np.ndarray):
#         return image

#     image_path = cast(PathTypes, image)

#     return lljpeg.imread(image_path)


# def _centralised_straight_image(
#     image_interpolator,
#     field_centre,
#     field_rotation,
#     edge_lengths,
#     penumbra,
#     interpolated_pixel_size,
# ):
#     centralised_straight_field = utilities.create_centralised_field(
#         image_interpolator, field_centre, field_rotation
#     )

#     half_x_range = edge_lengths[0] / 2 + penumbra * 3
#     half_y_range = edge_lengths[1] / 2 + penumbra * 3

#     x_range = np.arange(
#         -half_x_range, half_x_range + interpolated_pixel_size, interpolated_pixel_size
#     )
#     y_range = np.arange(
#         -half_y_range, half_y_range + interpolated_pixel_size, interpolated_pixel_size
#     )

#     xx_range, yy_range = np.meshgrid(x_range, y_range)

#     return centralised_straight_field(xx_range, yy_range)


# def _version_key_to_version(pylinac_version_key):
#     pylinac_version = pylinac_version_key("-")[1]
#     if pylinac_version == "installed":
#         pylinac_version = pylinac.__version__

#     return pylinac_version
