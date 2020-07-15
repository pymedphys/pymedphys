# Copyright (C) 2019 South Western Sydney Local Health District,
# University of New South Wales

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# This work is derived from:
# https://github.com/AndrewWAlexander/Pinnacle-tar-DICOM
# which is released under the following license:

# Copyright (c) [2017] [Colleen Henschel, Andrew Alexander]

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.


import os

from .pinn_yaml import pinn_to_dict


class PinnacleImage:
    """Represents an image within the Pinnacle data.

    This class manages the data specific to an image within a Pinnacle dataset.

    Parameters
    ----------
        pinnacle : PinnacleExport
            PinnacleExport object representing the dataset.
        path : str
            Path to raw Pinnacle data (directoy containing 'Patient' file).
        image : dict
            Image info dict from 'Patient' file.
    """

    def __init__(self, pinnacle, path, image):

        self._pinnacle = pinnacle
        self._path = path
        self._image = image

        self._image_info = None  # Data from ImageInfo
        self._image_header = None  # Data from .header file
        self._image_set = None  # Data from .ImageSet file

    @property
    def logger(self):
        """Gets the configured logger.

        Returns
        -------
        logger : Logger
            Logger configured.
        """
        return self._pinnacle.logger

    @property
    def pinnacle(self):
        """Gets the PinnacleExport object.

        Returns
        -------
        pinnacle : PinnacleExport
            PinnacleExport object for this dataset.
        """
        return self._pinnacle

    @property
    def path(self):
        """Gets the path of the Pinnacle data.

        Returns
        -------
        path : str
            Path containing the Pinnacle data.
        """
        return self._path

    @property
    def image(self):
        """Gets the image information from the 'Patient' file.

        Returns
        -------
        image : dict
            Image info as found in the Pinnacle 'Patient' file.
        """
        return self._image

    @property
    def image_info(self):
        """Gets the image information from the '.ImageInfo' file.

        Returns
        -------
        image_info : dict
            Image info as found in the Pinnacle '.ImageInfo' file.
        """

        if not self._image_info:
            path_image_info = os.path.join(
                self._path, f"ImageSet_{self._image['ImageSetID']}.ImageInfo"
            )

            # Make sure the ImageInfo file really exists
            if not os.path.exists(path_image_info):
                self.logger.warning("ImageInfo path doesn't exist: %s", path_image_info)
                return None

            self.logger.debug("Reading image data from: %s", path_image_info)
            self._image_info = pinn_to_dict(path_image_info)

        return self._image_info

    @property
    def image_header(self):
        """Gets the image header from the '.header' file.

        Returns
        -------
        image_header : dict
            Image info as found in the Pinnacle '.header' file.
        """

        if not self._image_header:
            path_image_header = os.path.join(
                self._path, f"ImageSet_{self._image['ImageSetID']}.header"
            )

            # Make sure the ImageInfo file really exists
            if not os.path.exists(path_image_header):
                self.logger.warning(
                    "ImageHeader path doesn't exist: %s", path_image_header
                )
                return None

            self.logger.debug("Reading image data from: %s", path_image_header)
            self._image_header = {}
            with open(path_image_header, "rt") as f:
                for line in f:
                    parts = line.split(" = ")

                    if len(parts) < 2:
                        parts = line.split(" : ")

                    if len(parts) > 1:
                        self._image_header[parts[0].strip()] = (
                            parts[1].replace(";", "").replace("\n", "")
                        )

        return self._image_header

    @property
    def image_set(self):
        """Gets the image set from the '.ImageSet' file.

        Returns
        -------
        image_set : dict
            Image set as found in the Pinnacle '.ImageSet' file.
        """

        if not self._image_set:
            path_image_set = os.path.join(
                self._path, f"ImageSet_{self._image['ImageSetID']}.ImageSet"
            )

            # Make sure the ImageInfo file really exists
            if not os.path.exists(path_image_set):
                self.logger.warning("ImageSet path doesn't exist: %s", path_image_set)
                return None

            self.logger.debug("Reading image data from: %s", path_image_set)
            self._image_set = pinn_to_dict(path_image_set)

            parts = self._image_set["ScanTimeFromScanner"].split(" ")
            self._image_set["scan_date"] = parts[0].replace("-", "")
            self._image_set["scan_time"] = parts[1].replace(":", "")

        return self._image_set
