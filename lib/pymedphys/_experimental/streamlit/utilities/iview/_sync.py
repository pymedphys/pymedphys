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
import datetime

from pymedphys._imports import altair as alt
from pymedphys._imports import numpy as np
from pymedphys._imports import pandas as pd
from pymedphys._imports import scipy
from pymedphys._imports import streamlit as st

from pymedphys._experimental.streamlit.utilities import icom as _icom


def icom_iview_timestamp_alignment(
    database_table,
    icom_patients_directory,
    selected_date,
    selected_machine_id,
    advanced_mode,
    quiet=False,
):
    if not quiet:
        st.write("## iView to iCom timestamp alignment")

        st.write(icom_patients_directory)

    if not icom_patients_directory.exists():
        st.error(
            f"The iCom patient directory of `{icom_patients_directory}` "
            "provided within the config file doesn't exist."
        )
        st.stop()

    selected_paths_by_date = _icom.get_paths_by_date(
        icom_patients_directory, selected_date=selected_date
    )

    all_relevant_times = _icom.get_relevant_times_for_filepaths(
        selected_paths_by_date["filepath"]
    )

    try:
        relevant_times = all_relevant_times[selected_machine_id]
    except KeyError:
        st.write(selected_machine_id)
        st.write(all_relevant_times)
        raise

    min_iview_datetime = (np.min(database_table["datetime"])).floor("min")
    max_iview_datetime = (np.max(database_table["datetime"])).ceil("min")

    time_step = datetime.timedelta(minutes=1)
    min_icom_datetime = (np.min(relevant_times["datetime"])).floor("min")
    max_icom_datetime = (np.max(relevant_times["datetime"])).ceil("min")

    buffer = datetime.timedelta(minutes=30)
    init_min_time = np.max([min_iview_datetime - buffer, min_icom_datetime])
    init_max_time = np.min([max_iview_datetime + buffer, max_icom_datetime])

    initial_region = [init_min_time.time(), init_max_time.time()]

    if advanced_mode:
        icom_time_range = st.slider(
            "iCom alignment range",
            min_value=min_icom_datetime.time(),
            max_value=max_icom_datetime.time(),
            step=time_step,
            value=initial_region,
        )
    else:
        icom_time_range = initial_region

    time = relevant_times["datetime"].dt.time
    icom_lookup_mask = (time >= icom_time_range[0]) & (time <= icom_time_range[1])
    time_filtered_icom_times = relevant_times.loc[icom_lookup_mask]

    if advanced_mode:
        _icom.plot_relevant_times(
            time_filtered_icom_times,
            step=1,
            title="iCom | Timesteps with recorded meterset",
        )

        _icom.plot_relevant_times(
            database_table, step=1, title="iView | Timesteps with recorded image frames"
        )

    iview_datetimes = pd.Series(database_table["datetime"], name="datetime")

    icom_datetimes = pd.Series(time_filtered_icom_times["datetime"], name="datetime")

    loop_offset, loop_minimise_f = _determine_loop_offset(
        iview_datetimes, icom_datetimes
    )
    basinhopping_offset, basinhopping_minimise_f = _determine_basinhopping_offset(
        iview_datetimes, icom_datetimes
    )

    if loop_minimise_f > basinhopping_minimise_f:
        offset_to_apply = basinhopping_offset
        offset_used = "basinhopping"
    else:
        offset_to_apply = loop_offset
        offset_used = "loop"

    if not quiet:
        st.write(
            f"""
                Offset estimation undergone with two approaches. The offset
                from the `{offset_used}` approach was utilised. The offset
                required to align the iCom timestamps to the iView
                timestamps was determined to be
                `{round(offset_to_apply, 1)}` s.

                * Basinhopping offset: `{round(basinhopping_offset, 2)}`
                * Minimiser `{round(basinhopping_minimise_f, 4)}`
                * Loop offset: `{round(loop_offset, 2)}`
                * Minimiser `{round(loop_minimise_f, 4)}`
            """
        )

    if np.abs(basinhopping_offset - loop_offset) > 1:
        st.error(
            "The time offset methods disagree by more than 1 second. "
            "Offset alignment accuracy can be improved by either "
            "decreasing the time of capture between consecutive imaging "
            "frames (such as provided "
            "by movie mode) or by adjusting the clocks on both the "
            "iView and the NRT so that the expected deviation between "
            "them is less than the time between consecutive images."
        )

    usable_icom_times = relevant_times.copy()
    usable_icom_times["datetime"] += datetime.timedelta(seconds=offset_to_apply)

    time = usable_icom_times["datetime"].dt.time
    adjusted_buffer = datetime.timedelta(seconds=30)
    adjusted_icom_lookup_mask = (
        time >= (min_iview_datetime - adjusted_buffer).time()
    ) & (time <= (max_iview_datetime + adjusted_buffer).time())
    usable_icom_times = usable_icom_times.loc[adjusted_icom_lookup_mask]

    if advanced_mode:
        _icom.plot_relevant_times(
            usable_icom_times, step=1, title=f"iCom | With {offset_used} offset applied"
        )

    time_diffs = _get_time_diffs(iview_datetimes, usable_icom_times["datetime"])
    time_diffs = pd.concat([iview_datetimes, time_diffs], axis=1)
    time_diffs["time"] = time_diffs["datetime"].dt.time

    if advanced_mode:
        raw_chart = (
            alt.Chart(time_diffs)
            .mark_circle()
            .encode(
                x=alt.X("datetime", axis=alt.Axis(title="iView timestamp")),
                y=alt.Y(
                    "time_diff",
                    axis=alt.Axis(title="Time diff [iView - Adjusted iCom] (s)"),
                ),
                tooltip=["time:N", "time_diff"],
            )
        ).properties(
            title="Time displacement between iView image timestamp and closest iCom record"
        )

        st.altair_chart(altair_chart=raw_chart, use_container_width=True)

    max_diff = np.max(np.abs(time_diffs["time_diff"]))

    if not quiet:
        st.write(
            "The maximum deviation between an iView frame and the closest "
            f"adjusted iCom timestep was found to be "
            f"`{round(max_diff, 1)}` s."
        )

    filepaths_to_load = usable_icom_times["filepath"].unique()

    if max_diff > 5:
        if advanced_mode:
            st.error(
                "This maximum deviation is significantly larger than "
                "should occur. Please adjust the "
                "**iCom alignment range** time slider above."
            )
            st.stop()
        else:
            st.error(
                "This maximum deviation is significantly larger than "
                "should occur. This alignment utility is being "
                "forcibly swapped into advanced mode in order to "
                "manually adjust the time alignment window.\n\n"
                "Please use the **iCom alignment range** time slider "
                "below to select the time window where the iView "
                "images were captured."
            )
            filepaths_to_load, offset_to_apply = icom_iview_timestamp_alignment(
                database_table,
                icom_patients_directory,
                selected_date,
                selected_machine_id,
                advanced_mode=True,
            )

    return filepaths_to_load, offset_to_apply


