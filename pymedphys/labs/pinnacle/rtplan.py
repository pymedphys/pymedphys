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
import time

from pymedphys._imports import pydicom

from .constants import (
    GImplementationClassUID,
    GTransferSyntaxUID,
    Manufacturer,
    RTPLANModality,
    RTPlanSOPClassUID,
    RTStructSOPClassUID,
)


def convert_plan(plan, export_path):

    # Check that the plan has a primary image, as we can't create a meaningful RTPLAN without it:
    if not plan.primary_image:
        plan.logger.error("No primary image found for plan. Unable to generate RTPLAN.")
        return

    # TODO Fix the RTPLAN export functionality and remove this warning
    plan.logger.warning(
        "RTPLAN export functionality is currently not validated and not stable. Use with caution."
    )

    patient_info = plan.pinnacle.patient_info
    plan_info = plan.plan_info
    trial_info = plan.trial_info
    image_info = plan.primary_image.image_info[0]
    machine_info = plan.machine_info

    patient_position = plan.patient_position

    # Get the UID for the Plan
    planInstanceUID = plan.plan_inst_uid

    # Populate required values for file meta information
    file_meta = pydicom.dataset.Dataset()
    file_meta.MediaStorageSOPClassUID = RTPlanSOPClassUID
    file_meta.TransferSyntaxUID = GTransferSyntaxUID
    file_meta.MediaStorageSOPInstanceUID = planInstanceUID
    file_meta.ImplementationClassUID = GImplementationClassUID

    # Create the pydicom.dataset.FileDataset instance (initially no data elements, but
    # file_meta supplied)
    RPfilename = f"RP.{file_meta.MediaStorageSOPInstanceUID}.dcm"
    ds = pydicom.dataset.FileDataset(
        RPfilename, {}, file_meta=file_meta, preamble=b"\x00" * 128
    )

    ds.SpecificCharacterSet = "ISO_IR 100"
    ds.InstanceCreationDate = time.strftime("%Y%m%d")
    ds.InstanceCreationTime = time.strftime("%H%M%S")

    ds.SOPClassUID = RTPlanSOPClassUID  # RT Plan Storage
    ds.SOPInstanceUID = planInstanceUID

    datetimesplit = plan_info["ObjectVersion"]["WriteTimeStamp"].split()
    datetimesplit = plan_info["ObjectVersion"]["WriteTimeStamp"].split()

    # Read more accurate date from trial file if it is available
    trial_info = plan.trial_info
    if trial_info:
        datetimesplit = trial_info["ObjectVersion"]["WriteTimeStamp"].split()

    ds.StudyDate = datetimesplit[0].replace("-", "")
    ds.StudyTime = datetimesplit[1].replace(":", "")
    ds.AccessionNumber = ""
    ds.Modality = RTPLANModality
    ds.Manufacturer = Manufacturer
    ds.OperatorsName = ""
    ds.ManufacturersModelName = plan_info["ToolType"]
    ds.SoftwareVersions = [plan_info["PinnacleVersionDescription"]]
    ds.PhysiciansOfRecord = patient_info["RadiationOncologist"]
    ds.PatientName = patient_info["FullName"]
    ds.PatientBirthDate = patient_info["DOB"]
    ds.PatientID = patient_info["MedicalRecordNumber"]
    ds.PatientSex = patient_info["Gender"][0]

    ds.StudyInstanceUID = image_info["StudyInstanceUID"]
    ds.SeriesInstanceUID = planInstanceUID
    ds.StudyID = plan.primary_image.image["StudyID"]

    ds.FrameOfReferenceUID = image_info["FrameUID"]
    ds.PositionReferenceIndicator = ""

    ds.RTPlanLabel = f"{plan.plan_info['PlanName']}.0"
    ds.RTPlanName = plan.plan_info["PlanName"]
    ds.RTPlanDescription = plan.pinnacle.patient_info["Comment"]
    ds.RTPlanDate = ds.StudyDate
    ds.RTPlanTime = ds.StudyTime

    # ds.PlanIntent = "" #Not sure where to get this informationd, will likely
    # be 'CURATIVE' or 'PALIATIVE'
    ds.RTPlanGeometry = "PATIENT"
    # Figure out what goes in DoseReferenceSequence... Should be like a target volume and
    # reference point I think...
    # ds.DoseReferenceSequence = pydicom.sequence.Sequence()
    # figure out where to get this information
    # ds.ToleranceTableSequence = pydicom.sequence.Sequence()
    ds.FractionGroupSequence = pydicom.sequence.Sequence()
    ds.BeamSequence = pydicom.sequence.Sequence()
    ds.PatientSetupSequence = pydicom.sequence.Sequence()  # need one per beam
    ds.ReferencedStructureSetSequence = pydicom.sequence.Sequence()
    ReferencedStructureSet1 = pydicom.dataset.Dataset()
    ds.ReferencedStructureSetSequence.append(ReferencedStructureSet1)
    ds.ReferencedStructureSetSequence[0].ReferencedSOPClassUID = RTStructSOPClassUID
    ds.ReferencedStructureSetSequence[0].ReferencedSOPInstanceUID = plan.struct_inst_uid
    ds.ApprovalStatus = "UNAPPROVED"  # find out where to get this information

    ds.FractionGroupSequence.append(pydicom.dataset.Dataset())
    ds.FractionGroupSequence[0].ReferencedBeamSequence = pydicom.sequence.Sequence()

    metersetweight = ["0"]

    num_fractions = 0
    beam_count = 0
    beam_list = trial_info["BeamList"] if trial_info["BeamList"] else []
    if len(beam_list) == 0:
        plan.logger.warning("No Beams found in Trial. Unable to generate RTPLAN.")
        return
    for beam in beam_list:

        beam_count = beam_count + 1

        plan.logger.info("Exporting Plan for beam: %s", beam["Name"])

        ds.PatientSetupSequence.append(pydicom.dataset.Dataset())
        ds.PatientSetupSequence[beam_count - 1].PatientPosition = patient_position
        ds.PatientSetupSequence[beam_count - 1].PatientSetupNumber = beam_count

        ds.FractionGroupSequence[0].ReferencedBeamSequence.append(
            pydicom.dataset.Dataset()
        )
        ds.FractionGroupSequence[0].ReferencedBeamSequence[
            beam_count - 1
        ].ReferencedBeamNumber = beam_count
        ds.BeamSequence.append(pydicom.dataset.Dataset())
        # figure out what to put here
        ds.BeamSequence[beam_count - 1].Manufacturer = Manufacturer
        ds.BeamSequence[beam_count - 1].BeamNumber = beam_count
        ds.BeamSequence[beam_count - 1].TreatmentDeliveryType = "TREATMENT"
        ds.BeamSequence[beam_count - 1].ReferencedPatientSetupNumber = beam_count
        ds.BeamSequence[beam_count - 1].SourceAxisDistance = "1000"
        ds.BeamSequence[beam_count - 1].FinalCumulativeMetersetWeight = "1"
        ds.BeamSequence[beam_count - 1].PrimaryDosimeterUnit = "MU"
        ds.BeamSequence[
            beam_count - 1
        ].PrimaryFluenceModeSequence = pydicom.sequence.Sequence()
        ds.BeamSequence[beam_count - 1].PrimaryFluenceModeSequence.append(
            pydicom.dataset.Dataset()
        )
        ds.BeamSequence[beam_count - 1].PrimaryFluenceModeSequence[
            0
        ].FluenceMode = "STANDARD"

        ds.BeamSequence[beam_count - 1].BeamName = beam["FieldID"]
        ds.BeamSequence[beam_count - 1].BeamDescription = beam["Name"]

        if "Photons" in beam["Modality"]:
            ds.BeamSequence[beam_count - 1].RadiationType = "PHOTON"
        elif "Electrons" in beam["Modality"]:
            ds.BeamSequence[beam_count - 1].RadiationType = "ELECTRON"
        else:
            ds.BeamSequence[beam_count - 1].RadiationType = ""

        if "STATIC" in beam["SetBeamType"].upper():
            ds.BeamSequence[beam_count - 1].BeamType = beam["SetBeamType"].upper()
        else:
            ds.BeamSequence[beam_count - 1].BeamType = "DYNAMIC"

        ds.BeamSequence[beam_count - 1].TreatmentMachineName = beam[
            "MachineNameAndVersion"
        ].partition(":")[0]

        doserefpt = None
        for point in plan.points:
            if point["Name"] == beam["PrescriptionPointName"]:
                doserefpt = plan.convert_point(point)
                plan.logger.debug("Dose reference point found: %s", point["Name"])

        if not doserefpt:
            plan.logger.debug("No dose reference point, setting to isocenter")
            doserefpt = plan.iso_center

        plan.logger.debug("Dose reference point: %s", doserefpt)

        ds.FractionGroupSequence[0].ReferencedBeamSequence[
            beam_count - 1
        ].BeamDoseSpecificationPoint = doserefpt

        ds.BeamSequence[
            beam_count - 1
        ].ControlPointSequence = pydicom.sequence.Sequence()

        cp_manager = {}
        if "CPManagerObject" in beam["CPManager"]:
            cp_manager = beam["CPManager"]["CPManagerObject"]
        else:
            cp_manager = beam["CPManager"]

        numctrlpts = cp_manager["NumberOfControlPoints"]
        currentmeterset = 0.0
        plan.logger.debug("Number of control points: %s", numctrlpts)

        x1 = ""
        x2 = ""
        y1 = ""
        y2 = ""
        leafpositions = []
        for cp in cp_manager["ControlPointList"]:

            metersetweight.append(cp["Weight"])

            if x1 == "":
                x1 = -cp["LeftJawPosition"] * 10
            if x2 == "":
                x2 = cp["RightJawPosition"] * 10
            if y2 == "":
                y2 = cp["TopJawPosition"] * 10
            if y1 == "":
                y1 = -cp["BottomJawPosition"] * 10

            points = cp["MLCLeafPositions"]["RawData"]["Points[]"].split(",")
            p_count = 0
            leafpositions1 = []
            leafpositions2 = []
            for p in points:
                leafpoint = float(p.strip())
                if p_count % 2 == 0:
                    leafpositions1.append(-leafpoint * 10)
                else:
                    leafpositions2.append(leafpoint * 10)
                p_count += 1

                if p_count == len(points):
                    leafpositions1 = list(reversed(leafpositions1))
                    leafpositions2 = list(reversed(leafpositions2))
                    leafpositions = leafpositions1 + leafpositions2

            gantryangle = cp["Gantry"]
            colangle = cp["Collimator"]
            psupportangle = cp["Couch"]
            numwedges = 0
            if (
                cp["WedgeContext"]["WedgeName"] == "No Wedge"
                or cp["WedgeContext"]["WedgeName"] == ""
            ):
                # wedgeflag = False
                plan.logger.debug("Wedge is no name")
                numwedges = 0
            elif (
                "edw" in cp["WedgeContext"]["WedgeName"]
                or "EDW" in cp["WedgeContext"]["WedgeName"]
            ):
                plan.logger.debug("Wedge present")
                wedgetype = "DYNAMIC"
                # wedgeflag = True
                numwedges = 1
                wedgeangle = cp["WedgeContext"]["Angle"]
                wedgeinorout = ""
                wedgeinorout = cp["WedgeContext"]["Orientation"]
                if wedgeinorout == "WedgeBottomToTop":
                    wedgename = (
                        f"{cp['WedgeContext']['WedgeName'].upper()}{wedgeangle}IN"
                    )
                    wedgeorientation = (
                        "0"  # temporary until I find out what to put here
                    )
                elif wedgeinorout == "WedgeTopToBottom":
                    wedgename = (
                        f"{cp['WedgeContext']['WedgeName'].upper()}{wedgeangle}OUT"
                    )
                    wedgeorientation = "180"
                plan.logger.debug("Wedge name = %s", wedgename)
            elif "UP" in cp["WedgeContext"]["WedgeName"]:
                plan.logger.debug("Wedge present")
                wedgetype = "STANDARD"
                # wedgeflag = True
                numwedges = 1
                wedgeangle = cp["WedgeContext"]["Angle"]
                wedgeinorout = ""
                wedgeinorout = cp["WedgeContext"]["Orientation"]
                if int(wedgeangle) == 15:
                    numberinname = "30"
                elif int(wedgeangle) == 45:
                    numberinname = "20"
                elif int(wedgeangle) == 30:
                    numberinname = "30"
                elif int(wedgeangle) == 60:
                    numberinname = "15"
                if wedgeinorout == "WedgeRightToLeft":
                    wedgename = f"W{int(wedgeangle)}R{numberinname}"
                    wedgeorientation = (
                        "90"  # temporary until I find out what to put here
                    )
                elif wedgeinorout == "WedgeLeftToRight":
                    wedgename = f"W{int(wedgeangle)}L{numberinname}"
                    wedgeorientation = "270"
                elif wedgeinorout == "WedgeTopToBottom":
                    wedgename = f"W{int(wedgeangle)}OUT{numberinname}"
                    wedgeorientation = (
                        "180"  # temporary until I find out what to put here
                    )
                elif wedgeinorout == "WedgeBottomToTop":
                    wedgename = f"W{int(wedgeangle)}IN{numberinname}"
                    wedgeorientation = (
                        "0"  # temporary until I find out what to put here
                    )
                plan.logger.debug("Wedge name = %s", wedgename)

        # Get the prescription for this beam
        prescription = [
            p
            for p in trial_info["PrescriptionList"]
            if p["Name"] == beam["PrescriptionName"]
        ][0]

        # Get the machine name and version and energy name for this beam
        machinenameandversion = beam["MachineNameAndVersion"].split(": ")
        machinename = machinenameandversion[0]
        machineversion = machinenameandversion[1]
        machineenergyname = beam["MachineEnergyName"]

        beam_energy = re.findall(r"[-+]?\d*\.\d+|\d+", beam["MachineEnergyName"])[0]

        # Find the DosePerMuAtCalibration parameter from the machine data
        dose_per_mu_at_cal = -1
        if (
            machine_info["Name"] == machinename
            and machine_info["VersionTimestamp"] == machineversion
        ):

            for energy in machine_info["PhotonEnergyList"]:

                if energy["Name"] == machineenergyname:
                    dose_per_mu_at_cal = energy["PhysicsData"]["OutputFactor"][
                        "DosePerMuAtCalibration"
                    ]
                    plan.logger.debug(
                        "Using DosePerMuAtCalibration of: %s", dose_per_mu_at_cal
                    )

        prescripdose = beam["MonitorUnitInfo"]["PrescriptionDose"]
        normdose = beam["MonitorUnitInfo"]["NormalizedDose"]

        if normdose == 0:
            ds.FractionGroupSequence[0].ReferencedBeamSequence[
                beam_count - 1
            ].BeamMeterset = 0
        else:
            ds.FractionGroupSequence[0].ReferencedBeamSequence[
                beam_count - 1
            ].BeamDose = (prescripdose / 100)
            ds.FractionGroupSequence[0].ReferencedBeamSequence[
                beam_count - 1
            ].BeamMeterset = prescripdose / (normdose * dose_per_mu_at_cal)

        gantryrotdir = "NONE"
        if (
            "GantryIsCCW" in cp_manager
        ):  # This may be a problem here!!!! Not sure how to Pinnacle does this, could
            # be 1 if CW, must be somewhere that states if gantry is rotating or not
            if cp_manager["GantryIsCCW"] == 1:
                gantryrotdir = "CC"
        if "GantryIsCW" in cp_manager:
            if cp_manager["GantryIsCW"] == 1:
                gantryrotdir = "CW"

        plan.logger.debug(
            "Beam MU: %s",
            ds.FractionGroupSequence[0]
            .ReferencedBeamSequence[beam_count - 1]
            .BeamMeterset,
        )

        doserate = 0
        if "DoseRate" in beam:  # TODO What to do if DoseRate isn't available in Beam?
            doserate = beam["DoseRate"]
        if (
            "STEP" in beam["SetBeamType"].upper()
            and "SHOOT" in beam["SetBeamType"].upper()
        ):
            plan.logger.debug("Using Step & Shoot")

            ds.BeamSequence[beam_count - 1].NumberOfControlPoints = numctrlpts * 2
            ds.BeamSequence[beam_count - 1].SourceToSurfaceDistance = beam["SSD"] * 10

            if numwedges > 0:
                ds.BeamSequence[
                    beam_count - 1
                ].WedgeSequence = pydicom.sequence.Sequence()
                ds.BeamSequence[beam_count - 1].WedgeSequence.append(
                    pydicom.dataset.Dataset()
                )  # I am assuming only one wedge per beam (which makes sense because you can't change it during beam)
                ds.BeamSequence[beam_count - 1].WedgeSequence[
                    0
                ].WedgeNumber = 1  # might need to change this
                ds.BeamSequence[beam_count - 1].WedgeSequence[0].WedgeType = wedgetype
                ds.BeamSequence[beam_count - 1].WedgeSequence[0].WedgeAngle = wedgeangle
                ds.BeamSequence[beam_count - 1].WedgeSequence[0].WedgeID = wedgename
                ds.BeamSequence[beam_count - 1].WedgeSequence[
                    0
                ].WedgeOrientation = wedgeorientation
                ds.BeamSequence[beam_count - 1].WedgeSequence[0].WedgeFactor = ""

            metercount = 1
            for j in range(0, numctrlpts * 2):
                ds.BeamSequence[beam_count - 1].ControlPointSequence.append(
                    pydicom.dataset.Dataset()
                )
                ds.BeamSequence[beam_count - 1].ControlPointSequence[
                    j
                ].ControlPointIndex = j
                ds.BeamSequence[beam_count - 1].ControlPointSequence[
                    j
                ].BeamLimitingDevicePositionSequence = pydicom.sequence.Sequence()
                ds.BeamSequence[beam_count - 1].ControlPointSequence[
                    j
                ].ReferencedDoseReferenceSequence = pydicom.sequence.Sequence()
                ds.BeamSequence[beam_count - 1].ControlPointSequence[
                    j
                ].ReferencedDoseReferenceSequence.append(pydicom.dataset.Dataset())
                if j % 2 == 1:  # odd number control point
                    currentmeterset = currentmeterset + float(
                        metersetweight[metercount]
                    )
                    metercount = metercount + 1

                ds.BeamSequence[beam_count - 1].ControlPointSequence[
                    j
                ].CumulativeMetersetWeight = currentmeterset
                ds.BeamSequence[beam_count - 1].ControlPointSequence[
                    j
                ].ReferencedDoseReferenceSequence[
                    0
                ].CumulativeDoseReferenceCoefficient = currentmeterset
                ds.BeamSequence[beam_count - 1].ControlPointSequence[
                    j
                ].ReferencedDoseReferenceSequence[0].ReferencedDoseReferenceNumber = "1"

                if j == 0:  # first control point beam meterset always zero
                    ds.BeamSequence[beam_count - 1].ControlPointSequence[
                        j
                    ].NominalBeamEnergy = beam_energy
                    ds.BeamSequence[beam_count - 1].ControlPointSequence[
                        j
                    ].DoseRateSet = doserate

                    ds.BeamSequence[beam_count - 1].ControlPointSequence[
                        j
                    ].GantryRotationDirection = "NONE"
                    ds.BeamSequence[beam_count - 1].ControlPointSequence[
                        j
                    ].GantryAngle = gantryangle
                    ds.BeamSequence[beam_count - 1].ControlPointSequence[
                        j
                    ].BeamLimitingDeviceAngle = colangle
                    ds.BeamSequence[beam_count - 1].ControlPointSequence[
                        j
                    ].BeamLimitingDeviceRotationDirection = "NONE"
                    ds.BeamSequence[beam_count - 1].ControlPointSequence[
                        j
                    ].SourceToSurfaceDistance = (beam["SSD"] * 10)

                    if numwedges > 0:
                        ds.BeamSequence[beam_count - 1].ControlPointSequence[
                            j
                        ].WedgePositionSequence = pydicom.sequence.Sequence()
                        ds.BeamSequence[beam_count - 1].ControlPointSequence[
                            j
                        ].WedgePositionSequence.append(pydicom.dataset.Dataset())
                        ds.BeamSequence[beam_count - 1].ControlPointSequence[
                            j
                        ].WedgePositionSequence[0].WedgePosition = "IN"
                        ds.BeamSequence[beam_count - 1].ControlPointSequence[
                            j
                        ].WedgePositionSequence[0].ReferencedWedgeNumber = "1"

                    ds.BeamSequence[beam_count - 1].ControlPointSequence[
                        j
                    ].BeamLimitingDevicePositionSequence.append(
                        pydicom.dataset.Dataset()
                    )  # This will be the x jaws
                    ds.BeamSequence[beam_count - 1].ControlPointSequence[
                        j
                    ].BeamLimitingDevicePositionSequence.append(
                        pydicom.dataset.Dataset()
                    )  # this will be the y jaws
                    ds.BeamSequence[beam_count - 1].ControlPointSequence[
                        j
                    ].BeamLimitingDevicePositionSequence[
                        0
                    ].RTBeamLimitingDeviceType = "ASYMX"
                    ds.BeamSequence[beam_count - 1].ControlPointSequence[
                        j
                    ].BeamLimitingDevicePositionSequence[0].LeafJawPositions = [x1, x2]
                    ds.BeamSequence[beam_count - 1].ControlPointSequence[
                        j
                    ].BeamLimitingDevicePositionSequence[
                        1
                    ].RTBeamLimitingDeviceType = "ASYMY"
                    ds.BeamSequence[beam_count - 1].ControlPointSequence[
                        j
                    ].BeamLimitingDevicePositionSequence[1].LeafJawPositions = [y1, y2]

                    ds.BeamSequence[beam_count - 1].ControlPointSequence[
                        j
                    ].BeamLimitingDevicePositionSequence.append(
                        pydicom.dataset.Dataset()
                    )  # this will be the MLC
                    ds.BeamSequence[beam_count - 1].ControlPointSequence[
                        j
                    ].BeamLimitingDevicePositionSequence[
                        2
                    ].RTBeamLimitingDeviceType = "MLCX"
                    ds.BeamSequence[beam_count - 1].ControlPointSequence[
                        j
                    ].BeamLimitingDevicePositionSequence[
                        2
                    ].LeafJawPositions = leafpositions
                    ds.BeamSequence[beam_count - 1].ControlPointSequence[
                        j
                    ].SourceToSurfaceDistance = (beam["SSD"] * 10)
                    ds.BeamSequence[beam_count - 1].ControlPointSequence[
                        j
                    ].BeamLimitingDeviceRotationDirection = "NONE"
                    ds.BeamSequence[beam_count - 1].ControlPointSequence[
                        j
                    ].PatientSupportAngle = psupportangle
                    ds.BeamSequence[beam_count - 1].ControlPointSequence[
                        j
                    ].PatientSupportRotationDirection = "NONE"
                    ds.BeamSequence[beam_count - 1].ControlPointSequence[
                        j
                    ].IsocenterPosition = plan.iso_center
                    ds.BeamSequence[beam_count - 1].ControlPointSequence[
                        j
                    ].GantryRotationDirection = gantryrotdir
                else:
                    ds.BeamSequence[beam_count - 1].ControlPointSequence[
                        j
                    ].BeamLimitingDevicePositionSequence.append(
                        pydicom.dataset.Dataset()
                    )  # This will be the mlcs for control points other than the first
                    ds.BeamSequence[beam_count - 1].ControlPointSequence[
                        j
                    ].BeamLimitingDevicePositionSequence[
                        0
                    ].RTBeamLimitingDeviceType = "MLCX"
                    ds.BeamSequence[beam_count - 1].ControlPointSequence[
                        j
                    ].BeamLimitingDevicePositionSequence[
                        0
                    ].LeafJawPositions = leafpositions
                ds.BeamSequence[
                    beam_count - 1
                ].NumberOfWedges = (
                    numwedges  # this is temporary value, will read in from file later
                )
                ds.BeamSequence[
                    beam_count - 1
                ].NumberOfCompensators = "0"  # Also temporary
                ds.BeamSequence[beam_count - 1].NumberOfBoli = "0"
                ds.BeamSequence[beam_count - 1].NumberOfBlocks = "0"  # Temp
                ds.BeamSequence[
                    beam_count - 1
                ].BeamLimitingDeviceSequence = pydicom.sequence.Sequence()
                ds.BeamSequence[beam_count - 1].BeamLimitingDeviceSequence.append(
                    pydicom.dataset.Dataset()
                )
                ds.BeamSequence[beam_count - 1].BeamLimitingDeviceSequence.append(
                    pydicom.dataset.Dataset()
                )
                ds.BeamSequence[beam_count - 1].BeamLimitingDeviceSequence.append(
                    pydicom.dataset.Dataset()
                )
                ds.BeamSequence[beam_count - 1].BeamLimitingDeviceSequence[
                    0
                ].RTBeamLimitingDeviceType = "ASYMX"
                ds.BeamSequence[beam_count - 1].BeamLimitingDeviceSequence[
                    1
                ].RTBeamLimitingDeviceType = "ASYMY"
                ds.BeamSequence[beam_count - 1].BeamLimitingDeviceSequence[
                    2
                ].RTBeamLimitingDeviceType = "MLCX"
                ds.BeamSequence[beam_count - 1].BeamLimitingDeviceSequence[
                    0
                ].NumberOfLeafJawPairs = "1"
                ds.BeamSequence[beam_count - 1].BeamLimitingDeviceSequence[
                    1
                ].NumberOfLeafJawPairs = "1"
                ds.BeamSequence[beam_count - 1].BeamLimitingDeviceSequence[
                    2
                ].NumberOfLeafJawPairs = (p_count / 2)
                bounds = [
                    "-200",
                    "-190",
                    "-180",
                    "-170",
                    "-160",
                    "-150",
                    "-140",
                    "-130",
                    "-120",
                    "-110",
                    "-100",
                    "-95",
                    "-90",
                    "-85",
                    "-80",
                    "-75",
                    "-70",
                    "-65",
                    "-60",
                    "-55",
                    "-50",
                    "-45",
                    "-40",
                    "-35",
                    "-30",
                    "-25",
                    "-20",
                    "-15",
                    "-10",
                    "-5",
                    "0",
                    "5",
                    "10",
                    "15",
                    "20",
                    "25",
                    "30",
                    "35",
                    "40",
                    "45",
                    "50",
                    "55",
                    "60",
                    "65",
                    "70",
                    "75",
                    "80",
                    "85",
                    "90",
                    "95",
                    "100",
                    "110",
                    "120",
                    "130",
                    "140",
                    "150",
                    "160",
                    "170",
                    "180",
                    "190",
                    "200",
                ]
                ds.BeamSequence[beam_count - 1].BeamLimitingDeviceSequence[
                    2
                ].LeafPositionBoundaries = bounds
        else:
            plan.logger.debug("Not using Step & Shoot")
            ds.BeamSequence[beam_count - 1].NumberOfControlPoints = numctrlpts + 1
            ds.BeamSequence[beam_count - 1].SourceToSurfaceDistance = beam["SSD"] * 10
            if numwedges > 0:
                ds.BeamSequence[
                    beam_count - 1
                ].WedgeSequence = pydicom.sequence.Sequence()
                ds.BeamSequence[beam_count - 1].WedgeSequence.append(
                    pydicom.dataset.Dataset()
                )
                # I am assuming only one wedge per beam (which makes sense
                # because you can't change it during beam)
                ds.BeamSequence[beam_count - 1].WedgeSequence[0].WedgeNumber = 1
                # might need to change this
                ds.BeamSequence[beam_count - 1].WedgeSequence[0].WedgeType = wedgetype
                ds.BeamSequence[beam_count - 1].WedgeSequence[0].WedgeAngle = wedgeangle
                ds.BeamSequence[beam_count - 1].WedgeSequence[0].WedgeID = wedgename
                ds.BeamSequence[beam_count - 1].WedgeSequence[
                    0
                ].WedgeOrientation = wedgeorientation
                ds.BeamSequence[beam_count - 1].WedgeSequence[0].WedgeFactor = ""
            for j in range(0, numctrlpts + 1):
                ds.BeamSequence[beam_count - 1].ControlPointSequence.append(
                    pydicom.dataset.Dataset()
                )
                ds.BeamSequence[beam_count - 1].ControlPointSequence[
                    j
                ].ControlPointIndex = j
                ds.BeamSequence[beam_count - 1].ControlPointSequence[
                    j
                ].BeamLimitingDevicePositionSequence = pydicom.sequence.Sequence()
                ds.BeamSequence[beam_count - 1].ControlPointSequence[
                    j
                ].ReferencedDoseReferenceSequence = pydicom.sequence.Sequence()
                ds.BeamSequence[beam_count - 1].ControlPointSequence[
                    j
                ].ReferencedDoseReferenceSequence.append(pydicom.dataset.Dataset())
                ds.BeamSequence[beam_count - 1].ControlPointSequence[
                    j
                ].CumulativeMetersetWeight = metersetweight[j]
                if j == 0:  # first control point beam meterset always zero
                    ds.BeamSequence[beam_count - 1].ControlPointSequence[
                        j
                    ].NominalBeamEnergy = beam_energy
                    ds.BeamSequence[beam_count - 1].ControlPointSequence[
                        j
                    ].DoseRateSet = doserate

                    ds.BeamSequence[beam_count - 1].ControlPointSequence[
                        j
                    ].GantryRotationDirection = "NONE"
                    ds.BeamSequence[beam_count - 1].ControlPointSequence[
                        j
                    ].GantryAngle = gantryangle
                    ds.BeamSequence[beam_count - 1].ControlPointSequence[
                        j
                    ].BeamLimitingDeviceAngle = colangle
                    ds.BeamSequence[beam_count - 1].ControlPointSequence[
                        j
                    ].SourceToSurfaceDistance = (beam["SSD"] * 10)
                    ds.BeamSequence[beam_count - 1].ControlPointSequence[
                        j
                    ].ReferencedDoseReferenceSequence[
                        0
                    ].CumulativeDoseReferenceCoefficient = "0"
                    ds.BeamSequence[beam_count - 1].ControlPointSequence[
                        j
                    ].ReferencedDoseReferenceSequence[
                        0
                    ].ReferencedDoseReferenceNumber = "1"
                    if numwedges > 0:
                        WedgePosition1 = pydicom.dataset.Dataset()
                        ds.BeamSequence[beam_count - 1].ControlPointSequence[
                            j
                        ].WedgePositionSequence = pydicom.sequence.Sequence()
                        ds.BeamSequence[beam_count - 1].ControlPointSequence[
                            j
                        ].WedgePositionSequence.append(WedgePosition1)
                        ds.BeamSequence[beam_count - 1].ControlPointSequence[
                            j
                        ].WedgePositionSequence[0].WedgePosition = "IN"
                        ds.BeamSequence[beam_count - 1].ControlPointSequence[
                            j
                        ].WedgePositionSequence[0].ReferencedWedgeNumber = "1"
                    ds.BeamSequence[beam_count - 1].ControlPointSequence[
                        j
                    ].BeamLimitingDevicePositionSequence.append(
                        pydicom.dataset.Dataset()
                    )  # This will be the x jaws
                    ds.BeamSequence[beam_count - 1].ControlPointSequence[
                        j
                    ].BeamLimitingDevicePositionSequence.append(
                        pydicom.dataset.Dataset()
                    )  # this will be the y jaws
                    ds.BeamSequence[beam_count - 1].ControlPointSequence[
                        j
                    ].BeamLimitingDevicePositionSequence[
                        0
                    ].RTBeamLimitingDeviceType = "ASYMX"
                    ds.BeamSequence[beam_count - 1].ControlPointSequence[
                        j
                    ].BeamLimitingDevicePositionSequence[0].LeafJawPositions = [x1, x2]
                    ds.BeamSequence[beam_count - 1].ControlPointSequence[
                        j
                    ].BeamLimitingDevicePositionSequence[
                        1
                    ].RTBeamLimitingDeviceType = "ASYMY"
                    ds.BeamSequence[beam_count - 1].ControlPointSequence[
                        j
                    ].BeamLimitingDevicePositionSequence[1].LeafJawPositions = [y1, y2]
                    ds.BeamSequence[beam_count - 1].ControlPointSequence[
                        j
                    ].BeamLimitingDevicePositionSequence.append(
                        pydicom.dataset.Dataset()
                    )  # this will be the MLC
                    ds.BeamSequence[beam_count - 1].ControlPointSequence[
                        j
                    ].BeamLimitingDevicePositionSequence[
                        2
                    ].RTBeamLimitingDeviceType = "MLCX"
                    ds.BeamSequence[beam_count - 1].ControlPointSequence[
                        j
                    ].BeamLimitingDevicePositionSequence[
                        2
                    ].LeafJawPositions = leafpositions
                    ds.BeamSequence[beam_count - 1].ControlPointSequence[
                        j
                    ].SourceToSurfaceDistance = (beam["SSD"] * 10)
                    ds.BeamSequence[beam_count - 1].ControlPointSequence[
                        j
                    ].BeamLimitingDeviceRotationDirection = "NONE"
                    ds.BeamSequence[beam_count - 1].ControlPointSequence[
                        j
                    ].PatientSupportAngle = psupportangle
                    ds.BeamSequence[beam_count - 1].ControlPointSequence[
                        j
                    ].PatientSupportRotationDirection = "NONE"
                    ds.BeamSequence[beam_count - 1].ControlPointSequence[
                        j
                    ].IsocenterPosition = plan.iso_center
                    ds.BeamSequence[beam_count - 1].ControlPointSequence[
                        j
                    ].GantryRotationDirection = gantryrotdir
                    ds.BeamSequence[beam_count - 1].NumberOfWedges = numwedges

                    ds.BeamSequence[
                        beam_count - 1
                    ].NumberOfCompensators = (
                        "0"  # this is temporary value, will read in from file later
                    )
                    ds.BeamSequence[beam_count - 1].NumberOfBoli = "0"  # Also temporary
                    ds.BeamSequence[beam_count - 1].NumberOfBlocks = "0"  # Temp
                else:
                    # This will be the mlcs for control points other than the first
                    ds.BeamSequence[beam_count - 1].ControlPointSequence[
                        j
                    ].BeamLimitingDevicePositionSequence.append(
                        pydicom.dataset.Dataset()
                    )
                    ds.BeamSequence[beam_count - 1].ControlPointSequence[
                        j
                    ].BeamLimitingDevicePositionSequence[
                        0
                    ].RTBeamLimitingDeviceType = "MLCX"
                    ds.BeamSequence[beam_count - 1].ControlPointSequence[
                        j
                    ].BeamLimitingDevicePositionSequence[
                        0
                    ].LeafJawPositions = leafpositions
                    ds.BeamSequence[beam_count - 1].ControlPointSequence[
                        j
                    ].ReferencedDoseReferenceSequence[
                        0
                    ].CumulativeDoseReferenceCoefficient = "1"
                    ds.BeamSequence[beam_count - 1].ControlPointSequence[
                        j
                    ].ReferencedDoseReferenceSequence[
                        0
                    ].ReferencedDoseReferenceNumber = "1"

                ds.BeamSequence[
                    beam_count - 1
                ].BeamLimitingDeviceSequence = pydicom.sequence.Sequence()
                ds.BeamSequence[beam_count - 1].BeamLimitingDeviceSequence.append(
                    pydicom.dataset.Dataset()
                )
                ds.BeamSequence[beam_count - 1].BeamLimitingDeviceSequence.append(
                    pydicom.dataset.Dataset()
                )
                ds.BeamSequence[beam_count - 1].BeamLimitingDeviceSequence.append(
                    pydicom.dataset.Dataset()
                )
                ds.BeamSequence[beam_count - 1].BeamLimitingDeviceSequence[
                    0
                ].RTBeamLimitingDeviceType = "ASYMX"
                ds.BeamSequence[beam_count - 1].BeamLimitingDeviceSequence[
                    1
                ].RTBeamLimitingDeviceType = "ASYMY"
                ds.BeamSequence[beam_count - 1].BeamLimitingDeviceSequence[
                    2
                ].RTBeamLimitingDeviceType = "MLCX"
                ds.BeamSequence[beam_count - 1].BeamLimitingDeviceSequence[
                    0
                ].NumberOfLeafJawPairs = "1"
                ds.BeamSequence[beam_count - 1].BeamLimitingDeviceSequence[
                    1
                ].NumberOfLeafJawPairs = "1"
                ds.BeamSequence[beam_count - 1].BeamLimitingDeviceSequence[
                    2
                ].NumberOfLeafJawPairs = (p_count / 2)
                bounds = [
                    "-200",
                    "-190",
                    "-180",
                    "-170",
                    "-160",
                    "-150",
                    "-140",
                    "-130",
                    "-120",
                    "-110",
                    "-100",
                    "-95",
                    "-90",
                    "-85",
                    "-80",
                    "-75",
                    "-70",
                    "-65",
                    "-60",
                    "-55",
                    "-50",
                    "-45",
                    "-40",
                    "-35",
                    "-30",
                    "-25",
                    "-20",
                    "-15",
                    "-10",
                    "-5",
                    "0",
                    "5",
                    "10",
                    "15",
                    "20",
                    "25",
                    "30",
                    "35",
                    "40",
                    "45",
                    "50",
                    "55",
                    "60",
                    "65",
                    "70",
                    "75",
                    "80",
                    "85",
                    "90",
                    "95",
                    "100",
                    "110",
                    "120",
                    "130",
                    "140",
                    "150",
                    "160",
                    "170",
                    "180",
                    "190",
                    "200",
                ]
                ds.BeamSequence[beam_count - 1].BeamLimitingDeviceSequence[
                    2
                ].LeafPositionBoundaries = bounds
            numwedges = 0

        # Get the prescription for this beam
        prescription = [
            p
            for p in trial_info["PrescriptionList"]
            if p["Name"] == beam["PrescriptionName"]
        ][0]
        num_fractions = prescription["NumberOfFractions"]

    ds.FractionGroupSequence[0].FractionGroupNumber = 1
    ds.FractionGroupSequence[0].NumberOfFractionsPlanned = num_fractions
    ds.FractionGroupSequence[0].NumberOfBeams = beam_count
    ds.FractionGroupSequence[0].NumberOfBrachyApplicationSetups = "0"

    # Save the RTPlan Dicom File
    output_file = os.path.join(export_path, RPfilename)
    plan.logger.info("Creating Plan file: %s", output_file)
    ds.save_as(output_file)
