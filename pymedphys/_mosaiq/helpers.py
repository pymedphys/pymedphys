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

"""Some helper utility functions for accessing Mosaiq SQL.
"""

import collections
import datetime

from pymedphys._imports import pandas as pd

import pymedphys._utilities.patient

from .connect import execute_sql
from .constants import FIELD_TYPES, ORIENTATION


def get_treatment_times(cursor, field_id):
    treatment_time_results = execute_sql(
        cursor,
        """
        SELECT
            TrackTreatment.Create_DtTm,
            TrackTreatment.Edit_DtTm,
            Tracktreatment.WasBeamComplete,
            Tracktreatment.WasQAMode
        FROM TrackTreatment
        WHERE
            TrackTreatment.FLD_ID = %(field_id)s
        """,
        {"field_id": field_id},
    )

    return pd.DataFrame(
        data=treatment_time_results, columns=["start", "end", "completed", "qa_mode"]
    )


def get_patient_fields(cursor, patient_id):
    """Returns all of the patient fields for a given Patient ID.
    """
    patient_id = str(patient_id)

    patient_field_results = execute_sql(
        cursor,
        """
        SELECT
            TxField.FLD_ID,
            TxField.Field_Label,
            TxField.Field_Name,
            TxField.Version,
            TxField.Meterset,
            TxField.Type_Enum,
            Site.Site_Name
        FROM Ident, TxField, Site
        WHERE
            TxField.Pat_ID1 = Ident.Pat_ID1 AND
            TxField.SIT_Set_ID = Site.SIT_Set_ID AND
            Ident.IDA = %(patient_id)s
        """,
        {"patient_id": patient_id},
    )

    table = pd.DataFrame(
        data=patient_field_results,
        columns=[
            "field_id",
            "field_label",
            "field_name",
            "field_version",
            "monitor_units",
            "field_type",
            "site",
        ],
    )

    table.drop_duplicates(inplace=True)

    table["field_type"] = [FIELD_TYPES[item] for item in table["field_type"]]

    return table


def get_patient_name(cursor, patient_id):
    patient_id = str(patient_id)

    patient_name_results = execute_sql(
        cursor,
        """
        SELECT
            Patient.Last_Name,
            Patient.First_Name
        FROM Ident, Patient
        WHERE
            Patient.Pat_ID1 = Ident.Pat_ID1 AND
            Ident.IDA = %(patient_id)s
        """,
        {"patient_id": patient_id},
    )

    table = pd.DataFrame(data=patient_name_results, columns=["last_name", "first_name"])
    table.drop_duplicates(inplace=True)

    if len(table.index) < 1:
        raise ValueError("No patient found with that ID")

    if len(table.index) > 1:
        raise ValueError("Multiple patients were found with that ID")

    series = table.iloc[0]

    last_name = series["last_name"]
    first_name = series["first_name"]

    patient_name = pymedphys._utilities.patient.convert_patient_name_from_split(  # pylint: disable = protected-access
        last_name, first_name
    )

    return patient_name


def get_treatments(cursor, start, end, machine):
    treatment_results = execute_sql(
        cursor,
        """
        SELECT
            Ident.IDA,
            Patient.Last_Name,
            Patient.First_Name,
            TxField.FLD_ID,
            TxField.Field_Label,
            TxField.Field_Name,
            TxField.Type_Enum,
            TxField.Meterset,
            TxField.Version,
            Tracktreatment.WasQAMode,
            Tracktreatment.WasBeamComplete,
            TrackTreatment.Create_DtTm,
            TrackTreatment.Edit_DtTm
        FROM TrackTreatment, Ident, Patient, TxField, Staff
        WHERE
            TrackTreatment.Pat_ID1 = Ident.Pat_ID1 AND
            Patient.Pat_ID1 = Ident.Pat_ID1 AND
            TrackTreatment.FLD_ID = TxField.FLD_ID AND
            Staff.Staff_ID = TrackTreatment.Machine_ID_Staff_ID AND
            REPLACE(Staff.Last_Name, ' ', '') = %(machine)s AND
            TrackTreatment.Edit_DtTm >= %(start)s AND
            TrackTreatment.Create_DtTm <= %(end)s
        """,
        {"machine": machine, "start": start, "end": end},
    )

    table = pd.DataFrame(
        data=treatment_results,
        columns=[
            "patient_id",
            "last_name",
            "first_name",
            "field_id",
            "field_label",
            "field_name",
            "field_type",
            "monitor_units",
            "field_version",
            "qa_mode",
            "completed",
            "start",
            "end",
        ],
    )

    table["field_type"] = [FIELD_TYPES[item] for item in table["field_type"]]

    table = table.sort_values("start")

    return table


