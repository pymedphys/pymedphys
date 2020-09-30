import datetime

import pandas as pd

#######################################################################################################################

"""
Summary: Define a function which assigns color values depending on whether or not the values between systems match.
Input: Table of values which you wish to compare.
Results:    match = green
            mismatch = red
            uncomparable = yellow
"""


def color_results(val):
    not_in = [
        "field_type",
        "machine",
        "rx",
        "technique",
        "tolerance",
        "modality",
        "technique",
        "backup_time",
    ]

    # set any values which cannot accurately be compared as yellow (#FDFF8A)
    if val.name in not_in:
        return ["background-color: #FDFF8A", "background-color: #FDFF8A"]

    # begin comparing everything else, if they match make green (#C1FFC1), else red (#EE6363)
    elif type(val[0]) == str and type(val[1]) == str:
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

    elif isinstance(val[0], datetime.date) or isinstance(val[1], datetime.date):
        if val[0] == val[1]:
            return ["background-color: #C1FFC1", "background-color: #C1FFC1"]
        else:
            return ["background-color: #EE6363", "background-color: #EE6363"]

    elif type(val[0]) == float and type(val[1]) == str:
        if val[0] == val[1]:
            return ["background-color: #C1FFC1", "background-color: #C1FFC1"]
        else:
            return ["background-color: #EE6363", "background-color: #EE6363"]

    else:
        if round(float(val[0]), 2) == round(float(val[1]), 2):
            val[0] = round(float(val[0]), 2)
            val[1] = round(float(val[1]), 2)
            return ["background-color: #C1FFC1", "background-color: #C1FFC1"]
        else:
            return ["background-color: #EE6363", "background-color: #EE6363"]


#######################################################################################################################

"""
Summary: Define a function which collects general prescription information for a patient.
Results: Creates a pandas dataframe with 2 columns (one Dicom, one Mosaiq) for each prescription.
"""


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

"""
Summary: Define a function which compares two dataframes and produces an excel spreadsheet of the results.
Input: One dataframe from DICOM, one dataframe from Mosaiq.
Results: Produces a dataframe giving a side by side comparison of the two systems
"""


def compare_to_mosaiq(dicom_table, mos_table):
    values_table = pd.DataFrame()
    to_be_compared = dicom_table.columns
    mos_index = mos_table.columns
    dicom_list = pd.DataFrame()
    mosaiq_list = pd.DataFrame()

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

                dicom_list[label] = add_dicom
                mosaiq_list[label] = add_mosaiq
            # continue if the value is not in Mosaiq
            else:
                continue

        values_table = values_table.append(dicom_list, ignore_index=True)
        values_table = values_table.append(mosaiq_list, ignore_index=True)

    values_index = []
    for value in dicom_table[:]["field_name"]:
        values_index.append(value + "_DICOM")
        values_index.append(value + "_MOSAIQ")

    values_table["beam_index"] = pd.Series(values_index).values
    values_table = values_table.set_index("beam_index", drop=True)

    return values_table


#######################################################################################################################
