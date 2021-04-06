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
import pathlib

from pymedphys._imports import numpy as np
from pymedphys._imports import pandas as pd
from pymedphys._imports import streamlit as st

import pymedphys._mosaiq.api as pp_mosaiq

from .tolerance_constants import FIELD_TYPES, ORIENTATION, TOLERANCE_TYPES


def _invert_angle(angle):
    return (180 - angle) % 360


def get_dicom_wedge_info(beam_reference, field):

    for cp in field.ControlPointSequence:
        if cp.WedgePositionSequence[0].WedgePosition == "OUT":
            wedge_MU = cp.CumulativeMetersetWeight
            break

    wedge_info = {
        "wedge_type": field.WedgeSequence[0].WedgeType,
        "wedge_angle": field.WedgeSequence[0].WedgeAngle,
        "wedge_orientation": field.WedgeSequence[0].WedgeOrientation,
        "wedge_MU": wedge_MU * beam_reference.BeamMeterset,
    }

    st.write(field.BeamDescription)
    st.write(wedge_info)
    return wedge_info


def get_dicom_coll_info(field):

    keys = {
        "coll_x1": [0, 0],
        "coll_x2": [0, 1],
        "coll_y1": [1, 0],
        "coll_y2": [1, 1],
    }

    colls = {}
    for key, value in keys.items():
        colls[key] = (
            field.ControlPointSequence[0]
            .BeamLimitingDevicePositionSequence[value[0]]
            .LeafJawPositions[value[1]]
            / 10
        )

    return colls


def get_all_dicom_treatment_data(dicom):
    # dicom = pydicom.dcmread(dicomFile, force=True)
    table = pd.DataFrame()

    try:
        prescriptionDescription = dicom.PrescriptionDescription.split("\\")
    except (TypeError, ValueError, AttributeError):
        prescriptionDescription = ""

    for fraction in dicom[0x300A, 0x0070]:
        for beam in fraction.ReferencedBeamSequence:
            bn = beam.ReferencedBeamNumber
            dose_ref_number = fraction.ReferencedDoseReferenceSequence[
                0
            ].ReferencedDoseReferenceNumber
            dose_ref = dicom.DoseReferenceSequence[dose_ref_number - 1]
            fn = fraction.FractionGroupNumber
            field = dicom.BeamSequence[bn - 1]
            first_cp = field.ControlPointSequence[0]

            colls = get_dicom_coll_info(field)
            iso = first_cp.IsocenterPosition

            dicom_beam = {
                "site": dicom.RTPlanName,
                "mrn": dicom.PatientID,
                "first_name": dicom.PatientName.given_name,
                "last_name": dicom.PatientName.family_name,
                "dob": dicom.PatientBirthDate,
                "dose_reference": dose_ref_number,
                "field_label": str(field.BeamName).upper(),
                "field_name": field.BeamDescription,
                "machine": field.TreatmentMachineName,
                "rx": prescriptionDescription[fn - 1],
                "modality": field.RadiationType,
                "position": dicom.PatientSetupSequence[0].PatientPosition,
                "fraction_dose [cGy]": dose_ref.TargetPrescriptionDose
                * 100
                / fraction.NumberOfFractionsPlanned,
                "total_dose [cGy]": dose_ref.TargetPrescriptionDose * 100,
                "fractions": fraction.NumberOfFractionsPlanned,
                "BEAM NUMBER": bn,
                "energy [MV]": first_cp.NominalBeamEnergy,
                "monitor_units": beam.BeamMeterset,
                "meterset_rate": first_cp.DoseRateSet,
                "number_of_wedges": field.NumberOfWedges,
                "block": field.NumberOfBlocks,
                "compensator": field.NumberOfCompensators,
                "bolus": field.NumberOfBoli,
                "gantry_angle": first_cp.GantryAngle,
                "collimator_angle": first_cp.BeamLimitingDeviceAngle,
                "field_type": field.BeamType,
                "ssd [cm]": np.round(first_cp.SourceToSurfaceDistance / 10, 1),
                "sad [cm]": np.round(field.SourceAxisDistance / 10, 1),
                "iso_x [cm]": np.round(iso[0] / 10, 2),
                "iso_y [cm]": np.round(iso[1] / 10, 2),
                "iso_z [cm]": np.round(iso[2] / 10, 2),
                "field_x [cm]": np.round(colls["coll_x2"] - colls["coll_x1"], 1),
                "coll_x1 [cm]": np.round(colls["coll_x1"], 1),
                "coll_x2 [cm]": np.round(colls["coll_x2"], 1),
                "field_y [cm]": np.round(colls["coll_y2"] - colls["coll_y1"], 1),
                "coll_y1 [cm]": np.round(colls["coll_y1"], 1),
                "coll_y2 [cm]": np.round(colls["coll_y2"], 1),
                "couch_vrt [cm]": first_cp.TableTopVerticalPosition,
                "couch_lat [cm]": first_cp.TableTopLateralPosition,
                "couch_lng [cm]": first_cp.TableTopLongitudinalPosition,
                "couch_angle": first_cp.PatientSupportAngle,
                "technique": "",
                "tolerance": "",
                "control_points": field.NumberOfControlPoints,
            }

            if dicom_beam["number_of_wedges"] != 0:
                dicom_beam.update(
                    get_dicom_wedge_info(beam, dicom.BeamSequence[bn - 1])
                )

            if dicom_beam["machine"] in ["Vault 1-IMRT", "Dual-120"]:

                angle_keys = [key for key in dicom_beam if "angle" in key]
                for key in angle_keys:
                    dicom_beam[key] = _invert_angle(dicom_beam[key])

                dicom_beam["coll_x1 [cm]"] = dicom_beam["coll_x1 [cm]"] * (-1)
                dicom_beam["coll_y1 [cm]"] = dicom_beam["coll_y1 [cm]"] * (-1)

            table = table.append(dicom_beam, ignore_index=True, sort=False)

    return table


