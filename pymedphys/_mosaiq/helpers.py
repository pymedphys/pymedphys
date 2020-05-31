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

import datetime

from pymedphys._imports import pandas as pd

import pymedphys._utilities.patient

from .connect import execute_sql
from .constants import FIELD_TYPES


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

    results = results.sort_values(by=["due"], ascending=False)

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
    table = execute_sql(
        cursor,
        """
        SELECT
            Ident.IDA,
            Patient.First_Name,
            Patient.Last_Name,
            Patient.Birth_DtTm,
            Staff.Last_Name,
            TxField.FLD_ID,
            TxField.Field_Label,
            TxField.Field_Name,
            Site.Target,
            Site.Rx_Depth,
            Site.Target_Units,
            Site.Technique,
            Site.Modality,
            TxFieldPoint.Energy,
            Site.Dose_Tx,
            Site.Dose_Ttl,
            Site.Fractions,
            Site.Notes,
            TxField.Version,
            TxField.Meterset,
            TxFieldPoint.Meterset_Rate,
            TxField.Type_Enum,
            TxFieldPoint.Gantry_Ang,
            TxFieldPoint.Coll_Ang,
            TxField.Ssd,
            TxField.SAD,
            Site.Site_Name,
            TxField.Dyn_Wedge,
            TxField.Wdg_Appl,
            TxField.Block,
            TxField.Blk_Desc,
            TxField.Comp_Fda,
            TxField.FDA_Desc,
            TxField.Bolus,
            SiteSetup.Isocenter_Position_X,
            SiteSetup.Isocenter_Position_Y,
            SiteSetup.Isocenter_Position_Z,
            TxFieldPoint.Field_X,
            TxFieldPoint.Coll_X1,
            TxFieldPoint.Coll_X2,
            TxFieldPoint.Field_Y,
            TxFieldPoint.Coll_Y1,
            TxFieldPoint.Coll_Y2,
            TxFieldPoint.Couch_Vrt,
            TxFieldPoint.Couch_Lat,
            TxFieldPoint.Couch_Lng,
            TxFieldPoint.Couch_Ang,
            TxField.Tol_Tbl_ID,
            TxField.BackupTimer

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
        """,
        {"patient_id": mrn},
    )

    mosaiq_fields = pd.DataFrame(
        data=table,
        columns=[
            "mrn",
            "first_name",
            "last_name",
            "dob",
            "machine",
            "field_id",
            "field_label",
            "field_name",
            "target",
            "rx_depth",
            "target_units",
            "technique",
            "modality",
            "energy",
            "fraction_dose",
            "total_dose",
            "fractions",
            "notes",
            "field_version",
            "monitor_units",
            "meterset_rate",
            "field_type",
            "gantry_angle",
            "collimator_angle",
            "ssd",
            "sad",
            "site",
            "dyn_wedge",
            "wdg_appl",
            "block",
            "blk_desc",
            "comp_fda",
            "fda_desc",
            "bolus",
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
            "tolerance",
            "time",
        ],
    )

    mosaiq_fields.drop_duplicates(inplace=True)
    mosaiq_fields["field_type"] = [
        FIELD_TYPES[item] for item in mosaiq_fields["field_type"]
    ]

    return mosaiq_fields
