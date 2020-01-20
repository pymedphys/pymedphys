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


"""Uses Mosaiq SQL to extract patient delivery details.
"""

import functools
import struct

from pymedphys._imports import attr
from pymedphys._imports import numpy as np

from pymedphys._base.delivery import DeliveryBase
from pymedphys._utilities.transforms import convert_IEC_angle_to_bipolar

from .connect import execute_sql
from .constants import FIELD_TYPES


@functools.lru_cache()
def create_ois_delivery_details_class():
    @attr.s
    class OISDeliveryDetails:
        """A class containing patient information extracted from Mosaiq."""

        patient_id = attr.ib()
        field_id = attr.ib()
        last_name = attr.ib()
        first_name = attr.ib()
        qa_mode = attr.ib()
        field_type = attr.ib()
        beam_completed = attr.ib()

    return OISDeliveryDetails


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

    parameters = {"field_id": field_id}

    sql_result = execute_sql(cursor, execute_string, parameters)

    return FIELD_TYPES[sql_result[0][0]]


def get_mosaiq_delivery_details(
    cursor, machine, delivery_time, field_label, field_name, buffer=0
):
    """Identifies the patient details for a given delivery time.

    Args:
    Args:
        cursor: A pymssql cursor pointing to the Mosaiq SQL server
        machine: The name of the machine the delivery occured on
        delivery_time: The time of the treatment delivery
        field_label: The beam field label, called Field ID within Monaco
        field_name: The beam field name, called Description within Monaco
    Returns:
        delivery_details: The identified delivery details
            patient_id: User defined Mosaiq patient ID
            field_id: Internal Mosaiq SQL field ID
            last_name: Patient last name
            first_name: Patient first name
            qa_mode: Whether or not the delivery was in QA mode
            field_type: What field type the delivery was
            beam_completed: Whether or not this beam was the last in a sequence
    """

    # TODO Need to update the logic here to search for previous treatments
    # that were incomplete. Actually, this doesn't need to be in the indexing.
    # Can solve this later on using multiple beams with one logfile ending in
    # 'Terminated Fault'.

    # TODO WasBeamComplete informs whether or not there were beams grouped
    # together. If WasBeamComplete is false should actually search for
    # subsequent beams until WasBeamComplete is true. This will help the case
    # where multiple beams are MFSed into one delivery, resulting in multiple
    # field ids and labels for a single logfile.

    # TODO Convert all times to UTC so that timezone is not required within
    # the API.
    # https://docs.microsoft.com/en-us/sql/t-sql/queries/at-time-zone-transact-sql?view=sql-server-2017

    execute_string = """
        SELECT
            Ident.IDA,
            TxField.FLD_ID,
            Patient.Last_Name,
            Patient.First_Name,
            Tracktreatment.WasQAMode,
            TxField.Type_Enum,
            Tracktreatment.WasBeamComplete
        FROM TrackTreatment, Ident, Patient, TxField, Staff
        WHERE
            TrackTreatment.Pat_ID1 = Ident.Pat_ID1 AND
            Patient.Pat_ID1 = Ident.Pat_ID1 AND
            TrackTreatment.FLD_ID = TxField.FLD_ID AND
            Staff.Staff_ID = TrackTreatment.Machine_ID_Staff_ID AND
            REPLACE(Staff.Last_Name, ' ', '') = %(machine)s AND
            TrackTreatment.Create_DtTm <= DATEADD(second, %(buffer)d, %(delivery_time)s) AND
            TrackTreatment.Edit_DtTm >= DATEADD(second, -%(buffer)d, %(delivery_time)s) AND
            TxField.Field_Label = %(field_label)s AND
            TxField.Field_Name = %(field_name)s
        """

    parameters = {
        "buffer": buffer,
        "machine": machine,
        "delivery_time": delivery_time,
        "field_label": field_label,
        "field_name": field_name,
    }

    sql_result = execute_sql(cursor, execute_string, parameters)

    if len(sql_result) > 1:
        for result in sql_result[1::]:
            if result != sql_result[0]:
                if buffer != 0:
                    return get_mosaiq_delivery_details(
                        cursor,
                        machine,
                        delivery_time,
                        field_label,
                        field_name,
                        buffer=0,
                    )

                raise MultipleMosaiqEntries("Disagreeing entries were found.")

    if not sql_result:
        raise NoMosaiqEntries(
            "No Mosaiq entries were found for {}/{} at {}".format(
                field_label, field_name, delivery_time
            )
        )

    OISDeliveryDetails = create_ois_delivery_details_class()
    delivery_details = OISDeliveryDetails(*sql_result[0])

    delivery_details.field_type = FIELD_TYPES[delivery_details.field_type]

    return delivery_details


def mosaiq_mlc_missing_byte_workaround(raw_bytes_list):
    """This function checks if there is an odd number of bytes in the mlc list
    and appends a \\x00 if the byte number is odd.

    It is uncertain whether or not this is the correct method to restore the
    data.
    """
    length = check_all_items_equal_length(raw_bytes_list, "mlc bytes")

    if length % 2 == 1:
        raw_bytes_list = append_x00_byte_to_all(raw_bytes_list)

    check_all_items_equal_length(raw_bytes_list, "mlc bytes")

    return raw_bytes_list


def append_x00_byte_to_all(raw_bytes_list):
    appended_bytes_list = []
    for item in raw_bytes_list:
        bytes_as_list = list(item)
        bytes_as_list.append(0)
        appended_bytes_list.append(bytes(bytes_as_list))

    return appended_bytes_list