def _create_icom_timestamp_minimiser(iview_datetimes, icom_datetimes):
    def _icom_timestamp_minimiser(seconds):
        deviation_to_apply = datetime.timedelta(seconds=seconds[0])
        adjusted_icom_datetimes = icom_datetimes + deviation_to_apply

        return _get_mean_of_square_diffs(iview_datetimes, adjusted_icom_datetimes) * 10

    return _icom_timestamp_minimiser


def _get_mean_of_square_diffs(iview_datetimes, icom_datetimes):
    time_diffs = _get_time_diffs(iview_datetimes, icom_datetimes)
    return np.mean(np.square(time_diffs))


def _get_mean_based_offset(iview_datetimes, icom_datetimes):
    time_diffs = _get_time_diffs(iview_datetimes, icom_datetimes)
    new_offset = np.mean(time_diffs)

    return datetime.timedelta(seconds=new_offset)


def _get_time_diffs(iview_datetimes, icom_datetimes):
    iview_datetimes = np.array(iview_datetimes)[:, None]
    icom_datetimes = np.array(icom_datetimes)[None, :]

    all_time_diffs = iview_datetimes - icom_datetimes

    time_diffs_pairs_index = np.argmin(np.abs(all_time_diffs), axis=1)
    max_time_diffs = np.take_along_axis(
        all_time_diffs, time_diffs_pairs_index[:, None], axis=1
    )

    if max_time_diffs.shape[1] != 1:
        raise ValueError("Expected last dimension to have collapsed")

    max_time_diffs = max_time_diffs[:, 0]

    alignment_time_diffs = pd.Series(
        max_time_diffs, name="time_diff"
    ).dt.total_seconds()

    return alignment_time_diffs


@st.cache
def _estimated_initial_deviation_to_apply(iview_datetimes, icom_datetimes):
    alignment_time_diffs = _get_time_diffs(iview_datetimes, icom_datetimes)

    sign_to_apply = np.sign(np.sum(alignment_time_diffs))
    deviation_to_apply = sign_to_apply * np.max(sign_to_apply * alignment_time_diffs)

    return datetime.timedelta(seconds=deviation_to_apply)


@st.cache
def _determine_basinhopping_offset(iview_datetimes, icom_datetimes):
    initial_deviation_to_apply = _estimated_initial_deviation_to_apply(
        iview_datetimes, icom_datetimes
    )

    to_minimise = _create_icom_timestamp_minimiser(iview_datetimes, icom_datetimes)
    result = scipy.optimize.basinhopping(
        to_minimise,
        [initial_deviation_to_apply.total_seconds()],
        T=1,
        niter=1000,
        niter_success=100,
        stepsize=10,
    )

    basinhopping_offset = result.x[0]
    basinhopping_minimise_f = to_minimise(result.x)

    return basinhopping_offset, basinhopping_minimise_f


@st.cache
def _determine_loop_offset(iview_datetimes, icom_datetimes):
    to_minimise = _create_icom_timestamp_minimiser(iview_datetimes, icom_datetimes)
    total_offset = datetime.timedelta(seconds=0)

    initial_deviation_to_apply = _estimated_initial_deviation_to_apply(
        iview_datetimes, icom_datetimes
    )
    total_offset += initial_deviation_to_apply
    icom_datetimes = icom_datetimes + initial_deviation_to_apply

    absolute_total_seconds_applied = np.abs(initial_deviation_to_apply.total_seconds())

    while absolute_total_seconds_applied > 0.00001:
        deviation_to_apply = _get_mean_based_offset(iview_datetimes, icom_datetimes)
        total_offset += deviation_to_apply
        icom_datetimes = icom_datetimes + deviation_to_apply

        absolute_total_seconds_applied = np.abs(deviation_to_apply.total_seconds())

    loop_offset = total_offset.total_seconds()
    loop_minimise_f = to_minimise([loop_offset])

    return loop_offset, loop_minimise_f
