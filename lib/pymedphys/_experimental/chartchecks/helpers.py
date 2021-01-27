# Copyright (C) 2020 Jacob Rembish

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

import collections

from pymedphys._imports import pandas as pd
from pymedphys._imports import pydicom

import pymedphys._mosaiq.api as pp_mosaiq

from .tolerance_constants import FIELD_TYPES, ORIENTATION


def _invert_angle(angle):
    return (180 - angle) % 360


def get_all_dicom_treatment_info(dicomFile):
    dicom = pydicom.dcmread(dicomFile)
    table = pd.DataFrame()

    try:
        prescriptionDescription = dicom.PrescriptionDescription.split("\\")
    except (TypeError, ValueError, AttributeError):
        prescriptionDescription = ""

    for fraction in dicom[0x300A, 0x0070]:
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

            dicom_beam = {
                "site": dicom.RTPlanName,
                "mrn": dicom.PatientID,
                "first_name": dicom.PatientName.given_name,
                "last_name": dicom.PatientName.family_name,
                "dob": dicom.PatientBirthDate,
                "dose_reference": doseRef,
                "field_label": dicom.BeamSequence[bn - 1].BeamName,
                "field_name": dicom.BeamSequence[bn - 1].BeamDescription,
                "machine": dicom.BeamSequence[bn - 1].TreatmentMachineName,
                "rx": prescriptionDescription[fn - 1],
                "modality": dicom.BeamSequence[bn - 1].RadiationType,
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
                "monitor_units": beam.BeamMeterset,
                "meterset_rate": dicom.BeamSequence[bn - 1]
                .ControlPointSequence[0]
                .DoseRateSet,
                "backup_time": "",
                "wedge": dicom.BeamSequence[bn - 1].NumberOfWedges,
                "block": dicom.BeamSequence[bn - 1].NumberOfBlocks,
                "compensator": dicom.BeamSequence[bn - 1].NumberOfCompensators,
                "bolus": dicom.BeamSequence[bn - 1].NumberOfBoli,
                "gantry_angle": dicom.BeamSequence[bn - 1]
                .ControlPointSequence[0]
                .GantryAngle,
                "collimator_angle": dicom.BeamSequence[bn - 1]
                .ControlPointSequence[0]
                .BeamLimitingDeviceAngle,
                "field_type": dicom.BeamSequence[bn - 1].BeamType,
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
                "field_x [cm]": round(coll_x2 - coll_x1, 1),
                "coll_x1 [cm]": round(coll_x1, 1),
                "coll_x2 [cm]": round(coll_x2, 1),
                "field_y [cm]": round(coll_y2 - coll_y1, 1),
                "coll_y1 [cm]": round(coll_y1, 1),
                "coll_y2 [cm]": round(coll_y2, 1),
                "couch_vrt [cm]": dicom.BeamSequence[bn - 1]
                .ControlPointSequence[0]
                .TableTopVerticalPosition,
                "couch_lat [cm]": dicom.BeamSequence[bn - 1]
                .ControlPointSequence[0]
                .TableTopLateralPosition,
                "couch_lng [cm]": dicom.BeamSequence[bn - 1]
                .ControlPointSequence[0]
                .TableTopLongitudinalPosition,
                "couch_angle": dicom.BeamSequence[bn - 1]
                .ControlPointSequence[0]
                .TableTopEccentricAngle,
                "technique": "",
            }

            try:
                dicom_beam["tolerance"] = dicom.BeamSequence[
                    bn - 1
                ].ReferencedToleranceTableNumber
            except (TypeError, ValueError, AttributeError):
                dicom_beam["tolerance"] = 0

            if dicom_beam["machine"] == "Vault 1-IMRT":

                angle_keys = [key for key in dicom_beam if "angle" in key]
                for key in angle_keys:
                    dicom_beam[key] = _invert_angle(dicom_beam[key])

                dicom_beam["coll_x1 [cm]"] = dicom_beam["coll_x1 [cm]"] * (-1)
                dicom_beam["coll_y1 [cm]"] = dicom_beam["coll_y1 [cm]"] * (-1)

            table = table.append(dicom_beam, ignore_index=True, sort=False)

    # table["tolerance"] = [
    #     tolerance_constants.TOLERANCE_TYPES[item] for item in table["tolerance"]
    # ]

    return table


