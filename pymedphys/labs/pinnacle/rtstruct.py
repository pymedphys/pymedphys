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
# The following needs to be removed before leaving labs
# pylint: skip-file

import os
import random
import re
import time

import pydicom
import pydicom.uid
from pydicom.dataset import Dataset, FileDataset
from pydicom.sequence import Sequence

from .constants import *


# Determine which point to use for the iso center and set this value in
# the plan object
def find_iso_center(plan):

    iso_center = []
    ct_center = []
    dose_ref_pt = []

    for point in plan.points:

        refpoint = plan.convert_point(point)

        if (
            "Iso" in point["Name"]
            or "isocenter" in point["Name"]
            or "isocentre" in point["Name"]
            or "ISO" in point["Name"]
        ):
            iso_center = refpoint
        if (
            "CT Center" in point["Name"]
            or "ct center" in point["Name"]
            or "ct centre" in point["Name"]
        ):
            ct_center = refpoint
        if "drp" in point["Name"] or "DRP" in point["Name"]:
            dose_ref_pt = refpoint

        if "PoiInterpretedType" in point.keys():
            if "ISO" in point["PoiInterpretedType"]:  # This point is Iso CenterAtZero
                iso_center = refpoint
                plan.logger.debug("ISO Center located: " + str(iso_center))

    if len(iso_center) < 2:
        iso_center = ct_center
        plan.logger.debug(
            "Isocenter not located, setting to ct center: " + str(iso_center)
        )

    if len(iso_center) < 2:
        plan.logger.debug(
            "Isocenter still not located, setting to point with center in name, if not, with iso in name"
        )
        temp_point1 = []
        temp_point2 = []

        for p in plan.points:
            if "center" in p["Name"]:
                temp_point1 = p["refpoint"]
            elif "iso" in p["Name"]:
                temp_point2 = p["refpoint"]

        if len(temp_point1) > 1:
            iso_center = temp_point1
        elif len(temp_point2) > 1:
            iso_center = temp_point2
        else:
            if len(plan.points) > 0:
                # setting to first point if isocenter or ct center not found
                iso_center = plan.points[0]["refpoint"]

    plan.iso_center = iso_center
    plan.ct_center = ct_center
    plan.dose_ref_pt = dose_ref_pt

    plan.logger.debug("Isocenter: " + str(iso_center))


# Read points and insert them into the dicom dataset
def read_points(ds, plan):

    plan.roi_count = 0

    for point in plan.points:

        plan.roi_count = plan.roi_count + 1

        refpoint = plan.convert_point(point)

        roi_contour = Dataset()
        roi_contour.ReferencedROINumber = str(plan.roi_count)
        roi_contour.ROIDisplayColor = colors[point["Color"]]
        roi_contour.ContourSequence = Sequence()
        contour = Dataset()
        contour.ContourData = refpoint
        contour.ContourGeometricType = "POINT"
        contour.NumberOfContourPoints = 1
        contour.ContourImageSequence = Sequence()

        contour_image = Dataset()

        closestvalue = abs(
            float(plan.primary_image.image_info[0]["TablePosition"])
            - float(refpoint[-1])
        )
        for s in plan.primary_image.image_info:
            if (
                abs(float(s["TablePosition"]) - (-float(refpoint[-1] / 10)))
                <= closestvalue
            ):
                closestvalue = abs(
                    float(s["TablePosition"]) - (-float(refpoint[-1] / 10))
                )
                contour_image.ReferencedSOPClassUID = "1.2.840.10008.5.1.4.1.1.2"
                contour_image.ReferencedSOPInstanceUID = s["InstanceUID"]

        contour.ContourImageSequence.append(contour_image)

        roi_contour.ContourSequence.append(contour)
        ds.ROIContourSequence.append(roi_contour)

        structure_set_roi = Dataset()
        structure_set_roi.ROINumber = plan.roi_count
        structure_set_roi.ROIName = point["Name"]
        plan.logger.info("Exporting point: " + point["Name"])

        # Not sure what this is for, just basing off template, should look into further
        structure_set_roi.ROIGenerationAlgorithm = "SEMIAUTOMATIC"
        structure_set_roi.ReferencedFrameOfReferenceUID = plan.primary_image.image_info[
            0
        ]["FrameUID"]

        ds.StructureSetROISequence.append(structure_set_roi)

        rt_roi_observations = Dataset()
        rt_roi_observations.ObservationNumber = plan.roi_count
        rt_roi_observations.ReferencedROINumber = plan.roi_count
        rt_roi_observations.RTROIInterpretedType = "MARKER"
        rt_roi_observations.ROIInterpreter = ""
        ds.RTROIObservationsSequence.append(rt_roi_observations)

    # Not applying any shifts of points at the moment. Needed for Pinnacle pre v9.0
    # for enteredpoints in ds.ROIContourSequence:
    #     #logger.debug("In loop applying shifts: isocenter:" + str(data["isocenter"]) )
    #     enteredpoints.ContourSequence[0].ContourData[0] = str(float(enteredpoints.ContourSequence[0].ContourData[0]) - data["xshift"])
    #     enteredpoints.ContourSequence[0].ContourData[1] = str(float(enteredpoints.ContourSequence[0].ContourData[1]) - data["yshift"])
    #     #enteredpoints.ContourSequence[0].ContourData[2] = str(float(enteredpoints.ContourSequence[0].ContourData[2]) - float(data["isocenter"][2]))
    #     #logger.debug("bottom of loop applying shifts isocenter:" + str(data["isocenter"]))

    return ds


