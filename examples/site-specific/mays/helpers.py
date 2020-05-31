# Copyright (C) 2018 Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""Some helper utility functions for accessing DICOM RT Plan info.
"""

import pandas as pd

import pydicom

import tolerance_constants


def get_all_dicom_treatment_info(dicomFile):
    dicom = pydicom.dcmread(dicomFile)
    dicomBeam = []
    dicomData = []
    prescriptionDescription = dicom.PrescriptionDescription.split("\\")
    for fraction in dicom.FractionGroupSequence:
        for beam in fraction.ReferencedBeamSequence:
            dicomBeam = []
            bn = (
                beam.ReferencedBeamNumber
            )  # pull beam reference number for simplification
            doseRef = fraction.ReferencedDoseReferenceSequence[
                0
            ].ReferencedDoseReferenceNumber  # pull dose reference number for simplification
            fn = fraction.FractionGroupNumber
            dicomBeam.append(dicom.RTPlanName)  # add prescription plan name
            dicomBeam.append(dicom.PatientID)  # add patient ID
            dicomBeam.append(dicom.PatientName.given_name)  # add patient name
            dicomBeam.append(dicom.PatientName.family_name)
            dicomBeam.append(dicom.PatientBirthDate)
            dicomBeam.append(doseRef)
            dicomBeam.append(dicom.BeamSequence[bn - 1].BeamName)  # add beam name
            dicomBeam.append(
                dicom.BeamSequence[bn - 1].BeamDescription
            )  # add beam description
            dicomBeam.append(
                dicom.BeamSequence[bn - 1].TreatmentMachineName
            )  # add machine being used
            dicomBeam.append(
                prescriptionDescription[fn - 1]
            )  # add specific prescription description
            dicomBeam.append(dicom.BeamSequence[bn - 1].RadiationType)
            dicomBeam.append(dicom.PatientSetupSequence[0].PatientPosition)
            dicomBeam.append(
                dicom.DoseReferenceSequence[doseRef - 1].TargetPrescriptionDose
                * 100
                / fraction.NumberOfFractionsPlanned
            )  # add dose per fraction for prescription
            dicomBeam.append(
                dicom.DoseReferenceSequence[doseRef - 1].TargetPrescriptionDose * 100
            )  # add prescription dose
            dicomBeam.append(fraction.NumberOfFractionsPlanned)
            dicomBeam.append(bn)
            dicomBeam.append(
                dicom.BeamSequence[bn - 1].ControlPointSequence[0].NominalBeamEnergy
            )  # add beam energy
            dicomBeam.append(
                dicom.BeamSequence[bn - 1].ReferencedToleranceTableNumber
            )  # add tolerance
            dicomBeam.append(
                beam.BeamMeterset
            )  # add planned MU to be delivered by beam
            dicomBeam.append(
                dicom.BeamSequence[bn - 1].ControlPointSequence[0].DoseRateSet
            )  # add dose rate for the beam
            dicomBeam.append("Back-Up Time")  # add back-up time for beam
            dicomBeam.append(
                dicom.BeamSequence[bn - 1].NumberOfWedges
            )  # add number of wedges on beam
            dicomBeam.append(
                dicom.BeamSequence[bn - 1].NumberOfBlocks
            )  # add number of blocks on beam
            dicomBeam.append("Cones")  # add number of cones on beam
            dicomBeam.append(
                dicom.BeamSequence[bn - 1].NumberOfBoli
            )  # add number of boli on beam
            dicomBeam.append(
                dicom.BeamSequence[bn - 1].ControlPointSequence[0].GantryAngle
            )  # add starting gantry angle
            dicomBeam.append(
                dicom.BeamSequence[bn - 1]
                .ControlPointSequence[0]
                .BeamLimitingDeviceAngle
            )  # add starting collimator angle
            dicomBeam.append("Field Size")  # add field size
            dicomBeam.append(
                dicom.BeamSequence[bn - 1].ControlPointSequence[0].PatientSupportAngle
            )
            dicomBeam.append(
                round(
                    dicom.BeamSequence[bn - 1]
                    .ControlPointSequence[0]
                    .SourceToSurfaceDistance
                    / 10,
                    1,
                )
            )
            dicomBeam.append(
                round(dicom.BeamSequence[bn - 1].SourceAxisDistance / 10, 1)
            )
            dicomBeam.append(
                dicom.BeamSequence[bn - 1].ControlPointSequence[0].IsocenterPosition[0]
                / 10
            )
            dicomBeam.append(
                dicom.BeamSequence[bn - 1].ControlPointSequence[0].IsocenterPosition[1]
                / 10
            )
            dicomBeam.append(
                dicom.BeamSequence[bn - 1].ControlPointSequence[0].IsocenterPosition[2]
                / 10
            )
            coll_x1 = (
                dicom.BeamSequence[bn - 1]
                .ControlPointSequence[0]
                .BeamLimitingDevicePositionSequence[0]
                .LeafJawPositions[0]
                / 10
            )
            coll_x2 = (
                dicom.BeamSequence[bn - 1]
                .ControlPointSequence[0]
                .BeamLimitingDevicePositionSequence[0]
                .LeafJawPositions[1]
                / 10
            )
            field_x = coll_x2 - coll_x1
            dicomBeam.append(field_x)
            dicomBeam.append(coll_x1)
            dicomBeam.append(coll_x2)
            coll_y1 = (
                dicom.BeamSequence[bn - 1]
                .ControlPointSequence[0]
                .BeamLimitingDevicePositionSequence[1]
                .LeafJawPositions[0]
                / 10
            )
            coll_y2 = (
                dicom.BeamSequence[bn - 1]
                .ControlPointSequence[0]
                .BeamLimitingDevicePositionSequence[1]
                .LeafJawPositions[1]
                / 10
            )
            field_y = coll_y2 - coll_y1
            dicomBeam.append(field_y)
            dicomBeam.append(coll_y1)
            dicomBeam.append(coll_y2)
            dicomBeam.append(
                dicom.BeamSequence[bn - 1]
                .ControlPointSequence[0]
                .TableTopVerticalPosition
            )
            dicomBeam.append(
                dicom.BeamSequence[bn - 1]
                .ControlPointSequence[0]
                .TableTopLateralPosition
            )
            dicomBeam.append(
                dicom.BeamSequence[bn - 1]
                .ControlPointSequence[0]
                .TableTopLongitudinalPosition
            )
            dicomBeam.append(
                dicom.BeamSequence[bn - 1]
                .ControlPointSequence[0]
                .TableTopEccentricAngle
            )
            dicomData.append(
                dicomBeam
            )  # add each prescription associated with a patient to the overall dicomBeam

    table = pd.DataFrame(
        data=dicomData,
        columns=[
            "site",
            "mrn",
            "first_name",
            "last_name",
            "dob",
            "dose_reference",
            "field_label",
            "field_name",
            "machine",
            "target",
            "technique",
            "postion",
            "fraction_dose",
            "total_dose",
            "fractions",
            "BEAM NUMBER",
            "energy",
            "tolerance",
            "monitor_units",
            "meterset_rate",
            "BACKUP TIME",
            "WEDGES",
            "block",
            "CONES",
            "BOLI",
            "gantry_angle",
            "collimator_angle",
            "FIELD SIZE",
            "COUCH ANGLE",
            "ssd",
            "sad",
            "iso_x",
            "iso_y",
            "iso_z",
            "field_x",
            "coll_x1",
            "coll_x2",
            "field_y",
            "coll_y1",
            "coll_y2",
            "couch_vrt",
            "couch_lat",
            "couch_lng",
            "couch_ang",
        ],
    )

    table["tolerance"] = [
        tolerance_constants.TOLERANCE_TYPES[item] for item in table["tolerance"]
    ]

    return table
