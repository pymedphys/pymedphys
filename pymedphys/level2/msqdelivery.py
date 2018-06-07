# Copyright (C) 2018 CCA Health Care

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
# Affrero General Public License. These aditional terms are Sections 1, 5,
# 6, 7, 8, and 9 from the Apache License, Version 2.0 (the "Apache-2.0")
# where all references to the definition "License" are instead defined to
# mean the AGPL-3.0+.

# You should have received a copy of the Apache-2.0 along with this
# program. If not, see <http://www.apache.org/licenses/LICENSE-2.0>.


"""Uses Mosaiq SQL to name the linac log files.
"""

import struct

import attr

import numpy as np

from ..level1.trfdecode import DeliveryData
from ..level1.msqconnect import execute_sql


FIELD_TYPES = {
    1: 'Static',
    2: 'StepNShoot',
    5: 'CT',
    6: 'Port',
    11: 'Arc',
    12: 'Skip Arcs',
    13: 'VMAT',
    14: 'DMLC'
}

@attr.s
class OISDeliveryDetails(object):
    """A class containing patient information extracted from Mosaiq."""
    patient_id = attr.ib()
    field_id = attr.ib()
    last_name = attr.ib()
    first_name = attr.ib()
    qa_mode = attr.ib()
    field_type = attr.ib()


class MultipleMosaiqEntries(Exception):
    """Raise an exception when more than one disagreeing entry is found"""


class NoMosaiqEntries(Exception):
    """Raise an exception when no entry is found"""


def get_field_type(cursor, field_id):
    execute_string = """
        SELECT
            TxField.Type_Enum
        FROM TxField
        WHERE
            TxField.FLD_ID = %(field_id)s
        """

    parameters = {
        'field_id': field_id,
    }

    sql_result = execute_sql(cursor, execute_string, parameters)

    return FIELD_TYPES[sql_result[0][0]]


def get_mosaiq_delivery_details(cursor, machine, delivery_time, field_label,
                                field_name):
    """Identifies the patient details for a given delivery time.
    """

    execute_string = """
        SELECT
            Ident.IDA,
            TxField.FLD_ID,
            Patient.Last_Name,
            Patient.First_Name,
            Tracktreatment.WasQAMode,
            TxField.Type_Enum
        FROM TrackTreatment, Ident, Patient, TxField, Staff
        WHERE
            TrackTreatment.Pat_ID1 = Ident.Pat_ID1 AND
            Patient.Pat_ID1 = Ident.Pat_ID1 AND
            TrackTreatment.FLD_ID = TxField.FLD_ID AND
            Staff.Staff_ID = TrackTreatment.Machine_ID_Staff_ID AND
            REPLACE(Staff.Last_Name, ' ', '') = %(machine)s AND
            TrackTreatment.Create_DtTm <= %(delivery_time)s AND
            TrackTreatment.Edit_DtTm >= %(delivery_time)s AND
            TxField.Field_Label = %(field_label)s AND
            TxField.Field_Name = %(field_name)s
        """

    parameters = {
        'machine': machine,
        'delivery_time': delivery_time,
        'field_label': field_label,
        'field_name': field_name
    }

    sql_result = execute_sql(cursor, execute_string, parameters)

    if len(sql_result) > 1:
        for result in sql_result[1::]:
            if result != sql_result[0]:
                raise MultipleMosaiqEntries("Disagreeing entries were found.")

    if not sql_result:
        raise NoMosaiqEntries(
            "No Mosaiq entries were found for {}/{} at {}".format(
                field_label, field_name, delivery_time
            ))

    delivery_details = OISDeliveryDetails(*sql_result[0])

    delivery_details.field_type = FIELD_TYPES[delivery_details.field_type]

    return delivery_details


def mosaiq_mlc_missing_byte_workaround(raw_bytes_list):
    """This function checks if there is an odd number of bytes in the mlc list
    and appends a \\x00 if the byte number is odd.

    It is uncertain whether or not this is the correct method to restore the
    data.
    """
    length = check_all_items_equal_length(raw_bytes_list, 'mlc bytes')

    if length % 2 == 1:
        raw_bytes_list = append_x00_byte_to_all(raw_bytes_list)

    check_all_items_equal_length(raw_bytes_list, 'mlc bytes')

    return raw_bytes_list


def append_x00_byte_to_all(raw_bytes_list):
    appended_bytes_list = []
    for item in raw_bytes_list:
        bytes_as_list = list(item)
        bytes_as_list.append(0)
        appended_bytes_list.append(bytes(bytes_as_list))

    return appended_bytes_list


def check_all_items_equal_length(items, name):
    all_lengths = [
        len(item) for item in items
    ]
    length = list(set(all_lengths))

    assert len(length) == 1, "All {} should be the same length".format(name)

    return length[0]


