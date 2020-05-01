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


import logging
import os
import sys

from .image import convert_image
from .pinn_yaml import pinn_to_dict
from .pinnacle_image import PinnacleImage
from .pinnacle_plan import PinnaclePlan
from .rtdose import convert_dose
from .rtplan import convert_plan
from .rtstruct import convert_struct


class PinnacleExport:
    """Handle Pinnacle data to allow export of DICOM objects

    This class is used to export the various DICOM objects from Pinnacle
    data found within the given path.

    Parameters
    ----------
        path : str
            Path to raw Pinnacle data (directory containing 'Patient' file).
        logger : Logger
            Logger the tool will log to.
    """

    def __init__(self, path, logger=None):

        self._logger = logger  # Logger to use for all logging

        self._path = path  # Path to the root directory of the dataset
        # (containing the Patient file)

        self._patient_info = None  # The patient data read from
        self._plans = None  # Pinnacle plans for this path
        self._images = None  # Images found in image.info

        if not self._logger:
            self._logger = logging.getLogger(__name__)
            self._logger.setLevel(logging.DEBUG)

            if len(self._logger.handlers) == 0:
                ch = logging.StreamHandler(sys.stdout)
                formatter = logging.Formatter(
                    "%(asctime)s - %(levelname)s - %(message)s"
                )
                ch.setFormatter(formatter)
                ch.setLevel(logging.DEBUG)

                self._logger.addHandler(ch)

    @property
    def logger(self):
        """Gets the configured logger.

        Returns
        -------
        logger : Logger
            Logger configured.
        """
        return self._logger

    @property
    def patient_info(self):
        """Gets the patient info.

        Returns
        -------
        patient_info : dict
            Dictionary object containing the data found in the 'Patient'
            file within the raw Pinnacle data.
        """

        if not self._patient_info:
            path_patient = os.path.join(self._path, "Patient")
            self.logger.debug("Reading patient data from: %s", path_patient)
            self._patient_info = pinn_to_dict(path_patient)

            # Set the full patient name
            last_name = self._patient_info["LastName"]
            first_name = self._patient_info["FirstName"]
            middle_name = self._patient_info["MiddleName"]
            self._patient_info["FullName"] = f"{last_name}^{first_name}^{middle_name}^"

            # gets birthday string with numbers and dashes
            dobstr = self._patient_info["DateOfBirth"]
            if "-" in dobstr:
                dob_list = dobstr.split("-")
            elif "/" in dobstr:
                dob_list = dobstr.split("/")
            else:
                dob_list = dobstr.split(" ")

            dob = ""
            for num in dob_list:
                if len(num) == 1:
                    num = f"0{num}"
                dob = f"{dob}{num}"

            self._patient_info["DOB"] = dob

        return self._patient_info

    @property
    def plans(self):
        """Get the plans available.

        Returns
        -------
        plans : list
            List of PinnaclePlan's available within the Pinnacle raw data in the path
            configured.
        """

        # Read patient info to populate patients plans
        if not self._plans:

            self._plans = []
            for plan in self.patient_info["PlanList"]:
                path_plan = os.path.join(self._path, f"Plan_{plan['PlanID']}")
                self._plans.append(PinnaclePlan(self, path_plan, plan))

        return self._plans

    @property
    def images(self):
        """Get the images available.

        Returns
        -------
        images : list
            List of PinnacleImage's available within the Pinnacle raw data in the path
            configured.
        """

        # Read patient info to populate patients images
        if not self._images:
            self._images = []
            for image in self.patient_info["ImageSetList"]:
                pi = PinnacleImage(self, self._path, image)
                self._images.append(pi)

        return self._images

    @staticmethod
    def export_struct(plan, export_path="."):
        """Exports the RTSTRUCT DICOM modality.

        Parameters
        ----------
            plan : PinnaclePlan
                The plan for which structures should be exported.
            export_path : str, optional
                The file system path where the DICOM object should be
                exported to.
        """

        # Export Structures for plan
        convert_struct(plan, export_path)

    @staticmethod
    def export_dose(plan, export_path="."):
        """Exports the RTDOSE DICOM modality.

        Parameters
        ----------
            plan : PinnaclePlan
                The plan for which dose should be exported.
            export_path : str, optional
                The file system path where the DICOM object should be
                exported to.
        """

        # Export dose for plan
        convert_dose(plan, export_path)

    @staticmethod
    def export_plan(plan, export_path="."):
        """Exports the RTPLAN DICOM modality.

        Parameters
        ----------
            plan : PinnaclePlan
                The plan for which dose should be exported.
            export_path : str, optional
                The file system path where the DICOM object should be
                exported to.
        """

        # Export rtplan for plan
        convert_plan(plan, export_path)

    def export_image(self, image=None, series_uid="", export_path="."):
        """Exports an image from the Pinnacle data.

        Parameters
        ----------
            image : PinnacleImage, optional
                The image to export.
            series_uid : str, optional
                The SeriesInstanceUID of the image to export.
            export_path : str, optional
                The file system path where the DICOM objects should be
                exported to.
        """

        for im in self.images:
            im_info = im.image_info[0]
            im_suid = im_info["SeriesUID"]
            if len(series_uid) > 0 and im_suid == series_uid:
                convert_image(im, export_path)
                break

        if image:
            convert_image(image, export_path)

    def log_images(self):
        """Outputs all images found in the Pinnacle data to the log.
        """

        for i in self.images:
            image_header = i.image_header
            self.logger.info(
                "%s: %s %s",
                image_header["modality"],
                image_header["series_UID"],
                image_header["SeriesDateTime"],
            )

    def log_plan_names(self):
        """Outputs all plans found in the Pinnacle data to the log.
        """

        for p in self.plans:
            self.logger.info(p.plan_info["PlanName"])

    def log_trial_names(self):
        """Outputs all trials found in the Pinnacle data to the log.
        """

        for p in self.plans:
            self.logger.info("### %s ###", p.plan_info["PlanName"])
            for t in p.trials:
                self.logger.info("- %s", t["Name"])

    def log_trial_names_in_plan(self, plan):
        """Outputs all trials found within a plan to the log.

        Parameters
        ----------
            plan : PinnaclePlan
                The plan for which to log the trials.
        """

        self.logger.info("### %s ###", plan.plan_info["PlanName"])
        self.logger.info(plan.path)
        for trial in plan.trials:
            self.logger.info("- %s", trial["Name"])
