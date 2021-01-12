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

from pymedphys._imports import numpy as np
from pymedphys._imports import pandas as pd
from pymedphys._imports import plt
from pymedphys._imports import streamlit as st

from pymedphys._streamlit import categories
from pymedphys._streamlit.utilities import config as _config

from pymedphys._experimental.streamlit.apps.wlutz import _utilities
from pymedphys._experimental.wlutz import transformation as _transformation

CATEGORY = categories.PLANNING
TITLE = "WLutz Collimator Processing"

DEFAULT_OPPOSING_COLLIMATOR_TOLERANCE = 5  # degrees
DEFAULT_AGREEING_GANTRY_TOLERANCE = 10  # degrees


def main():
    config = _config.get_config()
    (
        _,
        _,
        wlutz_directory_by_date,
        _,
        _,
        _,
    ) = _utilities.get_directories_and_initial_database(config, refresh_cache=False)

    raw_results_csv_path = wlutz_directory_by_date.joinpath("raw_results.csv")

    st.write(f"`{raw_results_csv_path}`")

    try:
        dataframe = _get_results(raw_results_csv_path)
    except FileNotFoundError:
        st.error("Winston Lutz results not yet calculated/saved for this date.")
        st.stop()

    dataframe["x_centre"] = np.mean(dataframe[["x_lower", "x_upper"]], axis=1)
    dataframe["y_centre"] = np.mean(dataframe[["y_lower", "y_upper"]], axis=1)

    algorithm = "PyMedPhys"
    dataframe_by_algorithm = _filter_by(dataframe, "algorithm", algorithm)

    # st.write(dataframe)

    treatments = dataframe_by_algorithm["treatment"].unique()
    # st.write(treatments)

    treatment = st.radio("Treatment", list(treatments))
    # st.write(treatment)

    dataframe_by_treatment = _filter_by(dataframe_by_algorithm, "treatment", treatment)
    dataframe_by_treatment.reset_index(inplace=True)
    st.write(dataframe_by_treatment)

    collimator = np.array(dataframe_by_treatment["collimator"])
    gantry = np.array(dataframe_by_treatment["gantry"])
    opposing_indices = _find_index_of_opposing_images(gantry, collimator)

    fig, ax = plt.subplots()
    ax.plot(
        gantry,
        dataframe_by_treatment["x_centre"],
        "o-",
        alpha=0.7,
        label="MLC logfile centre",
    )
    ax.plot(
        gantry,
        dataframe_by_treatment["y_centre"],
        "o-",
        alpha=0.7,
        label="Jaw logfile centre",
    )
    plt.legend()
    st.pyplot(fig)

    # TODO: Create tests of this logic utilising the test fields created
    # on the 2021-01-07 on 2619.

    (
        adjusted_x_deviation,
        adjusted_y_deviation,
    ) = _determine_logfile_corrected_deviations(
        dataframe_by_treatment["x_centre"],
        dataframe_by_treatment["y_centre"],
        collimator,
        dataframe_by_treatment["diff_x"],
        dataframe_by_treatment["diff_y"],
    )
    dataframe_by_treatment["diff_x_logfile_corrected"] = adjusted_x_deviation
    dataframe_by_treatment["diff_y_logfile_corrected"] = adjusted_y_deviation

    for axis in ["x", "y"]:
        _make_coll_corrected_plots(
            dataframe_by_treatment, axis, ["", "_logfile_corrected"]
        )

    corrections = []
    for i, row in dataframe_by_treatment.iterrows():
        opposing_index = opposing_indices[i]

        if not np.isnan(opposing_index):
            assert opposing_index == int(opposing_index)
            opposing_index = int(opposing_index)

            diff_point = (
                row["diff_x_logfile_corrected"],
                row["diff_y_logfile_corrected"],
            )
            collimator = row["collimator"]
            opposing_row = dataframe_by_treatment.iloc[opposing_index]
            opposing_diff_point = (
                opposing_row["diff_x_logfile_corrected"],
                opposing_row["diff_y_logfile_corrected"],
            )
            opposing_collimator = opposing_row["collimator"]

            rotated = _transformation.rotate_point(diff_point, collimator)
            opposed_rotated = _transformation.rotate_point(
                opposing_diff_point, opposing_collimator + 180
            )

            stacked = np.vstack([rotated, opposed_rotated])
            avg = np.mean(stacked, axis=0)
            correction = avg - rotated
        else:
            correction = [np.nan, np.nan]

        corrections.append(correction)

    corrections = np.array(corrections)

    dataframe_by_treatment["diff_x_predicted_coll_correction"] = corrections[:, 0]
    dataframe_by_treatment["diff_y_predicted_coll_correction"] = corrections[:, 1]

    median_correction = np.nanmedian(corrections, axis=0)
    st.write(median_correction)

    # TODO: Do the above for all treatment combinations, then find the
    # median over all treatments.

    corrected_diffs = []
    for i, row in dataframe_by_treatment.iterrows():
        collimator = row["collimator"]
        rotated_correction = _transformation.rotate_point(
            median_correction, -collimator
        )

        corrected_diff = (
            np.array((row["diff_x_logfile_corrected"], row["diff_y_logfile_corrected"]))
            + rotated_correction
        )
        corrected_diffs.append(corrected_diff)

    corrected_diffs = np.array(corrected_diffs)
    dataframe_by_treatment["diff_x_coll_corrected"] = corrected_diffs[:, 0]
    dataframe_by_treatment["diff_y_coll_corrected"] = corrected_diffs[:, 1]

    st.write(dataframe_by_treatment[["gantry", "diff_x", "collimator"]])

    for axis in ["x", "y"]:
        _make_coll_corrected_plots(
            dataframe_by_treatment,
            axis,
            ["_logfile_corrected", "_coll_corrected"]
            # ["coll_corrected"],
        )
        _make_coll_correction_prediction_plots(dataframe_by_treatment, axis)

    original = _transform_points_to_field_reference_frame(
        dataframe_by_treatment, ["diff_x", "diff_y"]
    )
    logfile_corrected = _transform_points_to_field_reference_frame(
        dataframe_by_treatment, ["diff_x_logfile_corrected", "diff_y_logfile_corrected"]
    )
    coll_corrected = _transform_points_to_field_reference_frame(
        dataframe_by_treatment, ["diff_x_coll_corrected", "diff_y_coll_corrected"]
    )

    fig, ax = plt.subplots()
    ax.plot(gantry, original[:, 0], "o-", alpha=0.3)
    ax.plot(gantry, logfile_corrected[:, 0], "o-", alpha=0.3)
    st.pyplot(fig)

    fig, ax = plt.subplots()
    ax.plot(gantry, original[:, 1], "o-", alpha=0.3)
    ax.plot(gantry, logfile_corrected[:, 1], "o-", alpha=0.3)
    st.pyplot(fig)

    st.write(median_correction[0])
    fig, ax = plt.subplots()
    ax.set_title("MLC, logfile -> coll")
    ax.plot(gantry, logfile_corrected[:, 0], "o-", alpha=0.3)
    ax.plot(gantry, coll_corrected[:, 0], "o-", alpha=0.3)
    st.pyplot(fig)

    st.write(median_correction[1])
    fig, ax = plt.subplots()
    ax.set_title("Jaw, logfile -> coll")
    ax.plot(gantry, logfile_corrected[:, 1], "o-", alpha=0.3)
    ax.plot(gantry, coll_corrected[:, 1], "o-", alpha=0.3)
    st.pyplot(fig)


