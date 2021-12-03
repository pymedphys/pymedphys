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
from pymedphys._imports import pandas as pd

from pymedphys._base.delivery import DeliveryBase
from pymedphys._utilities.transforms import convert_IEC_angle_to_bipolar

from . import api, constants


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


class MultipleMosaiqEntries(ValueError):
    """Raise an exception when more than one disagreeing entry is found"""


class NoMosaiqEntries(ValueError):
    """Raise an exception when no entry is found"""


def get_field_type(connection, field_id):
    execute_string = """
        SELECT
            TxField.Type_Enum
        FROM TxField
        WHERE
            TxField.FLD_ID = %(field_id)s
        """

    parameters = {"field_id": field_id}

    sql_result = api.execute(connection, execute_string, parameters)

    return constants.FIELD_TYPES[sql_result[0][0]]


def get_mosaiq_delivery_details(
    connection, machine, delivery_time, field_label, field_name, buffer=0
):
    """Identifies the patient details for a given delivery time.

    Args:
    Args:
        connection: A connection pointing to the Mosaiq SQL server
        machine: The name of the machine the delivery occurred on
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

    sql_result = api.execute(connection, execute_string, parameters)

    if len(sql_result) > 1:
        for result in sql_result[1::]:
            if result != sql_result[0]:
                if buffer != 0:
                    return get_mosaiq_delivery_details(
                        connection,
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

    delivery_details.field_type = constants.FIELD_TYPES[delivery_details.field_type]

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
    all_lengths = {len(item) for item in items}

    if len(all_lengths) != 1:
        raise ValueError(
            f"All {name} should be the same length. The lengths seen were "
            f"{all_lengths}."
        )

    return list(all_lengths)[0]


def decode_msq_mlc(raw_bytes):
    """Convert MLCs from Mosaiq SQL byte format to cm floats."""
    raw_bytes = mosaiq_mlc_missing_byte_workaround(raw_bytes)

    length = check_all_items_equal_length(raw_bytes, "mlc bytes")

    if length % 2 == 1:
        raise ValueError(
            "There should be an even number of bytes within an MLC record."
        )

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


def _raw_delivery_data_sql(connection, field_id):
    txfield_results = api.execute(
        connection,
        """
        SELECT
            TxField.Meterset
        FROM TxField
        WHERE
            TxField.FLD_ID = %(field_id)s
        """,
        {
            "field_id": field_id,
        },
    )

    txfieldpoint_results = api.execute(
        connection,
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
        ORDER BY
            TxFieldPoint.Point
        """,
        {"field_id": field_id},
    )

    return txfield_results, txfieldpoint_results


def delivery_data_sql(connection, field_id):
    """Get the treatment delivery data from Mosaiq given the SQL field_id

    Args:
        connection: A connection pointing to the Mosaiq SQL server
        field_id: The Mosaiq SQL field ID

    Returns:
        txfield_results: The results from the TxField table.
        txfieldpoint_results: The results from the TxFieldPoint table.
    """
    raw_txfield_results, raw_txfieldpoint_results = _raw_delivery_data_sql(
        connection, field_id
    )

    if len(raw_txfield_results) != 1:
        raise ValueError(
            f"The return results from txfield query gave {raw_txfield_results}. "
            "Expected exactly one row."
        )
    meterset = np.array(raw_txfield_results[0]).astype(float)

    if len(raw_txfieldpoint_results) == 0:
        raise ValueError("No TxFieldPoints were returned.")

    txfieldpoint_results = pd.DataFrame(
        data=raw_txfieldpoint_results,
        columns=[
            "Index",
            "A_Leaf_Set",
            "B_Leaf_Set",
            "Gantry_Ang",
            "Coll_Ang",
            "Coll_Y1",
            "Coll_Y2",
        ],
    )

    return meterset, txfieldpoint_results


class DeliveryMosaiq(DeliveryBase):
    @classmethod
    def from_mosaiq(cls, connection, field_id):
        total_mu, tx_field_points = delivery_data_sql(connection, field_id)
        tx_field_points_index = tx_field_points["Index"].to_numpy(dtype=float)

        if np.shape(tx_field_points_index) == ():
            mu_per_control_point = [0, total_mu]
        else:
            cumulative_mu = tx_field_points_index / tx_field_points_index[-1] * total_mu
            mu_per_control_point = np.concatenate([[0], np.diff(cumulative_mu)])

        monitor_units = np.cumsum(mu_per_control_point).tolist()

        raw_mlc_a = tx_field_points["A_Leaf_Set"].to_numpy(dtype=bytes)
        mlc_a = np.squeeze(decode_msq_mlc(raw_mlc_a)).T

        raw_mlc_b = tx_field_points["B_Leaf_Set"].to_numpy(dtype=bytes)
        mlc_b = np.squeeze(decode_msq_mlc(raw_mlc_b)).T

        msq_gantry_angle = tx_field_points["Gantry_Ang"].to_numpy(dtype=float)
        msq_collimator_angle = tx_field_points["Coll_Ang"].to_numpy(dtype=float)

        coll_y1 = tx_field_points["Coll_Y1"].to_numpy(dtype=float)
        coll_y2 = tx_field_points["Coll_Y2"].to_numpy(dtype=float)

        mlc, jaw = collimation_to_bipolar_mm(mlc_a, mlc_b, coll_y1, coll_y2)
        gantry = convert_IEC_angle_to_bipolar(msq_gantry_angle)
        collimator = convert_IEC_angle_to_bipolar(msq_collimator_angle)

        # TODO Tidy up this axis swap
        mlc = np.swapaxes(mlc, 0, 2)
        jaw = np.swapaxes(jaw, 0, 1)

        mosaiq_delivery_data = cls(monitor_units, gantry, collimator, mlc, jaw)

        return mosaiq_delivery_data