def patient_fields(cursor, patient_id):
    """Returns all of the patient fields for a given Patient ID.
    """
    patient_id = str(patient_id)

    return execute_sql(
        cursor,
        """
        SELECT
            TxField.FLD_ID,
            TxField.Field_Label,
            TxField.Field_Name,
            TxField.Version,
            TxField.Meterset,
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


def decode_msq_mlc(raw_bytes):
    """Convert MLCs from Mosaiq SQL byte format to cm floats.
    """
    raw_bytes = mosaiq_mlc_missing_byte_workaround(raw_bytes)

    length = check_all_items_equal_length(raw_bytes, 'mlc bytes')

    if length % 2 == 1:
        raise Exception(
            'There should be an even number of bytes within an MLC record.')

    mlc_pos = np.array([
        [
            struct.unpack('<h', control_point[2*i:2*i+2])
            for i in range(len(control_point)//2)
        ]
        for control_point in raw_bytes
    ]) / 100

    return mlc_pos


def collimation_to_bipolar_mm(mlc_a, mlc_b, coll_y1, coll_y2):
    mlc1 = 10 * mlc_b[::-1, :]
    mlc2 = -10 * mlc_a[::-1, :]

    mlc = np.concatenate([mlc1[None, :, :], mlc2[None, :, :]], axis=0)

    jaw1 = 10 * coll_y2
    jaw2 = -10 * coll_y1

    jaw = np.concatenate([jaw1[None, :], jaw2[None, :]], axis=0)

    return mlc, jaw


def convert_angle_to_bipolar(angle):
    angle = np.copy(angle)
    angle[angle > 180] = angle[angle > 180] - 360

    is_180 = np.where(angle == 180)[0]
    not_180 = np.where(np.invert(angle == 180))[0]

    where_closest_left_leaning = np.argmin(
        np.abs(is_180[:, None] - not_180[None, :]), axis=1)
    where_closest_right_leaning = len(not_180) - 1 - np.argmin(np.abs(
        is_180[::-1, None] -
        not_180[None, ::-1]), axis=1)[::-1]

    closest_left_leaning = not_180[where_closest_left_leaning]
    closest_right_leaning = not_180[where_closest_right_leaning]

    assert np.all(
        np.sign(angle[closest_left_leaning]) ==
        np.sign(angle[closest_right_leaning])
    ), "Unable to automatically determine whether angle is 180 or -180"

    angle[is_180] = np.sign(angle[closest_left_leaning]) * angle[is_180]

    return angle


def delivery_data_sql(cursor, field_id):
    txfield_results = execute_sql(
        cursor,
        """
        SELECT
            TxField.Meterset
        FROM TxField
        WHERE
            TxField.FLD_ID = %(field_id)s
        """,
        {
            'field_id': field_id
        }
    )

    txfieldpoint_results = np.array(execute_sql(
        cursor,
        """
        SELECT
            TxFieldPoint.[Index],
            TxFieldPoint.A_Leaf_Set,
            TxFieldPoint.B_Leaf_Set,
            TxFieldPoint.Gantry_Ang,
            TxFieldPoint.Coll_Ang,
            TxFieldPoint.Coll_Y1,
            TxFieldPoint.Coll_Y2
        FROM TxFieldPoint
        WHERE
            TxFieldPoint.FLD_ID = %(field_id)s
        """,
        {
            'field_id': field_id
        }
    ))

    return txfield_results, txfieldpoint_results


def fetch_and_verify_mosaiq_sql(cursor, field_id):
    reference_results = delivery_data_sql(cursor, field_id)
    test_results = delivery_data_sql(cursor, field_id)

    agreement = False

    while not agreement:
        agreements = []
        for ref, test in zip(reference_results, test_results):
            agreements.append(np.all(ref == test))

        agreement = np.all(agreements)
        if not agreement:
            print('Mosaiq sql query gave conflicting data.')
            print('Trying again...')
            reference_results = test_results
            test_results = delivery_data_sql(cursor, field_id)

    return test_results


def delivery_data_from_mosaiq(cursor, field_id):
    txfield_results, txfieldpoint_results = fetch_and_verify_mosaiq_sql(
        cursor, field_id)

    total_mu = np.array(txfield_results[0]).astype(float)
    cumulative_percentage_mu = txfieldpoint_results[:, 0].astype(float)

    if np.shape(cumulative_percentage_mu) == ():
        mu_per_control_point = [0, total_mu]
    else:
        cumulative_mu = cumulative_percentage_mu * total_mu / 100
        mu_per_control_point = np.concatenate([[0], np.diff(cumulative_mu)])

    monitor_units = np.cumsum(mu_per_control_point).tolist()

    mlc_a = np.squeeze(
        decode_msq_mlc(txfieldpoint_results[:, 1].astype(bytes))).T
    mlc_b = np.squeeze(
        decode_msq_mlc(txfieldpoint_results[:, 2].astype(bytes))).T

    msq_gantry_angle = txfieldpoint_results[:, 3].astype(float)
    msq_collimator_angle = txfieldpoint_results[:, 4].astype(float)

    coll_y1 = txfieldpoint_results[:, 5].astype(float)
    coll_y2 = txfieldpoint_results[:, 6].astype(float)

    mlc, jaw = collimation_to_bipolar_mm(mlc_a, mlc_b, coll_y1, coll_y2)
    gantry = convert_angle_to_bipolar(msq_gantry_angle)
    collimator = convert_angle_to_bipolar(msq_collimator_angle)

    mosaiq_delivery_data = DeliveryData(
        monitor_units, gantry, collimator, mlc, jaw)

    return mosaiq_delivery_data