def get_all_treatment_data(cursor, mrn):

    dataframe_column_to_sql_reference = collections.OrderedDict(
        [
            ("mrn", "Ident.IDA"),
            ("Pat_ID", "Ident.Pat_ID1"),
            ("first_name", "Patient.First_Name"),
            ("last_name", "Patient.Last_Name"),
            ("dob", "Patient.Birth_DtTm"),
            ("machine", "Staff.Last_Name"),
            ("field_id", "TxField.FLD_ID"),
            ("field_label", "TxField.Field_Label"),
            ("field_name", "TxField.Field_Name"),
            ("target", "Site.Target"),
            ("rx_depth", "Site.Rx_Depth"),
            ("target_units", "Site.Target_Units"),
            ("technique", "Site.Technique"),
            ("modality", "Site.Modality"),
            ("energy [MV]", "TxFieldPoint.Energy"),
            ("fraction_dose [cGy]", "Site.Dose_Tx"),
            ("total_dose [cGy]", "Site.Dose_Ttl"),
            ("fractions", "Site.Fractions"),
            ("fraction_pattern", "Site.Frac_Pattern"),
            ("notes", "Site.Notes"),
            ("field_version", "TxField.Version"),
            ("monitor_units", "TxField.Meterset"),
            ("meterset_rate", "TxFieldPoint.Meterset_Rate"),
            ("field_type", "TxField.Type_Enum"),
            ("gantry_angle", "TxFieldPoint.Gantry_Ang"),
            ("collimator_angle", "TxFieldPoint.Coll_Ang"),
            ("ssd [cm]", "TxField.Ssd"),
            ("sad [cm]", "TxField.SAD"),
            ("site", "Site.Site_Name"),
            ("dyn_wedge", "TxField.Dyn_Wedge"),
            ("wedge", "TxField.Wdg_Appl"),
            ("block", "TxField.Block"),
            ("blk_desc", "TxField.Blk_Desc"),
            ("compensator", "TxField.Comp_Fda"),
            ("fda_desc", "TxField.FDA_Desc"),
            ("bolus", "TxField.Bolus"),
            ("iso_x [cm]", "SiteSetup.Isocenter_Position_X"),
            ("iso_y [cm]", "SiteSetup.Isocenter_Position_Y"),
            ("iso_z [cm]", "SiteSetup.Isocenter_Position_Z"),
            ("position", "SiteSetup.Patient_Orient"),
            ("field_x [cm]", "TxFieldPoint.Field_X"),
            ("coll_x1 [cm]", "TxFieldPoint.Coll_X1"),
            ("coll_x2 [cm]", "TxFieldPoint.Coll_X2"),
            ("field_y [cm]", "TxFieldPoint.Field_Y"),
            ("coll_y1 [cm]", "TxFieldPoint.Coll_Y1"),
            ("coll_y2 [cm]", "TxFieldPoint.Coll_Y2"),
            ("couch_vrt [cm]", "TxFieldPoint.Couch_Vrt"),
            ("couch_lat [cm]", "TxFieldPoint.Couch_Lat"),
            ("couch_lng [cm]", "TxFieldPoint.Couch_Lng"),
            ("couch_angle", "TxFieldPoint.Couch_Ang"),
            ("tolerance", "TxField.Tol_Tbl_ID"),
            ("backup_time", "TxField.BackupTimer"),
            ("site_setup_status", "SiteSetup.Status_Enum"),
            ("site_status", "Site.Status_Enum"),
            ("hidden", "TxField.IsHidden"),
            ("site_version", "Site.Version"),
            ("site_setup_version", "SiteSetup.Version"),
            ("create_id", "Site.Sanct_Id"),
            ("field_approval", "TxField.Sanct_ID"),
            ("site_ID", "Site.SIT_ID"),
            ("site_setup_ID", "SiteSetup.SIS_ID"),
        ]
    )

    columns = list(dataframe_column_to_sql_reference.keys())
    select_string = "SELECT " + ",\n\t\t    ".join(
        dataframe_column_to_sql_reference.values()
    )

    sql_string = (
        select_string
        + """
                FROM Ident, TxField, Site, Patient, SiteSetup, TxFieldPoint, Staff
                WHERE
                    TxField.Pat_ID1 = Ident.Pat_ID1 AND
                    TxField.Machine_ID_Staff_ID = Staff.Staff_ID AND
                    TxFieldPoint.FLD_ID = TxField.FLD_ID AND
                    TxFieldPoint.Point = 0 AND
                    Patient.Pat_ID1 = Ident.Pat_ID1 AND
                    SiteSetup.SIT_Set_ID = TxField.SIT_Set_ID AND
                    TxField.SIT_Set_ID = Site.SIT_Set_ID AND
                    Ident.IDA = %(patient_id)s
                """
    )

    table = pp_mosaiq.execute(
        cursor=cursor, sql_string=sql_string, parameters={"patient_id": mrn}
    )

    mosaiq_fields = pd.DataFrame(data=table, columns=columns)

    mosaiq_fields.drop_duplicates(inplace=True)
    mosaiq_fields["field_type"] = [
        FIELD_TYPES[item] for item in mosaiq_fields["field_type"]
    ]

    mosaiq_fields["position"] = [
        ORIENTATION[item] for item in mosaiq_fields["position"]
    ]

    # reformat some fields to create the 'rx' field
    rx = []
    for i in mosaiq_fields.index:
        rx.append(
            str(
                mosaiq_fields["target"][i]
                + " "
                + str(mosaiq_fields["rx_depth"][i])
                + str(mosaiq_fields["target_units"][i])
            )
            + str(mosaiq_fields["modality"][i])
        )
    mosaiq_fields["rx"] = rx

    return mosaiq_fields


