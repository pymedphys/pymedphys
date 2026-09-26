# Copyright (C) 2026 Matthew Jennings
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


"""Uses Mosaiq SQL to extract patient delivery details."""

import functools

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


def decode_msq_mlc(raw_bytes, leaf_count):
    """Convert one bank's Mosaiq leaf sets to leaf positions in cm.

    Mosaiq stores a bank's leaf positions for each control point as a
    fixed-width binary record of little-endian signed 16-bit integers in
    units of 0.01 cm. Only the first ``leaf_count`` values are in use; the
    rest of the record is padding.

    Parameters
    ----------
    raw_bytes : sequence of bytes
        One record per control point, as the database returns them. Do not
        convert them to a NumPy ``bytes`` array first: that strips trailing
        zero bytes, which can be part of the last leaf positions.
    leaf_count : int
        The number of leaves in the bank (``TxFieldPoint.MLC_Leaves``).

    Returns
    -------
    numpy.ndarray
        Leaf positions in cm, with shape (control points, leaves).
    """
    leaf_count = int(leaf_count)
    if leaf_count < 0:
        raise ValueError(f"MLC_Leaves must not be negative, got {leaf_count}.")

    positions = np.empty((len(raw_bytes), leaf_count))
    for control_point, record in enumerate(raw_bytes):
        record = b"" if record is None else bytes(record)
        if len(record) < 2 * leaf_count:
            raise ValueError(
                f"A leaf set holds {len(record)} bytes, fewer than the "
                f"{2 * leaf_count} bytes needed for {leaf_count} leaves."
            )
        positions[control_point] = np.frombuffer(record, dtype="<i2", count=leaf_count)

    return positions / 100


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
            TxFieldPoint.Coll_Y2,
            TxFieldPoint.MLC_Leaves
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
            "MLC_Leaves",
        ],
    )

    return meterset, txfieldpoint_results


class DeliveryMosaiq(DeliveryBase):
    @classmethod
    def from_mosaiq(cls, connection, field_id):
        total_mu, tx_field_points = delivery_data_sql(connection, field_id)
        total_mu = float(np.asarray(total_mu).item())

        leaf_counts = tx_field_points["MLC_Leaves"].unique()
        if len(leaf_counts) != 1:
            raise ValueError(
                "Every control point of a field should have the same "
                f"MLC_Leaves, but found {sorted(leaf_counts)}."
            )

        index = tx_field_points["Index"].to_numpy(dtype=float)
        mlc_a = decode_msq_mlc(tx_field_points["A_Leaf_Set"].tolist(), leaf_counts[0])
        mlc_b = decode_msq_mlc(tx_field_points["B_Leaf_Set"].tolist(), leaf_counts[0])
        msq_gantry_angle = tx_field_points["Gantry_Ang"].to_numpy(dtype=float)
        msq_collimator_angle = tx_field_points["Coll_Ang"].to_numpy(dtype=float)
        coll_y1 = tx_field_points["Coll_Y1"].to_numpy(dtype=float)
        coll_y2 = tx_field_points["Coll_Y2"].to_numpy(dtype=float)

        if len(index) == 1:
            # A static field has a single point. Deliver its whole meterset
            # between two copies of that point.
            monitor_units = [0.0, total_mu]
            mlc_a, mlc_b = (np.repeat(bank, 2, axis=0) for bank in (mlc_a, mlc_b))
            msq_gantry_angle, msq_collimator_angle, coll_y1, coll_y2 = (
                np.repeat(values, 2)
                for values in (msq_gantry_angle, msq_collimator_angle, coll_y1, coll_y2)
            )
        else:
            # Index is the cumulative meterset, as a percentage of the total.
            if index[-1] <= 0 or np.any(np.diff(index) < 0):
                raise ValueError(
                    "TxFieldPoint.Index should be non-decreasing and end above "
                    f"zero, but was {index.tolist()}."
                )
            monitor_units = ((index - index[0]) / index[-1] * total_mu).tolist()

        mlc_a = mlc_a.T
        mlc_b = mlc_b.T

        mlc, jaw = collimation_to_bipolar_mm(mlc_a, mlc_b, coll_y1, coll_y2)
        gantry = convert_IEC_angle_to_bipolar(msq_gantry_angle)
        collimator = convert_IEC_angle_to_bipolar(msq_collimator_angle)

        # TODO Tidy up this axis swap
        mlc = np.swapaxes(mlc, 0, 2)
        jaw = np.swapaxes(jaw, 0, 1)

        mosaiq_delivery_data = cls(monitor_units, gantry, collimator, mlc, jaw)

        return mosaiq_delivery_data
