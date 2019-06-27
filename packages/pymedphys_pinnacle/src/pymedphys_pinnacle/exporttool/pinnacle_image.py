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
import sys
import logging

from .pinn_yaml import pinn_to_dict

# This class holds all information relating to the Pinnacle Image


class PinnacleImage:

    logger = None  # Logger to use for all logging

    path = ""  # Path to the root directory of the image (contains ImageInfo)
    pinnacle = None  # Reference to main Pinnacle dataset object
    image = None  # The image details found in the Patient file
    image_info = None  # Data from ImageInfo
    image_header = None  # Data from .header file
    image_set = None  # Data from .ImageSet file

    def __init__(self, pinnacle, path, image):
        self.pinnacle = pinnacle
        self.path = path
        self.image = image
        self.logger = pinnacle.logger

    def get_image_info(self):

        if not self.image_info:
            path_image_info = os.path.join(
                self.path, "ImageSet_"+str(self.image['ImageSetID'])+".ImageInfo")
            self.logger.debug('Reading image data from: ' + path_image_info)
            self.image_info = pinn_to_dict(path_image_info)

        return self.image_info

    def get_image_header(self):

        if not self.image_header:
            path_image_header = os.path.join(
                self.path, "ImageSet_"+str(self.image['ImageSetID'])+".header")
            self.logger.debug('Reading image data from: ' + path_image_header)
            self.image_header = {}
            with open(path_image_header, "rt") as f2:
                for line in f2:
                    parts = line.split(" = ")

                    if len(parts) < 2:
                        parts = line.split(" : ")

                    if len(parts) > 1:
                        self.image_header[parts[0].strip()] = parts[1].replace(
                            ';', '').replace('\n', '')

        return self.image_header

    def get_image_set(self):

        if not self.image_set:
            path_image_set = os.path.join(
                self.path, "ImageSet_"+str(self.image['ImageSetID'])+".ImageSet")
            self.logger.debug('Reading image data from: ' + path_image_set)
            self.image_set = pinn_to_dict(path_image_set)

            parts = self.image_set['ScanTimeFromScanner'].split(' ')
            self.image_set['scan_date'] = parts[0].replace('-', '')
            self.image_set['scan_time'] = parts[1].replace(':', '')

        return self.image_set
