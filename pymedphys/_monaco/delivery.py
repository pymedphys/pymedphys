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


class DeliveryMonaco(
    pymedphys._base.delivery.DeliveryBase  # pylint: disable = protected-access
):
    @classmethod
    def from_monaco(cls, tel_path):
        read_trf_contents = create_read_trf_contents()
        tel_contents = read_trf_contents(tel_path)

        return cls(*delivery_from_tel_plan_contents(tel_contents))


def delivery_from_tel_plan_contents(tel_contents):
    pattern = get_control_point_pattern()
    all_controlpoint_results = re.findall(pattern, tel_contents)

    mu = np.cumsum([float(result[3]) for result in all_controlpoint_results])

    iec_gantry_angle = [float(result[1]) for result in all_controlpoint_results]
    bipolar_gantry_angle = pymedphys._utilities.transforms.convert_IEC_angle_to_bipolar(  # pylint: disable = protected-access
        iec_gantry_angle
    )

    iec_coll_angle = [float(result[2]) for result in all_controlpoint_results]
    bipolar_coll_angle = pymedphys._utilities.transforms.convert_IEC_angle_to_bipolar(  # pylint: disable = protected-access
        iec_coll_angle
    )

    mlcs = [convert_mlc_string(result[0]) for result in all_controlpoint_results]

    jaw_gap = np.array([float(result[4]) for result in all_controlpoint_results])
    jaw_field_centre = np.array(
        [float(result[5]) for result in all_controlpoint_results]
    )
    jaw_a = jaw_field_centre + jaw_gap / 2
    jaw_b = -(jaw_field_centre - jaw_gap / 2)
    jaws = np.vstack([jaw_a, jaw_b]).T

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
    mlc_pos_pattern = r" *-?\d+\.\d"
    ten_mlc_pos_pattern = ",".join([mlc_pos_pattern] * 10)
    sixteen_rows_of_mlcs_pattern = "\n".join([ten_mlc_pos_pattern] * 16)

    weird_ones = "\n".join([",".join(["1"] * 6)] * 13)

    decimal_param = r"-?\d+\.\d+"
    optional_decimal_param = r"-?\d+(?:\.\d+)?"

    parameters = (
        "1,1\n"
        f"{decimal_param},({optional_decimal_param})\n"
        f"({optional_decimal_param})\n{decimal_param},{decimal_param},{decimal_param},{decimal_param}\n"
        f"({decimal_param}),{decimal_param},{decimal_param},{decimal_param}\n"
        f"{optional_decimal_param},({optional_decimal_param}),{optional_decimal_param},({optional_decimal_param})"
    )

    total_pattern = f"({sixteen_rows_of_mlcs_pattern})\n{weird_ones}\n{parameters}"

    return total_pattern


@functools.lru_cache(maxsize=1)
def create_read_trf_contents():

    try:
        import win32file  # pylint: disable = import-error

        has_win32file = True
    except ImportError:
        has_win32file = False

    if has_win32file:
        import os
        import msvcrt  # pylint: disable = import-error

        def read_trf_contents(filepath):
            handle = win32file.CreateFile(
                str(filepath),
                win32file.GENERIC_READ,
                win32file.FILE_SHARE_DELETE
                | win32file.FILE_SHARE_READ
                | win32file.FILE_SHARE_WRITE,
                None,
                win32file.OPEN_EXISTING,
                0,
                None,
            )

            detached_handle = handle.Detach()

            file_descriptor = msvcrt.open_osfhandle(detached_handle, os.O_RDONLY)

            with open(file_descriptor) as file:
                data = file.read()

            return data

    else:

        def read_trf_contents(filepath):
            with open(filepath, "r") as file:
                data = file.read()

            return data

    return read_trf_contents