def get_all_mosaiq_treatment_data(connection, mrn):

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
            ("control_points", "TxField.ControlPoints"),
            ("field_type", "TxField.Type_Enum"),
            ("gantry_angle", "TxFieldPoint.Gantry_Ang"),
            ("collimator_angle", "TxFieldPoint.Coll_Ang"),
            ("ssd [cm]", "TxField.Ssd"),
            ("sad [cm]", "TxField.SAD"),
            ("site", "Site.Site_Name"),
            ("dyn_wedge", "TxField.Dyn_Wedge"),
            ("wedge", "TxField.Wdg_Appl"),
            ("wedge_slot", "TxField.WdgApplSlot"),
            ("motorized_wedge", "TxFieldPoint.IsMotorizedWedgeIn"),
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
        connection=connection, query=sql_string, parameters={"patient_id": mrn}
    )

    mosaiq_fields = pd.DataFrame(data=table, columns=columns)

    mosaiq_fields.drop_duplicates(inplace=True)
    mosaiq_fields["field_type"] = [
        FIELD_TYPES[item] for item in mosaiq_fields["field_type"]
    ]

    mosaiq_fields["position"] = [
        ORIENTATION[item] for item in mosaiq_fields["position"]
    ]

    mosaiq_fields["tolerance"] = [
        TOLERANCE_TYPES[item] for item in mosaiq_fields["tolerance"]
    ]

    mosaiq_fields["field_label"] = mosaiq_fields["field_label"].str.upper()
    # for row in mosaiq_fields.index:
    #     if mosaiq_fields.loc[row, 'rx_depth'] != 0:
    #         mosaiq_fields.loc[row, "fraction_dose [cGy]"] = round(mosaiq_fields.loc[row, "fraction_dose [cGy]"] / (mosaiq_fields.loc[row, 'rx_depth']/100), 2)
    #         mosaiq_fields.loc[row, "total_dose [cGy]"] = round(mosaiq_fields.loc[row, "total_dose [cGy]"] / (mosaiq_fields.loc[row, 'rx_depth'] / 100), 2)

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


def get_staff_initials(connection, staff_id):
    initials = pp_mosaiq.execute(
        connection,
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


def get_all_treatment_history_data(connection, mrn):

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
            ("overrides1", "Dose_Hst.Overrides1"),
            ("overrides2", "Dose_Hst.Overrides2"),
            ("overrides3", "Dose_Hst.Overrides3"),
            ("overrides4", "Dose_Hst.Overrides4"),
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
            ("fx_pattern", "Site.Frac_Pattern"),
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
        connection=connection, query=sql_string[0], parameters={"mrn": mrn}
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


def get_structure_aliases():
    file_path = pathlib.Path(__file__).parent.joinpath("structure_aliases.json")
    return pd.read_json(file_path)


def add_new_structure_alias(dvh_calcs, alias_df):
    file_path = pathlib.Path(__file__).parent.joinpath("structure_aliases.json")

    default = [
        "< Select an ROI >",
    ]
    alias_list = list(dvh_calcs.keys())
    alias_list = default + alias_list
    alias_select = st.selectbox("Select a structure to define: ", alias_list)
    key_list = list(list(alias_df))
    key_list = default + key_list
    key_select = st.selectbox("Select an assignment: ", key_list)

    if alias_select != "< Select an ROI >" and key_select != "< Select an ROI >":
        alias_df[key_select].iloc[0].append(alias_select.lower())
        alias_df.to_json(file_path, indent=4)


def get_dose_constraints():
    file_path = pathlib.Path(__file__).parent.joinpath("dose_constraints.json")
    return pd.read_json(file_path)
