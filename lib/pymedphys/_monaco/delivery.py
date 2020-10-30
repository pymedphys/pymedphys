# Copyright (C) 2019 Cancer Care Associates and Simon Biggs

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import functools
import re

from pymedphys._imports import numpy as np

import pymedphys._base.delivery
import pymedphys._utilities.transforms

from . import utility


class DeliveryMonaco(
    pymedphys._base.delivery.DeliveryBase  # pylint: disable = protected-access
):
    @classmethod
    def from_monaco(cls, tel_path):
        read_tel_contents = utility.create_read_monaco_file()
        tel_contents = read_tel_contents(tel_path)

        return cls(*delivery_from_tel_plan_contents(tel_contents))


def delivery_from_tel_plan_contents(tel_contents):
    pattern = get_control_point_pattern()
    all_controlpoint_results = re.findall(pattern, tel_contents)

    mu = np.cumsum([float(result[4]) for result in all_controlpoint_results]).tolist()

    iec_gantry_angle = [float(result[2]) for result in all_controlpoint_results]
    bipolar_gantry_angle = pymedphys._utilities.transforms.convert_IEC_angle_to_bipolar(  # pylint: disable = protected-access
        iec_gantry_angle
    ).tolist()

    iec_coll_angle = [float(result[3]) for result in all_controlpoint_results]
    bipolar_coll_angle = pymedphys._utilities.transforms.convert_IEC_angle_to_bipolar(  # pylint: disable = protected-access
        iec_coll_angle
    ).tolist()

    mlcs = [convert_mlc_string(result[0]) for result in all_controlpoint_results]

    jaw_gap = np.array([float(result[5]) for result in all_controlpoint_results])
    jaw_field_centre = np.array(
        [float(result[6]) for result in all_controlpoint_results]
    )
    jaw_a = jaw_field_centre + jaw_gap / 2
    jaw_b = -(jaw_field_centre - jaw_gap / 2)
    jaws = np.vstack([jaw_a, jaw_b]).T.tolist()

    for i in range(len(mu) - 1, -1, -1):
        result = all_controlpoint_results[i]
        if result[1] == "2,2":  #  A nasty hack to attempt to find static fields
            if i == 0:
                mu = [0] + mu
            else:
                mu = mu[0:i] + [mu[i - 1]] + mu[i::]

            bipolar_gantry_angle = (
                bipolar_gantry_angle[0:i]
                + [bipolar_gantry_angle[i]]
                + bipolar_gantry_angle[i::]
            )

            bipolar_coll_angle = (
                bipolar_coll_angle[0:i]
                + [bipolar_coll_angle[i]]
                + bipolar_coll_angle[i::]
            )

            mlcs = mlcs[0:i] + [mlcs[i]] + mlcs[i::]
            jaws = jaws[0:i] + [jaws[i]] + jaws[i::]
        elif result[1] != "1,1":
            raise ValueError(
                "Detection for static or dynamic control points has fallen down"
            )

    return mu, bipolar_gantry_angle, bipolar_coll_angle, mlcs, jaws


def convert_mlc_string(mlc_string):
    mlcs = np.array(mlc_string.replace(" ", "").replace("\n", ",").split(",")).astype(
        float
    )
    mlcs = mlcs.reshape((80, 2))

    mlcs[:, 0] = -mlcs[:, 0]
    mlcs = np.fliplr(np.flipud(mlcs))

    return mlcs


@functools.lru_cache(maxsize=1)
def get_control_point_pattern():
    mlc_pos_pattern = r" *-?\d+\.\d+"
    ten_mlc_pos_pattern = ",".join([mlc_pos_pattern] * 10)
    sixteen_rows_of_mlcs_pattern = "\n".join([ten_mlc_pos_pattern] * 16)

    ones_or_twos = "\n".join([",".join([r"\d"] * 6)] * 13)

    decimal_param = r"-?\d+\.\d+"
    optional_decimal_param = r"-?\d+(?:\.\d+)?"

    parameters = (
        r"(\d,\d)"
        "\n"
        f"{decimal_param},({optional_decimal_param})\n"
        f"({optional_decimal_param})\n{decimal_param},{decimal_param},{decimal_param},{decimal_param}\n"
        f"({decimal_param}),{decimal_param},{decimal_param},{decimal_param}\n"
        f"{optional_decimal_param},({optional_decimal_param}),{optional_decimal_param},({optional_decimal_param})"
    )

    total_pattern = f"({sixteen_rows_of_mlcs_pattern})\n{ones_or_twos}\n{parameters}"

    return total_pattern