def check_all_items_equal_length(items, name):
    all_lengths = [len(item) for item in items]
    length = list(set(all_lengths))

    assert len(length) == 1, "All {} should be the same length".format(name)

    return length[0]


def decode_msq_mlc(raw_bytes):
    """Convert MLCs from Mosaiq SQL byte format to cm floats.
    """
    raw_bytes = mosaiq_mlc_missing_byte_workaround(raw_bytes)

    length = check_all_items_equal_length(raw_bytes, "mlc bytes")

    if length % 2 == 1:
        raise Exception("There should be an even number of bytes within an MLC record.")

    mlc_pos = (
        np.array(
            [
                [
                    struct.unpack("<h", control_point[2 * i : 2 * i + 2])
                    for i in range(len(control_point) // 2)
                ]
                for control_point in raw_bytes
            ]
        )
        / 100
    )

    return mlc_pos


def collimation_to_bipolar_mm(mlc_a, mlc_b, coll_y1, coll_y2):
    mlc1 = 10 * mlc_b[::-1, :]
    mlc2 = -10 * mlc_a[::-1, :]

    mlc = np.concatenate([mlc1[None, :, :], mlc2[None, :, :]], axis=0)

    jaw1 = 10 * coll_y2
    jaw2 = -10 * coll_y1

    jaw = np.concatenate([jaw1[None, :], jaw2[None, :]], axis=0)

    return mlc, jaw


def delivery_data_sql(cursor, field_id):
    """Get the treatment delivery data from Mosaiq given the SQL field_id

    Args:
        cursor: A pymssql cursor pointing to the Mosaiq SQL server
        field_id: The Mosaiq SQL field ID

    Returns:
        txfield_results: The results from the TxField table.
        txfieldpoint_results: The results from the TxFieldPoint table.
    """
    txfield_results = execute_sql(
        cursor,
        """
        SELECT
            TxField.Meterset
        FROM TxField
        WHERE
            TxField.FLD_ID = %(field_id)s
        """,
        {"field_id": field_id},
    )

    txfieldpoint_results = np.array(
        execute_sql(
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
            {"field_id": field_id},
        )
    )

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
            print("Mosaiq sql query gave conflicting data.")
            print("Trying again...")
            reference_results = test_results
            test_results = delivery_data_sql(cursor, field_id)

    return test_results


class DeliveryMosaiq(DeliveryBase):
    @classmethod
    def from_mosaiq(cls, cursor, field_id):
        mosaiq_delivery_data = cls._from_mosaiq_base(cursor, field_id)
        reference_data = (
            mosaiq_delivery_data.monitor_units,
            mosaiq_delivery_data.mlc,
            mosaiq_delivery_data.jaw,
        )

        delivery_data = cls._from_mosaiq_base(cursor, field_id)
        test_data = (delivery_data.monitor_units, delivery_data.mlc, delivery_data.jaw)

        agreement = False

        while not agreement:
            agreements = []
            for ref, test in zip(reference_data, test_data):
                agreements.append(np.all(ref == test))

            agreement = np.all(agreements)
            if not agreement:
                print("Converted Mosaiq delivery data was conflicting.")
                print(
                    "MU agreement: {}\nMLC agreement: {}\n"
                    "Jaw agreement: {}".format(*agreements)
                )
                print("Trying again...")
                reference_data = test_data
                delivery_data = cls._from_mosaiq_base(cursor, field_id)
                test_data = (
                    delivery_data.monitor_units,
                    delivery_data.mlc,
                    delivery_data.jaw,
                )

        return delivery_data

    @classmethod
    def _from_mosaiq_base(cls, cursor, field_id):
        txfield_results, txfieldpoint_results = fetch_and_verify_mosaiq_sql(
            cursor, field_id
        )

        total_mu = np.array(txfield_results[0]).astype(float)
        cumulative_percentage_mu = txfieldpoint_results[:, 0].astype(float)

        if np.shape(cumulative_percentage_mu) == ():
            mu_per_control_point = [0, total_mu]
        else:
            cumulative_mu = cumulative_percentage_mu * total_mu / 100
            mu_per_control_point = np.concatenate([[0], np.diff(cumulative_mu)])

        monitor_units = np.cumsum(mu_per_control_point).tolist()

        mlc_a = np.squeeze(decode_msq_mlc(txfieldpoint_results[:, 1].astype(bytes))).T
        mlc_b = np.squeeze(decode_msq_mlc(txfieldpoint_results[:, 2].astype(bytes))).T

        msq_gantry_angle = txfieldpoint_results[:, 3].astype(float)
        msq_collimator_angle = txfieldpoint_results[:, 4].astype(float)

        coll_y1 = txfieldpoint_results[:, 5].astype(float)
        coll_y2 = txfieldpoint_results[:, 6].astype(float)

        mlc, jaw = collimation_to_bipolar_mm(mlc_a, mlc_b, coll_y1, coll_y2)
        gantry = convert_IEC_angle_to_bipolar(msq_gantry_angle)
        collimator = convert_IEC_angle_to_bipolar(msq_collimator_angle)

        # TODO Tidy up this axis swap
        mlc = np.swapaxes(mlc, 0, 2)
        jaw = np.swapaxes(jaw, 0, 1)

        mosaiq_delivery_data = cls(monitor_units, gantry, collimator, mlc, jaw)

        return mosaiq_delivery_data
