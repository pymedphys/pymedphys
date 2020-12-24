# Copyright (C) 2020 Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import warnings

from pymedphys._imports import numpy as np
from pymedphys._imports import pandas as pd

from pymedphys._utilities import transforms as pmp_transforms

from . import _utilities

GANTRY_EXPECTED_SPEED_LIMIT = 1  # RPM
COLLIMATOR_EXPECTED_SPEED_LIMIT = 2.7  # RPM
NOISE_BUFFER_FACTOR = 5  # To allow a noisy point to not trigger the speed limit


def make_icom_angles_continuous(icom_datasets):
    try:
        angle_speed_check(icom_datasets)
    except ValueError:
        icom_datasets["gantry"] = attempt_to_make_angle_continuous(
            icom_datasets["datetime"],
            icom_datasets["gantry"].to_numpy(),
            GANTRY_EXPECTED_SPEED_LIMIT * NOISE_BUFFER_FACTOR,
        )
        icom_datasets["collimator"] = attempt_to_make_angle_continuous(
            icom_datasets["datetime"],
            icom_datasets["collimator"].to_numpy(),
            COLLIMATOR_EXPECTED_SPEED_LIMIT * NOISE_BUFFER_FACTOR,
        )

    angle_speed_check(icom_datasets)

    return icom_datasets


def fix_bipolar_angle(angle: "pd.Series"):
    output = angle.to_numpy()
    output[output < 0] = output[output < 0] + 360

    output = pmp_transforms.convert_IEC_angle_to_bipolar(output)

    return output


def determine_speed(angle, time):
    diff_angle = np.diff(angle) / 360
    diff_time = pd.Series(np.diff(time)).dt.total_seconds().to_numpy() / 60

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        rpm = diff_angle / diff_time

    return np.abs(rpm)


def get_collimator_and_gantry_flags(icom_datasets):
    gantry_rpm = determine_speed(icom_datasets["gantry"], icom_datasets["datetime"])
    collimator_rpm = determine_speed(
        icom_datasets["collimator"], icom_datasets["datetime"]
    )

    gantry_flag = gantry_rpm > GANTRY_EXPECTED_SPEED_LIMIT * NOISE_BUFFER_FACTOR
    gantry_flag = _utilities.expand_border_events(gantry_flag)

    collimator_flag = (
        collimator_rpm > COLLIMATOR_EXPECTED_SPEED_LIMIT * NOISE_BUFFER_FACTOR
    )
    collimator_flag = _utilities.expand_border_events(collimator_flag)

    return gantry_flag, collimator_flag


def angle_speed_check(icom_datasets):
    gantry_flag, collimator_flag = get_collimator_and_gantry_flags(icom_datasets)

    if np.any(gantry_flag):
        raise ValueError("The gantry angle is changing faster than should be possible.")

    if np.any(collimator_flag):
        raise ValueError(
            "The collimator angle is changing faster than should be possible."
        )


def attempt_to_make_angle_continuous(
    time: "pd.Series",
    angle,
    speed_limit,
    init_range_to_adjust=0,
    max_range=5,
    range_iter=0.1,
):
    if init_range_to_adjust > max_range:
        raise ValueError("The adjustment range was larger than the maximum")

    within_adjustment_range = np.abs(angle) >= 180 - init_range_to_adjust
    outside_adjustment_range = np.invert(within_adjustment_range)

    if not np.any(outside_adjustment_range):
        raise ValueError("No data outside the safe angle bounds.")

    index_within = np.where(within_adjustment_range)[0]
    index_outside = np.where(np.invert(within_adjustment_range))[0]

    where_closest_left_leaning = np.argmin(
        np.abs(index_within[:, None] - index_outside[None, :]), axis=1
    )

    closest_left_leaning = index_outside[where_closest_left_leaning]

    sign_to_be_adjusted = np.sign(angle[index_within]) != np.sign(
        angle[closest_left_leaning]
    )

    angles_to_be_adjusted = angle[index_within][sign_to_be_adjusted]
    angles_to_be_adjusted = angles_to_be_adjusted + 360 * np.sign(
        angle[closest_left_leaning][sign_to_be_adjusted]
    )

    angle[index_within[sign_to_be_adjusted]] = angles_to_be_adjusted

    rpm = determine_speed(angle, time)
    if np.any(rpm > speed_limit):
        angle = attempt_to_make_angle_continuous(
            time,
            angle,
            speed_limit,
            init_range_to_adjust=init_range_to_adjust + range_iter,
            max_range=max_range,
            range_iter=range_iter,
        )

    return angle
