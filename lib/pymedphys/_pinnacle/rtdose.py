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


import math
import os
import re
import struct
import time

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom

from pymedphys._dicom.orientation import IMAGE_ORIENTATION_MAP

from .constants import (
    GImplementationClassUID,
    GTransferSyntaxUID,
    Manufacturer,
    RTDOSEModality,
    RTDoseSOPClassUID,
    RTPlanSOPClassUID,
)


def trilinear_interpolation(idx, grid):
    """
    Return trilinear interpolated value for a voxel with index idx within the grid
    """

    int_idx = [math.floor(f) for f in idx]
    frac_idx = [f % 1 for f in idx]

    l1 = [[[0 for x in range(2)] for x in range(2)] for x in range(2)]
    for x in range(0, 2):
        for y in range(0, 2):
            for z in range(0, 2):
                l1[x][y][z] = grid[int_idx[0] + x, int_idx[1] + y, int_idx[2] + z]

    l2 = [[0 for x in range(2)] for x in range(2)]
    for y in range(0, 2):
        for z in range(0, 2):
            l2[y][z] = l1[0][y][z] * (1 - frac_idx[0]) + l1[1][y][z] * frac_idx[0]

    l3 = [0 for x in range(2)]
    for z in range(0, 2):
        l3[z] = l2[0][z] * (1 - frac_idx[1]) + l2[1][z] * frac_idx[1]

    return l3[0] * (1 - frac_idx[2]) + l3[1] * frac_idx[2]