# This function reads the plan.roi file line by line. This file is somehow not structured like the others,
# and isn't tab indented properly, so won't parse onto YAML.
def read_roi(ds, plan):

    image_header = plan.primary_image.image_header

    path_roi = os.path.join(plan.path, "plan.roi")

    points = []
    flag_points = (
        False
    )  # bool value to tell me if I want to read the line in as point values
    prevroi = plan.roi_count
    plan.logger.debug("Reading ROI from: " + path_roi)
    first_points = []
    with open(path_roi, "rt") as f:
        for num, line in enumerate(f, 1):
            if (
                "};  // End of points for curve" in line
            ):  # this will tell me not to read in point values
                # all points for current curve saved until now. Here is where I
                # need to add them to dicom file
                numfind = int(line.find("curve") + 5)
                line = line[numfind : len(line)]
                line = line.strip()
                curvenum = int(line)

                ds.ROIContourSequence[plan.roi_count - 1].ContourSequence[
                    int(curvenum) - 1
                ].NumberOfContourPoints = int(len(points) / 3)

                ds.ROIContourSequence[plan.roi_count - 1].ContourSequence[
                    curvenum - 1
                ].ContourData = points
                ds.ROIContourSequence[plan.roi_count - 1].ContourSequence[
                    int(curvenum) - 1
                ].ContourImageSequence = Sequence()
                contour_image = Dataset()

                closestvalue = abs(
                    float(plan.primary_image.image_info[0]["TablePosition"])
                    - float(points[-1])
                )
                for s in plan.primary_image.image_info:
                    if (
                        abs(float(s["TablePosition"]) - (-float(points[-1] / 10)))
                        <= closestvalue
                    ):
                        closestvalue = abs(
                            float(s["TablePosition"]) - (-float(points[-1] / 10))
                        )
                        contour_image.ReferencedSOPClassUID = (
                            "1.2.840.10008.5.1.4.1.1.2"
                        )
                        contour_image.ReferencedSOPInstanceUID = s["InstanceUID"]

                ds.ROIContourSequence[plan.roi_count - 1].ContourSequence[
                    int(curvenum) - 1
                ].ContourImageSequence.append(contour_image)

                del points[:]
                flag_points = False
            if flag_points:
                curr_points = line.split(" ")

                if curr_points == first_points:
                    # These points are the exact same as the first point, skip it!
                    continue

                if len(first_points) == 0:
                    first_points = curr_points

                if image_header["patient_position"] == "HFS":
                    curr_points = [
                        float(curr_points[0]) * 10,
                        -float(curr_points[1]) * 10,
                        -float(curr_points[2]) * 10,
                    ]
                elif image_header["patient_position"] == "HFP":
                    curr_points = [
                        -float(curr_points[0]) * 10,
                        float(curr_points[1]) * 10,
                        -float(curr_points[2]) * 10,
                    ]
                elif image_header["patient_position"] == "FFP":
                    curr_points = [
                        float(curr_points[0]) * 10,
                        float(curr_points[1]) * 10,
                        float(curr_points[2]) * 10,
                    ]
                elif image_header["patient_position"] == "FFS":
                    curr_points = [
                        -float(curr_points[0]) * 10,
                        -float(curr_points[1]) * 10,
                        float(curr_points[2]) * 10,
                    ]

                if len(points) == 3:
                    points[0] = round(points[0], 5)
                    points[1] = round(points[1], 5)
                    points[2] = round(points[2], 5)

                points = points + curr_points
            if "Beginning of ROI" in line:  # Start of ROI
                plan.roi_count = (
                    plan.roi_count + 1
                )  # increment ROI_num because I've found a new ROI
                roi_contour = Dataset()
                roi_contour.ReferencedROINumber = str(plan.roi_count)
                ds.ROIContourSequence.append(roi_contour)
                structure_set_roi = Dataset()
                ds.StructureSetROISequence.append(roi_contour)
                rt_roi_observations = Dataset()
                ds.RTROIObservationsSequence.append(rt_roi_observations)
                ds.StructureSetROISequence[
                    plan.roi_count - 1
                ].ROINumber = plan.roi_count
                ROIName = line[22:]  # gets a string of ROI name
                ROIName = ROIName.replace("\n", "")
                ds.StructureSetROISequence[plan.roi_count - 1].ROIName = ROIName
                ds.StructureSetROISequence[
                    plan.roi_count - 1
                ].ROIGenerationAlgorithm = "SEMIAUTOMATIC"
                ds.StructureSetROISequence[
                    plan.roi_count - 1
                ].ReferencedFrameOfReferenceUID = plan.primary_image.image_info[0][
                    "FrameUID"
                ]
                ds.ROIContourSequence[plan.roi_count - 1].ContourSequence = Sequence()
                roiinterpretedtype = "ORGAN"
                plan.logger.info("Exporting ROI: " + ROIName)
            if "roiinterpretedtype:" in line:
                roiinterpretedtype = line.split(" ")[-1].replace("\n", "")
            if "color:" in line:
                roi_color = line.split(" ")[-1].replace("\n", "")

                try:
                    ds.ROIContourSequence[plan.roi_count - 1].ROIDisplayColor = colors[
                        roi_color
                    ]
                except KeyError:
                    plan.logger.info("ROI Color not known: " + roi_color)
                    new_color = random.choice(list(colors))
                    plan.logger.info("Instead, assigning color: " + new_color)
                    ds.ROIContourSequence[plan.roi_count - 1].ROIDisplayColor = colors[
                        new_color
                    ]

            if "}; // End of ROI" in line:  # end of ROI found
                ds.RTROIObservationsSequence[
                    plan.roi_count - 1
                ].ObservationNumber = plan.roi_count
                ds.RTROIObservationsSequence[
                    plan.roi_count - 1
                ].ReferencedROINumber = plan.roi_count
                ds.RTROIObservationsSequence[
                    plan.roi_count - 1
                ].RTROIInterpretedType = roiinterpretedtype
                ds.RTROIObservationsSequence[plan.roi_count - 1].ROIInterpreter = ""
                # add to ROI observation sequence
            if "volume =" in line:
                vol = re.findall(r"[-+]?\d*\.\d+|\d+", line)[0]
                ds.StructureSetROISequence[plan.roi_count - 1].ROIVolume = vol
            if "//  Curve " in line:  # found a curve
                first_points = []
                curvenum = re.findall(r"[-+]?\d*\.\d+|\d+", line)[0]
                contour = Dataset()
                ds.ROIContourSequence[plan.roi_count - 1].ContourSequence.append(
                    contour
                )
            if "num_points =" in line:
                npts = re.findall(r"[-+]?\d*\.\d+|\d+", line)[0]
                ds.ROIContourSequence[plan.roi_count - 1].ContourSequence[
                    int(curvenum) - 1
                ].ContourGeometricType = "CLOSED_PLANAR"
                ds.ROIContourSequence[plan.roi_count - 1].ContourSequence[
                    int(curvenum) - 1
                ].NumberOfContourPoints = npts
            if "points=" in line:
                flag_points = True

    plan.logger.debug("patient pos:" + image_header["patient_position"])

    return ds


