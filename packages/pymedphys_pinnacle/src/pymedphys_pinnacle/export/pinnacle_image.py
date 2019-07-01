# Copyright (C) 2019 South Western Sydney Local Health District,
# University of New South Wales

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

# This class holds all information relating to the Pinnacle Image


class PinnacleImage:

    def __init__(self, pinnacle, path, image):

        self._pinnacle = pinnacle
        self._path = path
        self._image = image

        self._image_info = None  # Data from ImageInfo
        self._image_header = None  # Data from .header file
        self._image_set = None  # Data from .ImageSet file

    @property
    def logger(self):
        return self._pinnacle.logger

    @property
    def pinnacle(self):
        return self._pinnacle

    @property
    def path(self):
        return self._path

    @property
    def image(self):
        return self._image

    @property
    def image_info(self):

        if not self._image_info:
            path_image_info = os.path.join(
                self._path, "ImageSet_"+str(self._image['ImageSetID'])+".ImageInfo")
            self.logger.debug('Reading image data from: ' + path_image_info)
            self._image_info = pinn_to_dict(path_image_info)

        return self._image_info

    @property
    def image_header(self):

        if not self._image_header:
            path_image_header = os.path.join(
                self._path, "ImageSet_"+str(self._image['ImageSetID'])+".header")
            self.logger.debug('Reading image data from: ' + path_image_header)
            self._image_header = {}
            with open(path_image_header, "rt") as f:
                for line in f:
                    parts = line.split(" = ")

                    if len(parts) < 2:
                        parts = line.split(" : ")

                    if len(parts) > 1:
                        self._image_header[parts[0].strip()] = parts[1].replace(
                            ';', '').replace('\n', '')

        return self._image_header

    @property
    def image_set(self):

        if not self._image_set:
            path_image_set = os.path.join(
                self._path, "ImageSet_"+str(self._image['ImageSetID'])+".ImageSet")
            self.logger.debug('Reading image data from: ' + path_image_set)
            self._image_set = pinn_to_dict(path_image_set)

            parts = self._image_set['ScanTimeFromScanner'].split(' ')
            self._image_set['scan_date'] = parts[0].replace('-', '')
            self._image_set['scan_time'] = parts[1].replace(':', '')

        return self._image_set
