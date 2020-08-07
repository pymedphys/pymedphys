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
    table = pd.DataFrame()

    try:
        prescriptionDescription = dicom.PrescriptionDescription.split("\\")
    except AttributeError:
        prescriptionDescription = ""

    for fraction in dicom.FractionGroupSequence:
        for beam in fraction.ReferencedBeamSequence:
            bn = (
                beam.ReferencedBeamNumber
            )  # pull beam reference number for simplification
            doseRef = fraction.ReferencedDoseReferenceSequence[
                0
            ].ReferencedDoseReferenceNumber  # pull dose reference number for simplification
            fn = fraction.FractionGroupNumber

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

            dicomBeam = {
                "site": dicom.RTPlanName,
                "mrn": dicom.PatientID,
                "first_name": dicom.PatientName.given_name,
                "last_name": dicom.PatientName.family_name,
                "dob": dicom.PatientBirthDate,
                "dose_reference": doseRef,
                "field_label": dicom.BeamSequence[bn - 1].BeamName,
                "field_name": dicom.BeamSequence[bn - 1].BeamDescription,
                "field_type": "",
                "machine": dicom.BeamSequence[bn - 1].TreatmentMachineName,
                "rx": prescriptionDescription[fn - 1],
                "technique": dicom.BeamSequence[bn - 1].RadiationType,
                "position": dicom.PatientSetupSequence[0].PatientPosition,
                "fraction_dose [cGy]": dicom.DoseReferenceSequence[
                    doseRef - 1
                ].TargetPrescriptionDose
                * 100
                / fraction.NumberOfFractionsPlanned,
                "total_dose [cGy]": dicom.DoseReferenceSequence[
                    doseRef - 1
                ].TargetPrescriptionDose
                * 100,
                "fractions": fraction.NumberOfFractionsPlanned,
                "BEAM NUMBER": bn,
                "energy [MV]": dicom.BeamSequence[bn - 1]
                .ControlPointSequence[0]
                .NominalBeamEnergy,
                "tolerance": dicom.BeamSequence[bn - 1].ReferencedToleranceTableNumber,
                "monitor_units": beam.BeamMeterset,
                "meterset_rate": dicom.BeamSequence[bn - 1]
                .ControlPointSequence[0]
                .DoseRateSet,
                "BACKUP TIME": "Back-Up Time",
                "WEDGES": dicom.BeamSequence[bn - 1].NumberOfWedges,
                "block": dicom.BeamSequence[bn - 1].NumberOfBlocks,
                "CONES": "cones",
                "bolus": dicom.BeamSequence[bn - 1].NumberOfBoli,
                "gantry_angle": dicom.BeamSequence[bn - 1]
                .ControlPointSequence[0]
                .GantryAngle,
                "collimator_angle": dicom.BeamSequence[bn - 1]
                .ControlPointSequence[0]
                .BeamLimitingDeviceAngle,
                "FIELD SIZE": "field size",
                "COUCH ANGLE": dicom.BeamSequence[bn - 1]
                .ControlPointSequence[0]
                .PatientSupportAngle,
                "ssd [cm]": round(
                    dicom.BeamSequence[bn - 1]
                    .ControlPointSequence[0]
                    .SourceToSurfaceDistance
                    / 10,
                    1,
                ),
                "sad [cm]": round(
                    dicom.BeamSequence[bn - 1].SourceAxisDistance / 10, 1
                ),
                "iso_x [cm]": dicom.BeamSequence[bn - 1]
                .ControlPointSequence[0]
                .IsocenterPosition[0]
                / 10,
                "iso_y [cm]": dicom.BeamSequence[bn - 1]
                .ControlPointSequence[0]
                .IsocenterPosition[1]
                / 10,
                "iso_z [cm]": dicom.BeamSequence[bn - 1]
                .ControlPointSequence[0]
                .IsocenterPosition[2]
                / 10,
                "field_x [cm]": coll_x2 - coll_x1,
                "coll_x1 [cm]": coll_x1,
                "coll_x2 [cm]": coll_x2,
                "field_y [cm]": coll_y2 - coll_y1,
                "coll_y1 [cm]": coll_y1,
                "coll_y2 [cm]": coll_y2,
                "couch_vrt [cm]": dicom.BeamSequence[bn - 1]
                .ControlPointSequence[0]
                .TableTopVerticalPosition,
                "couch_lat [cm]": dicom.BeamSequence[bn - 1]
                .ControlPointSequence[0]
                .TableTopLateralPosition,
                "couch_lng [cm]": dicom.BeamSequence[bn - 1]
                .ControlPointSequence[0]
                .TableTopLongitudinalPosition,
                "couch_ang": dicom.BeamSequence[bn - 1]
                .ControlPointSequence[0]
                .TableTopEccentricAngle,
            }

            table = table.append(dicomBeam, ignore_index=True, sort=False)

    # table["tolerance"] = [
    #     tolerance_constants.TOLERANCE_TYPES[item] for item in table["tolerance"]
    # ]

    return table