def _transform_points_to_field_reference_frame(dataframe, point_columns):
    field_frame_points = []
    for _, row in dataframe.iterrows():
        collimator = row["collimator"]
        # if collimator <= 0:
        #     collimator += 180
        point = row[point_columns]
        field_frame_point = _transformation.rotate_point(point, collimator)
        field_frame_points.append(field_frame_point)

    field_frame_points = np.array(field_frame_points)

    return field_frame_points


def _make_coll_corrected_plots(dataframe, axis, correction_types):
    gantry = np.array(dataframe["gantry"])
    collimator = np.array(dataframe["collimator"])
    original_column = f"diff_{axis}"

    fig, ax = plt.subplots()
    ax.set_title(f"Field - BB on iView {axis} axis")
    # ax.plot(gantry, dataframe[original_column], "o-", alpha=0.3, label=original_column)

    for correction_type in correction_types:
        corrected_column = f"{original_column}{correction_type}"
        ax.plot(
            gantry,
            # collimator,
            dataframe[corrected_column],
            "o-",
            alpha=0.3,
            label=corrected_column,
        )
    ax.legend()
    ax.set_xlabel("Gantry angle (degrees)")
    ax.set_ylabel(f"Field - BB [iView {axis} axis] (mm)")
    st.pyplot(fig)


