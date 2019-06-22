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
