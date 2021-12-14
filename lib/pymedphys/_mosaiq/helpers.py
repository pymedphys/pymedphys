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

from pymedphys._imports import pandas as pd

import pymedphys._utilities.patient

from . import api, constants


def get_treatment_times(connection, field_id):
    treatment_time_results = api.execute(
        connection,
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


def get_patient_fields(connection, patient_id):
    """Returns all of the patient fields for a given Patient ID."""
    patient_id = str(patient_id)

    patient_field_results = api.execute(
        connection,
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

    table["field_type"] = [constants.FIELD_TYPES[item] for item in table["field_type"]]

    return table


def get_patient_name(connection, patient_id):
    patient_id = str(patient_id)

    patient_name_results = api.execute(
        connection,
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


def get_treatments(connection, start, end, machine):
    treatment_results = api.execute(
        connection,
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
        {"machine": str(machine), "start": str(start), "end": str(end)},
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

    table["field_type"] = [constants.FIELD_TYPES[item] for item in table["field_type"]]

    table = table.sort_values("start")

    return table


def get_staff_name(connection, staff_id):
    data = api.execute(
        connection,
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


def get_qcls_by_date(connection, location, start, end):
    data = api.execute(
        connection,
        """
        SELECT
            Ident.IDA,
            Patient.Last_Name,
            Patient.First_Name,
            Chklist.Due_DtTm,
            Chklist.Act_DtTm,
            Com_Staff.Last_Name,
            Com_Staff.First_Name,
            QCLTask.Description
        FROM Chklist, Staff as Rsp_Staff, Staff as Com_Staff, QCLTask, Ident, Patient
        WHERE
            Chklist.Pat_ID1 = Ident.Pat_ID1 AND
            Patient.Pat_ID1 = Ident.Pat_ID1 AND
            QCLTask.TSK_ID = Chklist.TSK_ID AND
            Rsp_Staff.Staff_ID = Chklist.Rsp_Staff_ID AND
            RTRIM(LTRIM(Rsp_Staff.Last_Name)) = RTRIM(LTRIM(%(location)s)) AND
            Com_Staff.Staff_ID = Chklist.Com_Staff_ID AND
            Chklist.Act_DtTm >= %(start)s AND
            Chklist.Act_DtTm < %(end)s
        """,
        {"location": str(location), "start": str(start), "end": str(end)},
    )

    results = pd.DataFrame(
        data=data,
        columns=[
            "patient_id",
            "patient_last_name",
            "patient_first_name",
            "due",
            "actual_completed_time",
            "staff_last_name",
            "staff_first_name",
            "task",
        ],
    )

    results = results.sort_values(by=["actual_completed_time"], ascending=False)

    return results


def get_incomplete_qcls(connection, location):
    data = api.execute(
        connection,
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

    results = results.sort_values(by=["due"], ascending=True)

    return results
