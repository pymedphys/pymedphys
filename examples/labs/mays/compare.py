import numpy as np
import pandas as pd

#######################################################################################################################

"""
Summary: Define a function which assigns color values depending on whether or not the values between systems match.
Input: Table of values which you wish to compare.
Results:    match = green
            mismatch = red
"""


def color_results(val):
    is_true = []
    for i in range(0, len(val), 2):
        if type(val[i]) == str and type(val[i + 1]) == str:
            if val[i] == val[i + 1]:
                is_true.append(1)
                is_true.append(1)
            else:
                is_true.append(0)
                is_true.append(0)
        elif val[i] == "" or val[i + 1] == "":
            if val[i] == val[i + 1]:
                is_true.append(1)
                is_true.append(1)
            else:
                is_true.append(0)
                is_true.append(0)
        else:
            if round(float(val[i]), 2) == round(float(val[i + 1]), 2):
                is_true.append(1)
                is_true.append(1)
            else:
                is_true.append(0)
                is_true.append(0)
    return [
        "background-color: #78FB7E" if v == 1 else "background-color: #F76655"
        for v in is_true
    ]


# 'background-color: #FDFF8A' good yellow color to add later

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
Results: Produces an excel spreadsheet showing the
"""


def compare_to_mosaiq(dicom_table, mos_table):
    results = []
    dic_table = []
    mosaiq_table = []
    field_results = []
    table_results = []
    to_be_compared = [
        "mrn",
        "first_name",
        "last_name",
        "site",
        "field_label",
        "field_name",
        "machine",
        "energy",
        "monitor_units",
        "fraction_dose",
        "total_dose",
        "fractions",
        "gantry_angle",
        "collimator_angle",
        "ssd",
        "sad",
        "iso_x",
        "iso_y",
        "iso_z",
        "field_x",
        "coll_x1",
        "coll_x2",
        "field_y",
        "coll_y1",
        "coll_y2",
        "couch_vrt",
        "couch_lat",
        "couch_lng",
        "couch_ang",
        "tolerance",
        "meterset_rate",
    ]

    for field in range(len(dicom_table)):
        for label in to_be_compared:
            mosaiq_table.append(mos_table.iloc[field][label])
            dic_table.append(dicom_table.iloc[field][label])
            if (
                type(dicom_table.iloc[field][label]) == str
                and type(mos_table.iloc[field][label]) == str
            ):
                field_results.append(
                    dicom_table.iloc[field][label] == mos_table.iloc[field][label]
                )
            elif (
                dicom_table.iloc[field][label] == ""
                or mos_table.iloc[field][label] == ""
            ):
                field_results.append(
                    dicom_table.iloc[field][label] == mos_table.iloc[field][label]
                )
            else:
                field_results.append(
                    float(dicom_table.iloc[field][label])
                    == float(mos_table.iloc[field][label])
                )
        results.append(field_results)
        table_results.append(dic_table)
        table_results.append(mosaiq_table)
        field_results = []
        dic_table = []
        mosaiq_table = []

    values_index = []
    for value in dicom_table[:]["field_name"]:
        values_index.append(value + "_DICOM")
        values_index.append(value + "_MOSAIQ")

    values_table = pd.DataFrame(data=table_results, columns=to_be_compared)

    values_table["beam_index"] = pd.Series(values_index).values
    values_table = values_table.set_index("beam_index", drop=True)
    # values_table = values_table.transpose()
    general_info = get_general_info(dicom_table, mos_table)

    dose_ref = dicom_table["dose_reference"]
    prescription_index = []
    prescription_num = 1
    for i in range(min(dose_ref), max(dose_ref) + 1):
        prescription_index.append(np.where(dose_ref == i))

    idx = []
    for rx in prescription_index:
        count = rx[0].shape[0]
        idx.append(count)
    prescription_index = []
    i = 0
    for j in idx:
        prescription_index.append(list(range(i, i + 2 * j)))
        i += 2 * j

    with pd.ExcelWriter(
        "C:/Users/rembishj/Documents/Python Scripts/autoCheck/%s.xlsx"
        % (dicom_table.iloc[0]["last_name"] + "_pretreatment_check")
    ) as writer:
        general_info.to_excel(writer, sheet_name="Patient Info")
        for prescription in prescription_index:
            prescription_fields = values_table.iloc[prescription]
            prescription_fields = prescription_fields.transpose()
            prescription_fields.style.apply(color_results, axis=1).to_excel(
                writer, sheet_name="Field Info RX%s" % prescription_num
            )
            prescription_num += 1
    return values_table


#######################################################################################################################
