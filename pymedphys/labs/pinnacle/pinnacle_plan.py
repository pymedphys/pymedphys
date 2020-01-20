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
import re

from pymedphys._imports import pydicom

from .pinn_yaml import pinn_to_dict
from .rtstruct import find_iso_center

# Medical Connections offers free valid UIDs
# (http://www.medicalconnections.co.uk/FreeUID.html)
# Their service was used to obtain the following root UID for this tool:
UID_PREFIX = "1.2.826.0.1.3680043.10.202."


class PinnaclePlan:
    """Represents a plan within the Pinnacle data.

    This class manages the data specific to a plan within a Pinnacle dataset.

    Parameters
    ----------
        pinnacle : PinnacleExport
            PinnacleExport object representing the dataset.
        path : str
            Path to raw Pinnacle data (directoy containing 'Patient' file).
        plan : dict
            Plan info dict from 'Patient' file.
    """

    def __init__(self, pinnacle, path, plan):
        self._pinnacle = pinnacle
        self._path = path
        self._plan_info = plan

        self._machine_info = None  # Data of the machines used for this plan
        self._trials = None  # Data found in plan.Trial
        self._trial_info = None  # 'Active' trial for this plan
        self._points = None  # Data found in plan.Points
        self._patient_setup = None  # Data found in PatientSetup file
        self._primary_image = None  # Primary image for this plan
        self._uid_prefix = UID_PREFIX  # The prefix for UIDs generated

        self._roi_count = 0  # Store the total number of ROIs
        self._iso_center = []  # Store the iso center of this plan
        self._ct_center = []  # Store the ct center of the primary image of this plan
        self._dose_ref_pt = []  # Store the dose ref point of this plan

        self._plan_inst_uid = None  # UID for RTPlan instance
        self._dose_inst_uid = None  # UID for RTDose instance
        self._struct_inst_uid = None  # UID for RTStruct instance

        for image in pinnacle.images:
            if image.image["ImageSetID"] == self.plan_info["PrimaryCTImageSetID"]:
                self._primary_image = image

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
    def primary_image(self):
        """Gets the primary image for this plan.

        Returns
        -------
        primary_image : PinnacleImage
            PinnacleImage representing the primary image for this plan.
        """
        return self._primary_image

    @property
    def machine_info(self):
        """Gets the machine info for this plan.

        Returns
        -------
        machine_info : dict
            Machine info read from 'plan.Pinnacle.Machines' file.
        """

        if not self._machine_info:
            path_machine = os.path.join(self._path, "plan.Pinnacle.Machines")
            self.logger.debug("Reading machine data from: %s", path_machine)
            self._machine_info = pinn_to_dict(path_machine)

        return self._machine_info

    @property
    def trials(self):
        """Gets the trials within this plan.

        Returns
        -------
        trials : list
            List of all trials found within this plan.
        """

        if not self._trials:
            path_trial = os.path.join(self._path, "plan.Trial")
            self.logger.debug("Reading trial data from: %s", path_trial)
            self._trials = pinn_to_dict(path_trial)
            if isinstance(self._trials, dict):
                self._trials = [self._trials["Trial"]]

            # Select the first trial by default
            if not self._trial_info:
                self._trial_info = self._trials[0]

            self.logger.debug("Number of trials read: %s", len(self._trials))
            self.logger.debug("Active Trial: %s", self._trial_info["Name"])

        return self._trials

    @property
    def active_trial(self):
        """Get and set the active trial for this plan.

        When DICOM objects are exported, data from the active trial is
        used to generate the output.
        """

        return self._trial_info

    @active_trial.setter
    def active_trial(self, trial_name):

        if isinstance(trial_name, str):
            for trial in self._trials:
                if trial["Name"] == trial_name:
                    self._trial_info = trial
                    self.logger.info("Active Trial set: %s", trial_name)
                    return True

        return False

    @property
    def plan_info(self):
        """Gets the plan information for this plan.

        Returns
        -------
        plan_info : dict
            Plan info as found in the Pinnacle 'Patient' file.
        """
        return self._plan_info

    @property
    def trial_info(self):
        """Gets the trial information of the active trial.

        Returns
        -------
        trial_info : dict
            Trial info from the 'plan.Trial' file.
        """

        if not self._trial_info:
            # Ensures that the trials are read and a default
            # trial_info is set
            self.trials  # pylint: disable=pointless-statement

        return self._trial_info

    @property
    def points(self):
        """Gets the points defined within the plan.

        Returns
        -------
        points : list
            List of points read from the 'plan.Points' file.
        """

        if not self._points:
            path_points = os.path.join(self._path, "plan.Points")
            self.logger.debug("Reading points data from: %s", path_points)
            self._points = pinn_to_dict(path_points)

            if isinstance(self._points, dict):
                self._points = [self._points["Poi"]]

            if self._points is None:
                self._points = []

        return self._points

    @property
    def patient_position(self):
        """Gets the patient position

        Returns
        -------
        patient_position : str
            The patient position for this plan.
        """

        if not self._patient_setup:
            self._patient_setup = pinn_to_dict(
                os.path.join(self._path, "plan.PatientSetup")
            )

        pat_pos = ""

        if "Head First" in self._patient_setup["Orientation"]:
            pat_pos = "HF"
        elif "Feet First" in self._patient_setup["Orientation"]:
            pat_pos = "FF"

        if "supine" in self._patient_setup["Position"]:
            pat_pos = f"{pat_pos}S"
        elif "prone" in self._patient_setup["Position"]:
            pat_pos = f"{pat_pos}P"
        elif (
            "decubitus right" in self._patient_setup["Position"]
            or "Decuibitus Right" in self._patient_setup["Position"]
        ):
            pat_pos = f"{pat_pos}DR"
        elif (
            "decubitus left" in self._patient_setup["Position"]
            or "Decuibitus Left" in self._patient_setup["Position"]
        ):
            pat_pos = f"{pat_pos}DL"

        return pat_pos

    @property
    def iso_center(self):
        """Gets and sets the iso center for this plan.
        """

        if len(self._iso_center) == 0:
            find_iso_center(self)

        return self._iso_center

    @iso_center.setter
    def iso_center(self, iso_center):
        self._iso_center = iso_center

    @staticmethod
    def is_prefix_valid(prefix):
        """Check if a UID prefix is valid.

        Parameters
        ----------
            prefix :  str
                The UID prefix to check.

        Returns:
            True if valid, False otherwise.
        """

        if re.match(pydicom.uid.RE_VALID_UID_PREFIX, prefix):
            return True

        return False

    def generate_uids(self, uid_type="HASH"):
        """Generates UIDs to be used for exporting this plan.

        Parameters
        ----------
            uid_type : str, optional
                If 'HASH', the entropy will be generated
                to hash to consistant UIDs. If not then random UIDs will be
                generated. Default: 'HASH'
        """

        entropy_srcs = None
        if uid_type == "HASH":
            entropy_srcs = []
            entropy_srcs.append(self._pinnacle.patient_info["MedicalRecordNumber"])
            entropy_srcs.append(self.plan_info["PlanName"])
            entropy_srcs.append(self.trial_info["Name"])
            entropy_srcs.append(self.trial_info["ObjectVersion"]["WriteTimeStamp"])

        RTPLAN_prefix = f"{self._uid_prefix}1."
        self._plan_inst_uid = pydicom.uid.generate_uid(
            prefix=RTPLAN_prefix, entropy_srcs=entropy_srcs
        )
        RTDOSE_prefix = f"{self._uid_prefix}2."
        self._dose_inst_uid = pydicom.uid.generate_uid(
            prefix=RTDOSE_prefix, entropy_srcs=entropy_srcs
        )
        RTSTRUCT_prefix = f"{self._uid_prefix}3."
        self._struct_inst_uid = pydicom.uid.generate_uid(
            prefix=RTSTRUCT_prefix, entropy_srcs=entropy_srcs
        )

        self.logger.debug(f"Plan Instance UID: {self._plan_inst_uid}")
        self.logger.debug(f"Dose Instance UID: {self._dose_inst_uid}")
        self.logger.debug(f"Struct Instance UID: {self._struct_inst_uid}")

    @property
    def plan_inst_uid(self):
        """Gets the instance UID for RTPLAN.

        Returns
        -------
        uid : str
            The UID to use for the plan.
        """

        if not self._plan_inst_uid:
            self.generate_uids()

        return self._plan_inst_uid

    @property
    def dose_inst_uid(self):
        """Gets the instance UID for RTDOSE.

        Returns
        -------
        uid : str
            The UID to use for the dose.
        """

        if not self._dose_inst_uid:
            self.generate_uids()

        return self._dose_inst_uid

    @property
    def struct_inst_uid(self):
        """Gets the instance UID for RTSTRUCT.

        Returns
        -------
        uid : str
            The UID to use for the struct.
        """

        if not self._struct_inst_uid:
            self.generate_uids()

        return self._struct_inst_uid

    # Convert the point from the pinnacle plan format to dicom
    def convert_point(self, point):
        """Convert a point from Pinnacle coordinates to DICOM coordinates.

        Parameters
        ----------
            point : list
                The point to convert.

        Returns
        -------
            The converted point.

        """

        image_header = self.primary_image.image_header

        refpoint = [point["XCoord"] * 10, point["YCoord"] * 10, point["ZCoord"] * 10]
        if (
            image_header["patient_position"] == "HFP"
            or image_header["patient_position"] == "FFS"
        ):
            refpoint[0] = -refpoint[0]
        if (
            image_header["patient_position"] == "HFS"
            or image_header["patient_position"] == "FFS"
        ):
            refpoint[1] = -(refpoint[1])
        if (
            image_header["patient_position"] == "HFS"
            or image_header["patient_position"] == "HFP"
        ):
            refpoint[2] = -(refpoint[2])

        point["refpoint"] = refpoint

        refpoint[0] = round(refpoint[0], 5)
        refpoint[1] = round(refpoint[1], 5)
        refpoint[2] = round(refpoint[2], 5)

        return refpoint