def convert_dose(plan, export_path):

    # Check that the plan has a primary image, as we can't create a meaningful RTDOSE without it:
    if not plan.primary_image:
        plan.logger.error("No primary image found for plan. Unable to generate RTDOSE.")
        return

    supported_orientations = ("HFS", "HFP", "FFS", "FFP")

    patient_info = plan.pinnacle.patient_info
    plan_info = plan.plan_info
    trial_info = plan.trial_info
    image_info = plan.primary_image.image_info[0]

    patient_position = plan.patient_position

    if not patient_position in supported_orientations:
        raise NotImplementedError(
            f"{patient_position} orientation not supported. Only: "
            f"{supported_orientations}"
        )

    # Get the UID for the Dose and the Plan
    doseInstanceUID = plan.dose_inst_uid
    planInstanceUID = plan.plan_inst_uid

    # Populate required values for file meta information
    file_meta = pydicom.dataset.Dataset()
    file_meta.MediaStorageSOPClassUID = RTDoseSOPClassUID
    file_meta.TransferSyntaxUID = GTransferSyntaxUID
    file_meta.MediaStorageSOPInstanceUID = doseInstanceUID
    file_meta.ImplementationClassUID = GImplementationClassUID

    # Create the pydicom.dataset.FileDataset instance (initially no data elements, but
    # file_meta supplied)
    RDfilename = f"RD.{file_meta.MediaStorageSOPInstanceUID}.dcm"
    ds = pydicom.dataset.FileDataset(
        RDfilename, {}, file_meta=file_meta, preamble=b"\x00" * 128
    )
    ds.SpecificCharacterSet = "ISO_IR 100"
    ds.InstanceCreationDate = time.strftime("%Y%m%d")
    ds.InstanceCreationTime = time.strftime("%H%M%S")

    ds.SOPClassUID = RTDoseSOPClassUID  # RT Dose Storage
    ds.SOPInstanceUID = doseInstanceUID
    datetimesplit = plan_info["ObjectVersion"]["WriteTimeStamp"].split()
    # Read more accurate date from trial file if it is available
    trial_info = plan.trial_info
    if trial_info:
        datetimesplit = trial_info["ObjectVersion"]["WriteTimeStamp"].split()

    ds.StudyDate = datetimesplit[0].replace("-", "")
    ds.StudyTime = datetimesplit[1].replace(":", "")
    ds.AccessionNumber = ""
    ds.Modality = RTDOSEModality
    ds.Manufacturer = Manufacturer
    ds.OperatorsName = ""
    ds.ManufacturerModelName = plan_info["ToolType"]
    ds.SoftwareVersions = [plan_info["PinnacleVersionDescription"]]
    ds.PhysiciansOfRecord = patient_info["RadiationOncologist"]
    ds.PatientName = patient_info["FullName"]
    ds.PatientBirthDate = patient_info["DOB"]
    ds.PatientID = patient_info["MedicalRecordNumber"]
    ds.PatientSex = patient_info["Gender"][0]

    ds.SliceThickness = trial_info["DoseGrid .VoxelSize .Z"] * 10
    ds.SeriesInstanceUID = doseInstanceUID
    ds.InstanceNumber = "1"

    ds.StudyInstanceUID = image_info["StudyInstanceUID"]
    ds.FrameOfReferenceUID = image_info["FrameUID"]
    ds.StudyID = plan.primary_image.image["StudyID"]

    # Assume zero struct shift for now (may not the case for versions below Pinnacle 9)
    if patient_position in ("HFP", "FFS"):
        dose_origin_x = -trial_info["DoseGrid .Origin .X"] * 10
    elif patient_position in ("HFS", "FFP"):
        dose_origin_x = trial_info["DoseGrid .Origin .X"] * 10

    if patient_position in ("HFS", "FFS"):
        dose_origin_y = -trial_info["DoseGrid .Origin .Y"] * 10
    elif patient_position in ("HFP", "FFP"):
        dose_origin_y = trial_info["DoseGrid .Origin .Y"] * 10

    if patient_position in ("HFS", "HFP"):
        dose_origin_z = -trial_info["DoseGrid .Origin .Z"] * 10
    elif patient_position in ("FFS", "FFP"):
        dose_origin_z = trial_info["DoseGrid .Origin .Z"] * 10

    # Image Position (Patient) seems off, so going to calculate shift assuming
    # dose origin in center and I want outer edge
    ydoseshift = (
        trial_info["DoseGrid .VoxelSize .Y"] * 10 * trial_info["DoseGrid .Dimension .Y"]
        - trial_info["DoseGrid .VoxelSize .Y"] * 10
    )
    zdoseshift = (
        trial_info["DoseGrid .VoxelSize .Z"] * 10 * trial_info["DoseGrid .Dimension .Z"]
        - trial_info["DoseGrid .VoxelSize .Z"] * 10
    )

    if patient_position == "HFS":
        ds.ImagePositionPatient = [
            dose_origin_x,
            dose_origin_y - ydoseshift,
            dose_origin_z - zdoseshift,
        ]
    elif patient_position == "HFP":
        ds.ImagePositionPatient = [
            dose_origin_x,
            dose_origin_y + ydoseshift,
            dose_origin_z - zdoseshift,
        ]
    elif patient_position == "FFS":
        ds.ImagePositionPatient = [
            dose_origin_x,
            dose_origin_y - ydoseshift,
            dose_origin_z + zdoseshift,
        ]
    elif patient_position == "FFP":
        ds.ImagePositionPatient = [
            dose_origin_x,
            dose_origin_y + ydoseshift,
            dose_origin_z + zdoseshift,
        ]

    # Read this from CT DCM if available?
    ds.ImageOrientationPatient = IMAGE_ORIENTATION_MAP[patient_position]

    # Read this from CT DCM if available
    ds.PositionReferenceIndicator = ""
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"

    ds.NumberOfFrames = int(
        trial_info["DoseGrid .Dimension .Z"]
    )  # is this Z dimension???
    # Using y for Rows because that's what's in the exported dicom file for
    # test patient
    ds.Rows = int(trial_info["DoseGrid .Dimension .Y"])
    ds.Columns = int(trial_info["DoseGrid .Dimension .X"])
    ds.PixelSpacing = [
        trial_info["DoseGrid .VoxelSize .X"] * 10,
        trial_info["DoseGrid .VoxelSize .Y"] * 10,
    ]
    ds.BitsAllocated = 16
    ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 0
    ds.DoseUnits = "GY"
    ds.DoseType = "PHYSICAL"
    ds.DoseSummationType = "PLAN"

    # Since DoseSummationType is PLAN, only need to reference RTPLAN here, no need to
    # reference fraction group.
    ds.ReferencedRTPlanSequence = pydicom.sequence.Sequence()
    ds.ReferencedRTPlanSequence.append(pydicom.dataset.Dataset())
    ds.ReferencedRTPlanSequence[0].ReferencedSOPClassUID = RTPlanSOPClassUID
    ds.ReferencedRTPlanSequence[0].ReferencedSOPInstanceUID = planInstanceUID

    ds.TissueHeterogeneityCorrection = "IMAGE"

    grid_frame_offset_vector = []
    for p in range(0, int(trial_info["DoseGrid .Dimension .Z"])):
        grid_frame_offset_vector.append(
            p * float(trial_info["DoseGrid .VoxelSize .X"] * 10)
        )
    ds.GridFrameOffsetVector = grid_frame_offset_vector

    # Array in which to sum the dose values of all beams
    summed_pixel_values = []

    # For each beam in the trial, convert the dose from the Pinnacle binary
    # file and sum together
    beam_list = trial_info["BeamList"] if trial_info["BeamList"] else []
    if len(beam_list) == 0:
        plan.logger.warning("No Beams found in Trial. Unable to generate RTDOSE.")
        return

    for beam in beam_list:

        plan.logger.info("Exporting Dose for beam: %s", beam["Name"])

        # Get the binary file for this beam
        binary_id = re.findall("\\d+", beam["DoseVolume"])[0]
        filled_binary_id = str(binary_id).zfill(3)
        binary_file = os.path.join(plan.path, f"plan.Trial.binary.{filled_binary_id}")

        # Get the prescription for this beam (need this for number of fractions)
        prescription = [
            p
            for p in trial_info["PrescriptionList"]
            if p["Name"] == beam["PrescriptionName"]
        ][0]

        # Get the prescription point
        plan.logger.debug("PrescriptionPointName: %s", beam["PrescriptionPointName"])
        points = plan.points
        prescription_point = []
        for p in points:
            if p["Name"] == beam["PrescriptionPointName"]:
                plan.logger.debug(
                    "Presc Point: %s %s %s %s",
                    p["Name"],
                    p["XCoord"],
                    p["YCoord"],
                    p["ZCoord"],
                )
                prescription_point = plan.convert_point(p)
                break

        if len(prescription_point) < 3:
            plan.logger.warning(
                "No valid prescription point found for beam! Beam will be ignored for "
                "Dose conversion. Dose will most likely be incorrect"
            )
            continue

        plan.logger.debug("Presc Point Dicom: %s, %s", p["Name"], prescription_point)
        total_prescription = (
            beam["MonitorUnitInfo"]["PrescriptionDose"]
            * prescription["NumberOfFractions"]
        )
        plan.logger.debug("Total Prescription %s", total_prescription)

        # Read the dose into a grid, so that we can interpolate for the prescription
        # point and determine the MU for the grid
        dose_grid = np.zeros(
            (
                trial_info["DoseGrid .Dimension .X"],
                trial_info["DoseGrid .Dimension .Y"],
                trial_info["DoseGrid .Dimension .Z"],
            )
        )
        spacing = [
            trial_info["DoseGrid .VoxelSize .X"] * 10,
            trial_info["DoseGrid .VoxelSize .Y"] * 10,
            trial_info["DoseGrid .VoxelSize .Z"] * 10,
        ]
        origin = [
            ds.ImagePositionPatient[0],
            ds.ImagePositionPatient[1],
            ds.ImagePositionPatient[2],
        ]

        if os.path.isfile(binary_file):
            with open(binary_file, "rb") as b:
                for z in range(trial_info["DoseGrid .Dimension .Z"] - 1, -1, -1):
                    for y in range(0, trial_info["DoseGrid .Dimension .Y"]):
                        for x in range(0, trial_info["DoseGrid .Dimension .X"]):
                            data_element = b.read(4)
                            value = struct.unpack(">f", data_element)[0]
                            dose_grid[x, y, z] = value
        else:
            plan.logger.warning("Dose file not found")
            plan.logger.error("Skipping generating RTDOSE")
            return

        # Get the index within that grid of the dose reference point
        idx = [0.0, 0.0, 0.0]
        orientation_matrix = np.zeros((3, 3))
        orientation_matrix[0, :] = IMAGE_ORIENTATION_MAP[patient_position][:3]
        orientation_matrix[1, :] = IMAGE_ORIENTATION_MAP[patient_position][3:]
        orientation_matrix[2, :] = np.cross(
            orientation_matrix[0, :], orientation_matrix[1, :]
        )

        for i in range(3):
            idx[i] = -(origin[i] - prescription_point[i]) / spacing[i]
            idx[i] *= orientation_matrix[i, i]

        plan.logger.debug("Index of prescription point within grid: %s", idx)

        # Trilinear interpolation of that point within the dose grid
        cgy_mu = trilinear_interpolation(idx, dose_grid)
        plan.logger.debug("cgy_mu: %s", cgy_mu)

        # Now that we have the cgy/mu value of the dose reference point, we can
        # extract an accurate value for MU
        beam_mu = (total_prescription / cgy_mu) / prescription["NumberOfFractions"]
        plan.logger.debug("Beam MU: %s", beam_mu)

        pixel_data_list = []
        for z in range(trial_info["DoseGrid .Dimension .Z"] - 1, -1, -1):
            for y in range(0, trial_info["DoseGrid .Dimension .Y"]):
                for x in range(0, trial_info["DoseGrid .Dimension .X"]):
                    value = (
                        float(prescription["NumberOfFractions"])
                        * dose_grid[x, y, z]
                        * beam_mu
                        / 100
                    )
                    pixel_data_list.append(value)

        ds.FrameIncrementPointer = ds.data_element("GridFrameOffsetVector").tag

        main_pix_array = []
        for h in range(0, trial_info["DoseGrid .Dimension .Z"]):
            pixelsforframe = []
            for k in range(
                0,
                trial_info["DoseGrid .Dimension .X"]
                * trial_info["DoseGrid .Dimension .Y"],
            ):

                pixelsforframe.append(
                    float(
                        pixel_data_list[
                            h
                            * trial_info["DoseGrid .Dimension .Y"]
                            * trial_info["DoseGrid .Dimension .X"]
                            + k
                        ]
                    )
                )

            main_pix_array = main_pix_array + list(reversed(pixelsforframe))

        main_pix_array = list(reversed(main_pix_array))

        # Add the values from this beam to the summed values
        if len(summed_pixel_values) == 0:
            summed_pixel_values = main_pix_array
        else:
            for i, values in enumerate(summed_pixel_values):
                summed_pixel_values[i] = values + main_pix_array[i]

    # Compute the scaling factor
    scale = max(summed_pixel_values) / 16384
    ds.DoseGridScaling = scale
    plan.logger.debug("Dose Grid Scaling: %s", ds.DoseGridScaling)

    # Scale by the scaling factor
    pixelvaluelist = []
    for _, element in enumerate(summed_pixel_values, 0):

        if scale != 0:
            element = round(element / scale)
        else:
            element = 0
        pixelvaluelist.append(int(element))

    # Set the PixelData
    pixel_binary_block = struct.pack("%sh" % len(pixelvaluelist), *pixelvaluelist)
    ds.PixelData = pixel_binary_block

    # If Feet first, flip the dose grid
    if patient_position in ("FFS", "FFP"):
        arr = ds.pixel_array
        ds.PixelData = np.flip(arr, axis=0).tostring()

    # Save the RTDose Dicom File
    output_file = os.path.join(export_path, RDfilename)
    plan.logger.info("Creating Dose file: %s", output_file)
    ds.save_as(output_file)
