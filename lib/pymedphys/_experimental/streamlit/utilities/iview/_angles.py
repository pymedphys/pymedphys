# Copyright (C) 2020 Cancer Care Associates and Simon Biggs

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""A module to account for the discontinuous bipolar angles within iCom.

A significant benefit of the bipolar coordinate system is that should
an angle extend past 180 degrees, say to 181 degrees, this is able to
be destinguished from -179 degrees. Even though, strictly speaking,
these are the same angle, 181 is able to be used to designate that it
is in the position from which it can travel CCW as opposed to CW. This
also means that by using the bipolar system, all time consecutive
angles provided are able to be sensibly interpolated linearly in order
to find the the angles between the two time steps.

The Elekta linac's TRF format does follow this bipolar convention. The
Elekta linac's iCom stream, at first glance appears to follow this
convention, however, unfortunately it does not. The iCom angle format
presents angles between -180 and 180 degrees. Should ever the angle
travel past 180 degrees it causes a sign flip in its representation
effectively throwing out information and making it so that linear
interpolation between these time steps would return nonsense.

This module aims to utilise knowledge about the maximum travel speed
for the collimator and the gantry in order to correct this sign flip.
"""


import warnings

from pymedphys._imports import altair as alt
from pymedphys._imports import numpy as np
from pymedphys._imports import pandas as pd
from pymedphys._imports import streamlit as st

from . import _utilities

GANTRY_EXPECTED_SPEED_LIMIT = 1  # RPM
COLLIMATOR_EXPECTED_SPEED_LIMIT = 2.7  # RPM

# To allow a noisy point to not trigger the speed limit. Given a sign
# flip occurring within data on the order of 4 Hz would result in an
# apparent RPM of 240, as long as the below factor times the expected
# speed limits above is significantly less than 240 this is sufficient.
NOISE_BUFFER_FACTOR = 5

assert NOISE_BUFFER_FACTOR * GANTRY_EXPECTED_SPEED_LIMIT < 60
assert NOISE_BUFFER_FACTOR * COLLIMATOR_EXPECTED_SPEED_LIMIT < 60


def make_icom_angles_continuous(icom_datasets, quiet=False):
    try:
        angle_speed_check(icom_datasets)
    except ValueError:
        icom_datasets["gantry"] = attempt_to_make_angles_continuous(
            icom_datasets["datetime"],
            icom_datasets["gantry"].to_numpy(),
            GANTRY_EXPECTED_SPEED_LIMIT * NOISE_BUFFER_FACTOR,
            quiet=quiet,
        )
        icom_datasets["collimator"] = attempt_to_make_angles_continuous(
            icom_datasets["datetime"],
            icom_datasets["collimator"].to_numpy(),
            COLLIMATOR_EXPECTED_SPEED_LIMIT * NOISE_BUFFER_FACTOR,
            quiet=quiet,
        )

    # angle_speed_check(icom_datasets)

    return icom_datasets


def determine_speed(angles, times):
    diff_angles = np.diff(angles) / 360
    diff_times = pd.Series(np.diff(times)).dt.total_seconds().to_numpy() / 60

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        rpm = diff_angles / diff_times

    return np.abs(rpm)


def get_gantry_and_collimator_flags(icom_datasets):
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
    gantry_flag, collimator_flag = get_gantry_and_collimator_flags(icom_datasets)

    if np.any(gantry_flag):
        raise ValueError("The gantry angle is changing faster than should be possible.")

    if np.any(collimator_flag):
        raise ValueError(
            "The collimator angle is changing faster than should be possible."
        )


def attempt_to_make_angles_continuous(
    times: "pd.Series",
    angles,
    speed_limit,
    init_range_to_adjust=0,
    max_range=5,
    range_iter=0.1,
    quiet=False,
):
    if init_range_to_adjust > max_range:
        if not quiet:
            st.error(
                "Unable to automatically convert the iCom data to bipolar. "
                "Below are some diagnostic outputs to help get to the "
                "root cause of the issue."
            )

            st.info(
                f"""
                iCom data is converted to bipolar by making an assumption
                that the angle movement is unable to go above a certain
                RPM. If this error has occurred it is because no sign
                adjustment combination for the provided data was able to
                be found that brings the RPM to less than `{speed_limit}`.
                Below is a plot of the provided data with the data coloured
                by its RPM.
                """
            )
            rpm = determine_speed(angles, times)
            df = pd.concat(
                [
                    times,
                    pd.Series(angles, name="angle"),
                    pd.Series(rpm, name="rpm"),
                ],
                axis=1,
            )
            st.write(df)

            chart = (
                alt.Chart(df)
                .mark_circle()
                .encode(
                    x="datetime:T",
                    y="angle:Q",
                    color="rpm:Q",
                    tooltip=["datetime", "angle", "rpm"],
                )
                .interactive(bind_y=False)
            )
            st.altair_chart(chart, use_container_width=True)

            st.error(
                "The WLutz analysis will now continue with this angle 'jump' "
                "in-place. Be aware that this brings into question the sign "
                "of the angle determination in the vicinity of the high RPM regions "
                "presented in the above plot."
            )
        return angles

    within_adjustment_range = np.abs(angles) >= 180 - init_range_to_adjust
    outside_adjustment_range = np.invert(within_adjustment_range)

    if not np.any(outside_adjustment_range):
        raise ValueError("No data outside the safe angle bounds.")

    index_within = np.where(within_adjustment_range)[0]
    index_outside = np.where(np.invert(within_adjustment_range))[0]

    where_closest_left_leaning = np.argmin(
        np.abs(index_within[:, None] - index_outside[None, :]), axis=1
    )

    closest_left_leaning = index_outside[where_closest_left_leaning]

    sign_to_be_adjusted = np.sign(angles[index_within]) != np.sign(
        angles[closest_left_leaning]
    )

    angles_to_be_adjusted = angles[index_within][sign_to_be_adjusted]
    angles_to_be_adjusted = angles_to_be_adjusted + 360 * np.sign(
        angles[closest_left_leaning][sign_to_be_adjusted]
    )

    angles[index_within[sign_to_be_adjusted]] = angles_to_be_adjusted

    rpm = determine_speed(angles, times)
    if np.any(rpm > speed_limit):
        if np.any(sign_to_be_adjusted):
            new_range_adjust = init_range_to_adjust
        else:
            new_range_adjust = init_range_to_adjust + range_iter

        angles = attempt_to_make_angles_continuous(
            times,
            angles,
            speed_limit,
            init_range_to_adjust=new_range_adjust,
            max_range=max_range,
            range_iter=range_iter,
            quiet=quiet,
        )

    return angles