def get_staff_name(cursor, staff_id):
    data = execute_sql(
        cursor,
        """
        SELECT
            Staff.Initials,
            Staff.User_Name,
            Staff.Type,
            Staff.Category,
            Staff.Last_Name,
            Staff.First_Name
        FROM Staff
        WHERE
            Staff.Staff_ID = %(staff_id)s
        """,
        {"staff_id": staff_id},
    )

    results = pd.DataFrame(
        data=data,
        columns=[
            "initials",
            "user_name",
            "type",
            "category",
            "last_name",
            "first_name",
        ],
    )

    return results


def get_qcls_by_date(cursor, location, start, end):
    data = execute_sql(
        cursor,
        """
        SELECT
            Ident.IDA,
            Patient.Last_Name,
            Patient.First_Name,
            Chklist.Due_DtTm,
            Chklist.Act_DtTm,
            Chklist.Instructions,
            Chklist.Notes,
            QCLTask.Description
        FROM Chklist, Staff, QCLTask, Ident, Patient
        WHERE
            Chklist.Pat_ID1 = Ident.Pat_ID1 AND
            Patient.Pat_ID1 = Ident.Pat_ID1 AND
            QCLTask.TSK_ID = Chklist.TSK_ID AND
            Staff.Staff_ID = Chklist.Rsp_Staff_ID AND
            Staff.Last_Name = %(location)s AND
            Chklist.Act_DtTm >= %(start)s AND
            Chklist.Act_DtTm < %(end)s
        """,
        {"location": location, "start": start, "end": end},
    )

    results = pd.DataFrame(
        data=data,
        columns=[
            "patient_id",
            "last_name",
            "first_name",
            "due",
            "actual_completed_time",
            "instructions",
            "comment",
            "task",
        ],
    )

    results = results.sort_values(by=["actual_completed_time"])

    return results


def get_incomplete_qcls(cursor, location):
    data = execute_sql(
        cursor,
        """
        SELECT
            Ident.IDA,
            Patient.Last_Name,
            Patient.First_Name,
            Chklist.Due_DtTm,
            Chklist.Instructions,
            Chklist.Notes,
            QCLTask.Description
        FROM Chklist, Staff, QCLTask, Ident, Patient
        WHERE
            Chklist.Pat_ID1 = Ident.Pat_ID1 AND
            Patient.Pat_ID1 = Ident.Pat_ID1 AND
            QCLTask.TSK_ID = Chklist.TSK_ID AND
            Staff.Staff_ID = Chklist.Rsp_Staff_ID AND
            Staff.Last_Name = %(location)s AND
            Chklist.Complete = 0
        """,
        {"location": location},
    )
    datetime.date
    results = pd.DataFrame(
        data=data,
        columns=[
            "patient_id",
            "last_name",
            "first_name",
            "due",
            "instructions",
            "comment",
            "task",
        ],
    )

    results = results.sort_values(by=["due"], ascending=True)

    return results


def get_incomplete_qcls_across_sites(cursors, servers, centres, locations):
    results = pd.DataFrame()

    for centre in centres:
        cursor = cursors[servers[centre]]

        incomplete_qcls = get_incomplete_qcls(cursor, locations[centre])
        incomplete_qcls["centre"] = [centre] * len(incomplete_qcls)

        results = results.append(incomplete_qcls)

    results = results.sort_values(by="due")

    return results


def get_recently_completed_qcls_across_sites(
    cursors, servers, centres, locations, days=7
):
    now = datetime.datetime.now()
    days_ago = now - datetime.timedelta(days=days)
    tomorrow = now + datetime.timedelta(days=1)

    days_ago_string = "{} 00:00:00".format(days_ago.strftime("%Y-%m-%d"))
    tomorrow_string = "{} 00:00:00".format(tomorrow.strftime("%Y-%m-%d"))

    results = pd.DataFrame()

    for centre in centres:
        cursor = cursors[servers[centre]]

        qcls = get_qcls_by_date(
            cursor, locations[centre], days_ago_string, tomorrow_string
        )

        qcls["centre"] = [centre] * len(qcls)

        results = results.append(qcls)

    results = results.sort_values(by="actual_completed_time", ascending=False)

    return results


