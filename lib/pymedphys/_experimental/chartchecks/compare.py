# Copyright (C) 2020 Jacob Rembish

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

from pymedphys._imports import numpy as np
from pymedphys._imports import pandas as pd

#######################################################################################################################


# Summary: Define a function which assigns color values depending on whether or not the values between systems match.
# Input: Table of values which you wish to compare.
# Results:    match = green
#             mismatch = red
#             uncomparable = yellow


def colour_results(val):  # pylint: disable = too-many-return-statements
    not_in = [
        "field_type",
        "machine",
        "rx",
        "technique",
        "tolerance",
        "modality",
        "technique",
        "couch_lat [cm]",
        "couch_lng [cm]",
        "couch_vrt [cm]",
    ]

    # set any values which cannot accurately be compared as yellow (#FDFF8A)
    if val.name in not_in:
        return ["background-color: #FDFF8A", "background-color: #FDFF8A"]

    # begin comparing everything else, if they match make green (#C1FFC1), else red (#EE6363)
    elif isinstance(val[0], str) and isinstance(val[1], str):
        if val[0].lower() == val[1].lower():
            return ["background-color: #C1FFC1", "background-color: #C1FFC1"]
        else:
            return ["background-color: #EE6363", "background-color: #EE6363"]

    elif str(val[0]).strip() == "":
        val[0] = 0
        if val[0] == val[1]:
            return ["background-color: #C1FFC1", "background-color: #C1FFC1"]
        else:
            return ["background-color: #EE6363", "background-color: #EE6363"]
    elif str(val[1]).strip() == "":
        val[1] = 0
        if val[0] == val[1]:
            return ["background-color: #C1FFC1", "background-color: #C1FFC1"]
        else:
            return ["background-color: #EE6363", "background-color: #EE6363"]

    elif val[0] is None:
        val[0] = 0
        if val[0] == val[1]:
            return ["background-color: #C1FFC1", "background-color: #C1FFC1"]
        else:
            return ["background-color: #EE6363", "background-color: #EE6363"]

    elif val[1] is None:
        val[1] = 0
        if val[0] == val[1]:
            return ["background-color: #C1FFC1", "background-color: #C1FFC1"]
        else:
            return ["background-color: #EE6363", "background-color: #EE6363"]

    elif isinstance(val[0], datetime.date) or isinstance(val[1], datetime.date):
        if val[0] == val[1]:
            return ["background-color: #C1FFC1", "background-color: #C1FFC1"]
        else:
            return ["background-color: #EE6363", "background-color: #EE6363"]

    elif isinstance(val[0], float) and isinstance(val[1], str):
        if val[0] == val[1]:
            return ["background-color: #C1FFC1", "background-color: #C1FFC1"]
        else:
            return ["background-color: #EE6363", "background-color: #EE6363"]

    else:
        if np.round(float(val[0]), 2) == np.round(float(val[1]), 2):
            val[0] = np.round(float(val[0]), 2)
            val[1] = np.round(float(val[1]), 2)
            return ["background-color: #C1FFC1", "background-color: #C1FFC1"]
        else:
            return ["background-color: #EE6363", "background-color: #EE6363"]


#######################################################################################################################

# """
# Summary: Define a function which collects general prescription information for a patient.
# Results: Creates a pandas dataframe with 2 columns (one Dicom, one Mosaiq) for each prescription.
# """


def get_general_info(dicom_table, mos_table):
    mosaiq_table = []
    dic_table = []
    general_info_data = []
    used_prescriptions = []
    general_info_index = []

    general_info_columns = [
        "mrn",
        "first_name",
        "last_name",
        "site",
        "total_dose",
        "fraction_dose",
        "fractions",
        "target",
    ]

    for field in dicom_table["field_label"]:
        if dicom_table.iloc[int(field) - 1]["dose_reference"] not in used_prescriptions:
            for label in general_info_columns:
                mosaiq_table.append(mos_table.iloc[int(field) - 1][label])
                dic_table.append(dicom_table.iloc[int(field) - 1][label])
            general_info_index.append(
                "Prescription "
                + str(dicom_table.iloc[int(field) - 1]["dose_reference"])
                + " DICOM"
            )
            general_info_index.append(
                "Prescription "
                + str(dicom_table.iloc[int(field) - 1]["dose_reference"])
                + " Mosaiq"
            )
            used_prescriptions.append(
                dicom_table.iloc[int(field) - 1]["dose_reference"]
            )
            general_info_data.append(dic_table)
            general_info_data.append(mosaiq_table)
            dic_table = []
            mosaiq_table = []
        else:
            pass

    general_info_df = pd.DataFrame(data=general_info_data, columns=general_info_columns)

    general_info_df["dose_index"] = pd.Series(general_info_index).values
    general_info_df = general_info_df.set_index("dose_index", drop=True)
    general_info_df = general_info_df.transpose()

    return general_info_df