def get_staff_initials(cursor, staff_id):
    initials = pp_mosaiq.execute(
        cursor,
        """
        SELECT
        Staff.Initials
        FROM Staff
        WHERE
        Staff.Staff_ID = %(staff_id)s
        """,
        parameters={"staff_id": staff_id},
    )

    return initials


def get_all_treatment_history_data(cursor, mrn):

    dataframe_column_to_sql_reference = collections.OrderedDict(
        [
            ("dose_ID", "TrackTreatment.DHS_ID"),
            ("pat_ID", "Dose_Hst.Pat_ID1"),
            ("mrn", "Ident.IDA"),
            ("first_name", "Patient.First_Name"),
            ("last_name", "Patient.Last_Name"),
            ("date", "Fld_Hst.Tx_DtTm"),
            ("site", "Site.Site_Name"),
            ("field_name", "TxField.Field_Name"),
            ("field_label", "TxField.Field_Label"),
            ("fx", "Dose_Hst.Fractions_Tx"),
            ("rx", "Site.Dose_Ttl"),
            ("actual fx dose", "Dose_Hst.Dose_Tx_Act"),
            ("actual rx", "Dose_Hst.Dose_Ttl_Act"),
            ("field_dose_delivered", "Dose_Hst.Dose_Addtl_Projected"),
            ("machine", "Dose_Hst.Machine_ID_Staff_ID"),
            ("energy", "Dose_Hst.Energy"),
            ("energy_unit", "Dose_Hst.Energy_Unit_Enum"),
            ("couch_vrt", "TxFieldPoint_Hst.Couch_Vrt"),
            ("couch_lat", "TxFieldPoint_Hst.Couch_Lat"),
            ("couch_lng", "TxFieldPoint_Hst.Couch_Lng"),
            ("couch_angle", "TxFieldPoint_Hst.Couch_Ang"),
            ("coll_x1", "TxFieldPoint_Hst.Coll_X1"),
            ("coll_x2", "TxFieldPoint_Hst.Coll_X2"),
            ("field_x", "TxFieldPoint_Hst.Field_X"),
            ("coll_y1", "TxFieldPoint_Hst.Coll_Y1"),
            ("coll_y2", "TxFieldPoint_Hst.Coll_Y2"),
            ("field_y", "TxFieldPoint_Hst.Field_Y"),
            ("status", "Patient.Clin_Status"),
            ("site_ID", "Dose_Hst.SIT_ID"),
            ("site_version", "Site.Version"),
            ("field_ID", "Dose_Hst.FLD_ID"),
            ("site_setup_ID", "SiteSetup.SIS_ID"),
            ("site_setup_version", "SiteSetup.Version"),
            ("was_verified", "Dose_Hst.WasVerified"),
            ("was_overridden", "Dose_Hst.WasOverridden"),
            ("partial_tx", "Dose_Hst.PartiallyTreated"),
            ("vmi_error", "Dose_Hst.VMIError"),
            ("new_field", "Dose_Hst.NewFieldDef"),
            ("been_charted", "Dose_Hst.HasBeenCharted"),
            ("termination_status", "Dose_Hst.Termination_Status_Enum"),
            ("termination_verified", "Dose_Hst.Termination_Verify_Status_Enum"),
            ("modality", "Dose_Hst.Modality_Enum"),
            ("field_type", "Dose_Hst.Type_Enum"),
            ("meterset", "Dose_Hst.Meterset"),
            ("meterset_units", "Dose_Hst.MetersetUnit_Enum"),
            ("secondary_meterset", "Dose_Hst.SecondaryMeterset"),
            ("secondary_meterset_units", "Dose_Hst.SecondaryMetersetUnit_Enum"),
            ("MU_conversion", "Dose_Hst.cGrayPerMeterset"),
            ("TP_correction", "Dose_Hst.TP_Correction_Factor"),
        ]
    )

    columns = list(dataframe_column_to_sql_reference.keys())
    select_string = "SELECT " + ",\n\t\t    ".join(
        dataframe_column_to_sql_reference.values()
    )

    sql_string = (
        select_string
        + """
                From Ident, Dose_Hst, Fld_Hst, TrackTreatment, Patient, TxField, TxFieldPoint_Hst, SiteSetup, Site
                WHERE
                    Ident.IDA = %(mrn)s AND
                    Patient.Pat_ID1 = Ident.Pat_ID1 AND
                    Dose_Hst.Pat_ID1 = Patient.Pat_ID1 AND
                    Site.SIT_ID = Dose_Hst.SIT_ID AND
                    TxField.FLD_ID = Dose_Hst.FLD_ID AND
                    SiteSetup.SIS_ID = Dose_Hst.SIS_ID AND
                    TrackTreatment.DHS_ID = Dose_Hst.DHS_ID AND
                    FLD_HST.Pat_ID1 = Patient.Pat_ID1 AND
                    FLD_HST.DHS_ID = Dose_Hst.DHS_ID AND
                    TxFieldPoint_Hst.FHS_ID = Fld_Hst.FHS_ID AND
                    TxFieldPoint_Hst.Point=0 AND
                    TrackTreatment.WasQAMode = 0
        """,
    )

    table = pp_mosaiq.execute(
        cursor=cursor, sql_string=sql_string[0], parameters={"mrn": mrn}
    )

    treatment_history = pd.DataFrame(data=table, columns=columns)
    treatment_history = treatment_history.sort_values(by=["date"])
    treatment_history["total_dose_delivered"] = (
        treatment_history["actual rx"] + treatment_history["field_dose_delivered"]
    )
    treatment_history["total_dose_delivered"] = (
        treatment_history["total_dose_delivered"].astype(str)
        + "/"
        + treatment_history["rx"].astype(str)
    )
    treatment_history["field_type"] = [
        FIELD_TYPES[item] for item in treatment_history["field_type"]
    ]
    treatment_history = treatment_history.reset_index(drop=True)

    return treatment_history