def convert_struct(plan, export_path):

    # Check that the plan has a primary image, as we can't create a meaningful RTSTRUCT without it:
    if not plan.primary_image:
        plan.logger.error(
            "No primary image found for plan. Unable to generate RTSTRUCT."
        )
        return

    patient_info = plan.pinnacle.patient_info

    struct_sop_instuid = plan.struct_inst_uid

    # Populate required values for file meta information
    file_meta = Dataset()
    file_meta.MediaStorageSOPClassUID = RTStructSOPClassUID
    file_meta.TransferSyntaxUID = GTransferSyntaxUID
    file_meta.MediaStorageSOPInstanceUID = struct_sop_instuid
    file_meta.ImplementationClassUID = GImplementationClassUID

    struct_filename = "RS." + struct_sop_instuid + ".dcm"

    ds = FileDataset(struct_filename, {}, file_meta=file_meta, preamble=b"\x00" * 128)
    ds = FileDataset(struct_filename, {}, file_meta=file_meta, preamble=b"\x00" * 128)

    struct_series_instuid = pydicom.uid.generate_uid()
    ds.ReferencedStudySequence = Sequence()

    # not sure what I want here, going off of template dicom file
    ds.SpecificCharacterSet = "ISO_IR 100"
    ds.InstanceCreationDate = time.strftime("%Y%m%d")
    ds.InstanceCreationTime = time.strftime("%H%M%S")
    ds.SOPClassUID = RTStructSOPClassUID
    ds.SOPInstanceUID = struct_sop_instuid
    ds.Modality = RTSTRUCTModality
    ds.AccessionNumber = ""
    ds.Manufacturer = Manufacturer  # from sample dicom file, maybe should change?
    # not sure where to get information for this element can find this and
    # read in from
    ds.StationName = "adacp3u7"
    # ds.ManufacturersModelName = 'Pinnacle3'
    ReferencedStudy1 = Dataset()
    ds.ReferencedStudySequence.append(ReferencedStudy1)
    # Study Component Management SOP Class (chosen from template)
    ds.ReferencedStudySequence[0].ReferencedSOPClassUID = "1.2.840.10008.3.1.2.3.2"
    ds.ReferencedStudySequence[
        0
    ].ReferencedSOPInstanceUID = plan.primary_image.image_info[0]["StudyInstanceUID"]
    ds.StudyInstanceUID = plan.primary_image.image_info[0]["StudyInstanceUID"]
    ds.SeriesInstanceUID = struct_series_instuid

    ds.PatientID = patient_info["MedicalRecordNumber"]
    ds.ReferringPhysiciansName = patient_info["ReferringPhysician"]
    ds.PhysiciansOfRecord = patient_info["RadiationOncologist"]
    ds.StudyDescription = patient_info["Comment"]
    ds.PatientSex = patient_info["Gender"][0]
    ds.PatientBirthDate = patient_info["DOB"]
    ds.StructureSetLabel = plan.plan_info["PlanName"]
    ds.StudyID = plan.primary_image.image["StudyID"]

    datetimesplit = plan.plan_info["ObjectVersion"]["WriteTimeStamp"].split()
    # Read more accurate date from trial file if it is available
    trial_info = plan.trial_info
    if trial_info:
        datetimesplit = trial_info["ObjectVersion"]["WriteTimeStamp"].split()

    study_date = datetimesplit[0].replace("-", "")
    study_time = datetimesplit[1].replace(":", "")

    ds.StructureSetDate = study_date
    ds.StructureSetTime = study_time
    ds.StudyDate = study_date
    ds.StudyTime = study_time
    ds.ManufacturersModelName = plan.plan_info["ToolType"]
    ds.SoftwareVersions = plan.plan_info["PinnacleVersionDescription"]
    ds.StructureSetName = "POIandROI"
    ds.SeriesNumber = "1"
    ds.PatientName = patient_info["FullName"]

    ds.ReferencedFrameOfReferenceSequence = Sequence()
    ReferencedFrameofReference = Dataset()
    ds.ReferencedFrameOfReferenceSequence.append(ReferencedFrameofReference)
    ds.ReferencedFrameOfReferenceSequence[
        0
    ].FrameOfReferenceUID = plan.primary_image.image_info[0]["FrameUID"]
    ds.ReferencedFrameOfReferenceSequence[0].RTReferencedStudySequence = Sequence()

    RTReferencedStudy = Dataset()
    ds.ReferencedFrameOfReferenceSequence[0].RTReferencedStudySequence.append(
        RTReferencedStudy
    )
    ds.ReferencedFrameOfReferenceSequence[0].RTReferencedStudySequence[
        0
    ].ReferencedSOPClassUID = "1.2.840.10008.3.1.2.3.2"
    ds.ReferencedFrameOfReferenceSequence[0].RTReferencedStudySequence[
        0
    ].ReferencedSOPInstanceUID = plan.primary_image.image_info[0]["StudyInstanceUID"]
    ds.StudyInstanceUID = plan.primary_image.image_info[0]["StudyInstanceUID"]
    ds.ReferencedFrameOfReferenceSequence[0].RTReferencedStudySequence[
        0
    ].RTReferencedSeriesSequence = Sequence()

    RTReferencedSeries = Dataset()
    ds.ReferencedFrameOfReferenceSequence[0].RTReferencedStudySequence[
        0
    ].RTReferencedSeriesSequence.append(RTReferencedSeries)
    ds.ReferencedFrameOfReferenceSequence[0].RTReferencedStudySequence[
        0
    ].RTReferencedSeriesSequence[0].SeriesInstanceUID = plan.primary_image.image_info[
        0
    ][
        "SeriesUID"
    ]
    ds.ReferencedFrameOfReferenceSequence[0].RTReferencedStudySequence[
        0
    ].RTReferencedSeriesSequence[0].ContourImageSequence = Sequence()

    for info in plan.primary_image.image_info:
        contour_image = Dataset()
        contour_image.ReferencedSOPClassUID = "1.2.840.10008.5.1.4.1.1.2"
        contour_image.ReferencedSOPInstanceUID = info["InstanceUID"]
        ds.ReferencedFrameOfReferenceSequence[0].RTReferencedStudySequence[
            0
        ].RTReferencedSeriesSequence[0].ContourImageSequence.append(contour_image)

    ds.ROIContourSequence = Sequence()
    ds.StructureSetROISequence = Sequence()
    ds.RTROIObservationsSequence = Sequence()

    # Determine ISO Center
    find_iso_center(plan)

    ds = read_points(ds, plan)
    ds = read_roi(ds, plan)

    # find out where to get if its been approved or not
    # find out how to insert proper 'CodeString' here
    ds.ApprovalStatus = "UNAPPROVED"
    # Set the transfer syntax

    ds.is_little_endian = True
    ds.is_implicit_VR = True

    # Save the RTDose Dicom File
    output_file = os.path.join(export_path, struct_filename)
    plan.logger.info("Creating Struct file: %s \n" % (output_file))
    ds.save_as(output_file)