#######################################################################################################################
#
# """
# Summary: Define a function which compares two dataframes and produces an excel spreadsheet of the results.
# Input: One dataframe from DICOM, one dataframe from Mosaiq.
# Results: Produces a dataframe giving a side by side comparison of the two systems
# """


def compare_to_mosaiq(dicom_table, mos_table):
    values_table = pd.DataFrame()
    to_be_compared = dicom_table.columns
    mos_index = mos_table.columns
    dicom_df = pd.DataFrame()
    mosaiq_df = pd.DataFrame()

    for field in range(len(dicom_table)):
        for label in to_be_compared:

            # check that the corresponding value exists in Mosaiq
            if label in mos_index:
                add_dicom = pd.DataFrame(
                    [dicom_table.iloc[field][label]], columns=[label]
                )
                add_mosaiq = pd.DataFrame(
                    [mos_table.iloc[field][label]], columns=[label]
                )

                dicom_df = pd.concat([dicom_df, add_dicom], axis=1)
                mosaiq_df = pd.concat([mosaiq_df, add_mosaiq], axis=1)

            # continue if the value is not in Mosaiq
            else:
                continue

        values_table = values_table.append(dicom_df, ignore_index=True)
        values_table = values_table.append(mosaiq_df, ignore_index=True)

        dicom_df = pd.DataFrame()
        mosaiq_df = pd.DataFrame()

    values_index = []
    for value in dicom_table[:]["field_name"]:
        values_index.append(value + "_DICOM")
        values_index.append(value + "_MOSAIQ")

    values_table["beam_index"] = pd.Series(values_index).values
    values_table = values_table.set_index("beam_index", drop=True)
    # values_table = values_table.round(2)

    return values_table


#######################################################################################################################


def weekly_check_colour_results(val):
    failures = [
        "Unverified Treatment",
        "Partial Treatment",
        "Treatment Overridden",
        "New Field Delivered",
        "Prescription Altered",
        "Site Setup Altered",
        "No recorded treatments within last week.",
    ]
    failure_flag = 0
    for failure in failures:
        # begin comparing everything else, if they match make green (#C1FFC1), else red (#EE6363)
        if failure in set(val):
            failure_flag += 1
        else:
            failure_flag += 0

    if failure_flag == 0:
        return ["background-color: #C1FFC1"] * len(val)
    else:
        return ["background-color: #EE6363"] * len(val)


def specific_patient_weekly_check_colour_results(val):
    failures = ["was_overridden", "new_field", "partial_tx"]
    failure_flag = 0
    for failure in failures:
        # begin comparing everything else, if they match make green (#C1FFC1), else red (#EE6363)
        if val[failure] is True:
            failure_flag += 1
        else:
            failure_flag += 0

    if failure_flag == 0:
        return ["background-color: #C1FFC1"] * len(val)
    else:
        return ["background-color: #EE6363"] * len(val)


def constraint_check_colour_results(val):
    if val["Type"] != "Average Score" and val["Type"] != "Total Score":
        diff = val["Dose [Gy]"] - val["Actual Dose [Gy]"]
        limit = val["Dose [Gy]"] / 10
        if val["Actual Dose [Gy]"] > val["Dose [Gy]"]:
            return ["background-color: #EE6363"] * len(val)
        elif 0 < diff < limit:
            return ["background-color: #FDFF8A"] * len(val)
        else:
            return ["background-color: #C1FFC1"] * len(val)
    else:
        if val["Score"] > 0:
            return ["background-color: #C1FFC1"] * len(val)
        else:
            return ["background-color: #EE6363"] * len(val)