def get_all_treatment_data(cursor, mrn):

    dataframe_column_to_sql_reference = collections.OrderedDict(
        [
            ("mrn", "Ident.IDA"),
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
            ("wdg_appl", "TxField.Wdg_Appl"),
            ("block", "TxField.Block"),
            ("blk_desc", "TxField.Blk_Desc"),
            ("comp_fda", "TxField.Comp_Fda"),
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
            ("couch_ang", "TxFieldPoint.Couch_Ang"),
            ("tolerance", "TxField.Tol_Tbl_ID"),
            ("time", "TxField.BackupTimer"),
            ("site_setup_status", "SiteSetup.Status_Enum"),
            ("site_status", "Site.Status_Enum"),
            ("hidden", "TxField.IsHidden"),
            ("site_version", "Site.Version"),
            ("site_setup_version", "SiteSetup.Version"),
            ("create_id", "Site.Create_ID"),
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

    table = execute_sql(
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
    initials = execute_sql(
        cursor,
        """
        SELECT
        Staff.Initials
        FROM Staff
        WHERE
        Staff.Staff_ID = %(staff_id)s
        """,
        {"staff_id": staff_id},
    )

    return initials


def get_all_treatment_history_data(cursor, mrn):

    dataframe_column_to_sql_reference = collections.OrderedDict(
        [
            ("dose_ID", "TrackTreatment.DHS_ID"),
            ("date", "TrackTreatment.Create_DtTm"),
            ("field_name", "TxField.Field_Name"),
            ("fraction", "Dose_Hst.Fractions_Tx"),
            ("actual fx dose", "Dose_Hst.Dose_Tx_Act"),
            ("actual rx", "Dose_Hst.Dose_Ttl_Act"),
            ("actual cumRx", "Dose_Hst.Dose_Ttl_Cum_Act"),
            ("couch_vrt", "TxFieldPoint_Hst.Couch_Vrt"),
            ("couch_lat", "TxFieldPoint_Hst.Couch_Lat"),
            ("couch_lng", "TxFieldPoint_Hst.Couch_Lng"),
            ("couch_ang", "TxFieldPoint_Hst.Couch_Ang"),
            ("coll_x1", "TxFieldPoint_Hst.Coll_X1"),
            ("coll_x2", "TxFieldPoint_Hst.Coll_X2"),
            ("field_x", "TxFieldPoint_Hst.Field_X"),
            ("coll_y1", "TxFieldPoint_Hst.Coll_Y1"),
            ("coll_y2", "TxFieldPoint_Hst.Coll_Y2"),
            ("field_y", "TxFieldPoint_Hst.Field_Y"),
            ("status", "Patient.Clin_Status"),
            ("site_ID", "Dose_Hst.SIT_ID"),
            ("field_ID", "Dose_Hst.FLD_ID"),
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
        From Ident, Dose_Hst, Fld_Hst, TrackTreatment, Patient, TxField, TxFieldPoint_Hst, SiteSetup
        WHERE
        TxFieldPoint_Hst.FHS_ID = Fld_Hst.FHS_ID AND
        TxFieldPoint_Hst.Point=0 AND
        TrackTreatment.DHS_ID = Dose_Hst.DHS_ID AND
        Dose_Hst.SIS_ID = SiteSetup.SIS_ID AND
        FLD_HST.DHS_ID = Dose_Hst.DHS_ID AND
        Dose_Hst.Pat_ID1 = Patient.Pat_ID1 AND
        Patient.Pat_ID1 = Ident.Pat_ID1 AND
        TrackTreatment.WasQAMode = 0 AND
        TrackTreatment.FLD_ID = TxField.FLD_ID AND
        Ident.IDA = %(mrn)s
        """
    )

    table = execute_sql(cursor=cursor, sql_string=sql_string, parameters={"mrn": mrn})

    treatment_history = pd.DataFrame(data=table, columns=columns)
    treatment_history = treatment_history.sort_values(by=["date"])
    treatment_history = treatment_history.reset_index(drop=True)

    return treatment_history