def _make_coll_correction_prediction_plots(dataframe, axis):
    gantry = np.array(dataframe["gantry"])
    column = f"diff_{axis}_predicted_coll_correction"

    fig, ax = plt.subplots()
    ax.set_title(f"Predicted collimator correction along {axis}-axis of rotated field")
    ax.plot(gantry, dataframe[column], "o", alpha=0.3, label=column)
    ax.set_xlabel("Gantry angle (degrees)")
    ax.set_ylabel(f"{axis} axis predicted collimator correction (mm)")
    ax.legend()
    st.pyplot(fig)


def _get_results(filepath) -> "pd.DataFrame":
    raw_results_dataframe = pd.read_csv(filepath)

    return raw_results_dataframe


# def _filter_by_column(dataframe, column):
#     options = list(dataframe[column].unique())
#     selected = st.radio(column, options)
#     filtered = dataframe.loc[dataframe[column] == selected]

#     return filtered


def _filter_by(dataframe, column, value):
    filtered = dataframe.loc[dataframe[column] == value]

    return filtered


def _determine_logfile_corrected_deviations(
    icom_x_centres, icom_y_centres, collimator_angles, x_deviations, y_deviations
):
    adjusted_x_deviation = []
    adjusted_y_deviation = []

    st.write(icom_x_centres)

    corrections_to_apply = []
    for (icom_x_centre, icom_y_centre, collimator) in zip(
        icom_x_centres, icom_y_centres, collimator_angles
    ):
        icom_correction_in_collimator_coordinates = -np.array(
            [icom_x_centre, icom_y_centre]
        )
        icom_correction_in_world_coordinates = _transformation.rotate_point(
            icom_correction_in_collimator_coordinates, -collimator
        )
        corrections_to_apply.append(icom_correction_in_world_coordinates)

    corrections_to_apply = np.array(corrections_to_apply)
    adjusted_x_deviation = x_deviations + corrections_to_apply[:, 0]
    adjusted_y_deviation = y_deviations + corrections_to_apply[:, 1]

    return adjusted_x_deviation, adjusted_y_deviation


def _estimate_collimator_rotation_correction(
    grouping_labels, gantry_angles, collimator_angles, x_deviations, y_deviations
):
    pass


def _determine_predicted_collimator_rotation_correction_for_opposing_pairs(
    gantry_angles, collimator_angles, x_deviations, y_deviations
):
    """Must only be provided a set of data from a single delivery where
    the beam position is expected to be relatively equivalent. ie, don't
    provide data from different beam energies or beam dose rates.
    """
    pass


def _find_index_of_opposing_images(
    gantry_angles,
    collimator_angles,
    opposing_collimator_tolerance=DEFAULT_OPPOSING_COLLIMATOR_TOLERANCE,
    agreeing_gantry_tolerance=DEFAULT_AGREEING_GANTRY_TOLERANCE,
):
    gantry_mod = np.mod(gantry_angles[:, None] - gantry_angles[None, :], 360)
    coll_mod = np.mod(
        collimator_angles[:, None] - collimator_angles[None, :] + 180, 360
    )

    coll_combined = np.concatenate([coll_mod, coll_mod.T, coll_mod, coll_mod.T], axis=1)
    gantry_combined = np.concatenate(
        [gantry_mod, gantry_mod, gantry_mod.T, gantry_mod.T], axis=1
    )
    combined = coll_combined + gantry_combined

    index_of_min = np.argmin(combined, axis=1)
    min_coll_values = np.take_along_axis(coll_combined, index_of_min[:, None], axis=1)
    min_gantry_values = np.take_along_axis(
        gantry_combined, index_of_min[:, None], axis=1
    )

    out_of_tolerance = np.logical_or(
        min_coll_values > opposing_collimator_tolerance,
        min_gantry_values > agreeing_gantry_tolerance,
    )

    assert out_of_tolerance.shape[1] == 1
    assert len(out_of_tolerance.shape) == 2

    out_of_tolerance = out_of_tolerance[:, 0]

    opposing_indices = np.mod(index_of_min, len(gantry_angles))
    opposing_indices = opposing_indices.astype(float)
    opposing_indices[out_of_tolerance] = np.nan

    return opposing_indices
