# Copyright (C) 2018 Cancer Care Associates

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

"""Some helper utility functions for accessing Mosaiq SQL.
"""

import pandas as pd

from .._level1.msqconnect import execute_sql, multi_mosaiq_connect
from .._level1.msqdictionaries import FIELD_TYPES

from .._level0.libutils import get_imports
IMPORTS = get_imports(globals())


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
        {
            'field_id': field_id
        }
    )

    return pd.DataFrame(
        data=treatment_time_results,
        columns=['start', 'end', 'completed', 'qa_mode']
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
        {
            'patient_id': patient_id
        }
    )

    table = pd.DataFrame(
        data=patient_field_results,
        columns=[
            'field_id', 'field_label', 'field_name', 'field_version',
            'monitor_units', 'field_type', 'site'
        ]
    )

    table['field_type'] = [
        FIELD_TYPES[item]
        for item in table['field_type']
    ]

    return table


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
        {
            'machine': machine,
            'start': start,
            'end': end
        }
    )

    table = pd.DataFrame(
        data=treatment_results,
        columns=[
            'patient_id', 'last_name', 'first_name',
            'field_id', 'field_label', 'field_name', 'field_type',
            'monitor_units', 'field_version',
            'qa_mode', 'completed',
            'start', 'end'
        ]
    )

    table['field_type'] = [
        FIELD_TYPES[item]
        for item in table['field_type']
    ]

    table = table.sort_values('start')

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
        {
            'staff_id': staff_id
        }
    )

    results = pd.DataFrame(
        data=data,
        columns=['initials', 'user_name',
                 'type', 'category', 'last_name', 'first_name']
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
            QCLTask.Description,
            Chklist.Act_DtTm,
            Staff.Last_Name,
            Chklist.Instructions,
            Chklist.Due_DtTm,
            Chklist.Complete
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
        {
            'location': location,
            'start': start,
            'end': end
        }
    )

    results = pd.DataFrame(
        data=data,
        columns=['patient_id', 'last_name', 'first_name', 'task',
                 'actual_completed_time',
                 'responsible_staff', 'instructions', 'due', 'complete']
    )

    results = results.sort_values(by=['actual_completed_time'])

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
        {
            'location': location
        }
    )

    results = pd.DataFrame(
        data=data,
        columns=['patient_id', 'last_name', 'first_name',
                 'due', 'instructions', 'comment', 'task']
    )

    results = results.sort_values(by=['due'], ascending=False)

    return results


def get_incomplete_qcls_across_sites(servers, centres, locations):
    servers_list = [
        item for _, item in servers.items()
    ]

    results = pd.DataFrame()

    with multi_mosaiq_connect(servers_list) as cursors:
        for centre in centres:
            cursor = cursors[servers[centre]]

            incomplete_qcls = get_incomplete_qcls(
                cursor, locations[centre])
            incomplete_qcls['centre'] = [centre] * len(incomplete_qcls)

            results = results.append(incomplete_qcls)

    results = results.sort_values(by='due')

    return results
