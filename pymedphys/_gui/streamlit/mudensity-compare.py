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


# pylint: disable = pointless-statement, pointless-string-statement
# pylint: disable = no-value-for-parameter, expression-not-assigned
# pylint: disable = too-many-lines, redefined-outer-name

import lzma
import os
import pathlib
import subprocess
from datetime import datetime

from pymedphys._imports import imageio, keyring
from pymedphys._imports import numpy as np
from pymedphys._imports import pandas as pd
from pymedphys._imports import plt, pydicom, pymssql
from pymedphys._imports import streamlit as st
from pymedphys._imports import timeago

import pymedphys
from pymedphys import _config as pmp_config
from pymedphys._dicom.constants.uuid import DICOM_PLAN_UID
from pymedphys._monaco import patient as mnc_patient
from pymedphys._mosaiq import connect as msq_connect
from pymedphys._mosaiq import helpers as msq_helpers
from pymedphys._utilities import patient as utl_patient
from pymedphys.labs.managelogfiles import index as pmp_index

"""
# MU Density comparison tool

Tool to compare the MU Density between planned and delivery.
"""

DATA_OPTION_LABELS = {
    "monaco": "Monaco tel.1 filepath",
    "dicom": "DICOM RTPlan file upload",
    "icom": "iCOM record timestamp",
    "trf": "Linac Backup `.trf` filepath",
    "mosaiq": "Mosaiq SQL query",
}

LEAF_PAIR_WIDTHS = (10,) + (5,) * 78 + (10,)
MAX_LEAF_GAP = 410
GRID_RESOLUTION = 1
GRID = pymedphys.mudensity.grid(
    max_leaf_gap=MAX_LEAF_GAP,
    grid_resolution=GRID_RESOLUTION,
    leaf_pair_widths=LEAF_PAIR_WIDTHS,
)
COORDS = (GRID["jaw"], GRID["mlc"])


def download_and_extract_demo_data(cwd):
    pymedphys.zip_data_paths("mu-density-gui-e2e-data.zip", extract_directory=cwd)


@st.cache
def get_config():
    try:
        result = pmp_config.get_config()
    except FileNotFoundError:
        cwd = pathlib.Path.cwd()
        download_and_extract_demo_data(cwd)
        result = pmp_config.get_config(cwd.joinpath("pymedphys-gui-demo"))

    return result


@st.cache
def get_site_directories():
    config = get_config()
    site_directories = {
        site["name"]: {
            "monaco": pathlib.Path(site["monaco"]["focaldata"]).joinpath(
                site["monaco"]["clinic"]
            ),
            "escan": pathlib.Path(site["escan_directory"]),
        }
        for site in config["site"]
    }

    return site_directories


@st.cache
def get_dicom_export_locations():
    site_directories = get_site_directories()
    dicom_export_locations = {
        site: directories["monaco"].parent.parent.joinpath("DCMXprtFile")
        for site, directories in site_directories.items()
    }

    return dicom_export_locations


@st.cache
def get_icom_live_stream_directories():
    config = get_config()
    icom_live_stream_directories = {}
    for site in config["site"]:
        for linac in site["linac"]:
            icom_live_stream_directories[linac["name"]] = linac["icom_live_directory"]

    return icom_live_stream_directories


@st.cache
def get_machine_centre_map():
    config = get_config()
    machine_centre_map = {}
    for site in config["site"]:
        for linac in site["linac"]:
            machine_centre_map[linac["name"]] = site["name"]

    return machine_centre_map


@st.cache
def get_logfile_root_dir():
    config = get_config()
    logfile_root_dir = pathlib.Path(config["trf_logfiles"]["root_directory"])

    return logfile_root_dir


@st.cache
def get_indexed_backups_directory():
    logfile_root_dir = get_logfile_root_dir()
    indexed_backups_directory = logfile_root_dir.joinpath("diagnostics/already_indexed")

    return indexed_backups_directory


@st.cache
def get_indexed_trf_directory():
    logfile_root_dir = get_logfile_root_dir()
    indexed_trf_directory = logfile_root_dir.joinpath("indexed")

    return indexed_trf_directory


@st.cache
def get_mosaiq_details():
    config = get_config()
    mosaiq_details = {
        site["name"]: {
            "timezone": site["mosaiq"]["timezone"],
            "server": f'{site["mosaiq"]["hostname"]}:{site["mosaiq"]["port"]}',
        }
        for site in config["site"]
    }

    return mosaiq_details


@st.cache
def get_default_icom_directories():
    config = get_config()
    default_icom_directory = config["icom"]["patient_directories"]

    return default_icom_directory


@st.cache
def get_default_gamma_options():
    config = get_config()
    default_gamma_options = config["gamma"]

    return default_gamma_options


class InputRequired(ValueError):
    pass


class WrongFileType(ValueError):
    pass


class NoRecordsFound(ValueError):
    pass


class UnableToCreatePDF(ValueError):
    pass


class NoControlPointsFound(ValueError):
    pass


@st.cache(allow_output_mutation=True)
def get_mosaiq_cursor(server):
    _, cursor = msq_connect.single_connect(server)
    return cursor


def sidebar_overview():

    overview_placeholder = st.sidebar.empty()

    def set_overview_data(patient_id, patient_name, total_mu):
        overview_placeholder.markdown(
            f"Patient ID: `{patient_id}`\n\n"
            f"Patient Name: `{patient_name}`\n\n"
            f"Total MU: `{total_mu}`"
        )

    return set_overview_data


def get_most_recent_file_and_print(linac_id, filepaths):
    if not isinstance(filepaths, list):
        raise ValueError("Filepaths needs to be a list")

    latest_filepath = max(filepaths, key=os.path.getmtime)

    most_recent = datetime.fromtimestamp(os.path.getmtime(latest_filepath))
    now = datetime.now()

    if most_recent > now:
        most_recent = now

    human_readable = timeago.format(most_recent, now)

    st.sidebar.markdown(f"{linac_id}: `{human_readable}`")


def icom_status(linac_id, icom_directory):
    filepaths = list(pathlib.Path(icom_directory).glob("*.txt"))
    get_most_recent_file_and_print(linac_id, filepaths)


def trf_status(linac_id, backup_directory):
    directory = pathlib.Path(backup_directory).joinpath(linac_id)
    filepaths = list(directory.glob("*.zip"))
    get_most_recent_file_and_print(linac_id, filepaths)


def show_status_indicators():
    linac_icom_live_stream_directories = get_icom_live_stream_directories()
    linac_indexed_backups_directory = get_indexed_backups_directory()

    linac_ids = list(linac_icom_live_stream_directories.keys())

    if st.sidebar.button("Check status of iCOM and backups"):
        st.sidebar.markdown(
            """
            ## Last recorded iCOM stream
            """
        )

        for linac_id, icom_directory in linac_icom_live_stream_directories.items():
            icom_status(linac_id, icom_directory)

        st.sidebar.markdown(
            """
            ## Last indexed backup
            """
        )

        for linac_id in linac_ids:
            trf_status(linac_id, linac_indexed_backups_directory)

    """
    ## Selection of data to compare
    """


def get_gamma_options(advanced_mode_local):
    default_gamma_options = get_default_gamma_options()

    if advanced_mode_local:
        st.sidebar.markdown(
            """
            # Gamma parameters
            """
        )
        result = {
            **default_gamma_options,
            **{
                "dose_percent_threshold": st.sidebar.number_input(
                    "MU Percent Threshold",
                    value=default_gamma_options["dose_percent_threshold"],
                ),
                "distance_mm_threshold": st.sidebar.number_input(
                    "Distance (mm) Threshold",
                    value=default_gamma_options["distance_mm_threshold"],
                ),
                "local_gamma": st.sidebar.checkbox(
                    "Local Gamma", default_gamma_options["local_gamma"]
                ),
                "max_gamma": st.sidebar.number_input(
                    "Max Gamma", value=default_gamma_options["max_gamma"]
                ),
            },
        }
    else:
        result = default_gamma_options

    return result


@st.cache(allow_output_mutation=True)
def delivery_from_icom(icom_stream):
    return pymedphys.Delivery.from_icom(icom_stream)


@st.cache(allow_output_mutation=True)
def delivery_from_tel(tel_path):
    return pymedphys.Delivery.from_monaco(tel_path)


@st.cache(allow_output_mutation=True)
def delivery_from_trf(pandas_table):
    return pymedphys.Delivery._from_pandas(  # pylint: disable = protected-access
        pandas_table
    )


@st.cache(hash_funcs={pymssql.Cursor: id}, allow_output_mutation=True)
def delivery_from_mosaiq(cursor_and_field_id):
    cursor, field_id = cursor_and_field_id
    return pymedphys.Delivery.from_mosaiq(cursor, field_id)


def cached_deliveries_loading(inputs, method_function):
    deliveries = []

    for an_input in inputs:
        deliveries += [method_function(an_input)]

    return deliveries


@st.cache
def load_icom_stream(icom_path):
    with lzma.open(icom_path, "r") as f:
        contents = f.read()

    return contents


def load_icom_streams(icom_paths):
    icom_streams = []

    for icom_path in icom_paths:
        icom_streams += [load_icom_stream(icom_path)]

    return icom_streams


@st.cache
def read_monaco_patient_name(monaco_patient_directory):
    return mnc_patient.read_patient_name(monaco_patient_directory)


def filter_patient_names(patient_names):
    patient_names = list(set(patient_names))

    if len(patient_names) == 1:
        patient_name = patient_names[0]
    elif len(patient_names) == 0:
        patient_name = ""
    else:
        patient_name = f"Multiple Names Found: f{', '.join(patient_names)}"

    return patient_name


def monaco_input_method(
    patient_id="", key_namespace="", advanced_mode_local=False, **_
):

    site_directories = get_site_directories()

    site_options = list(site_directories.keys())
    monaco_site = st.radio(
        "Monaco Plan Location", site_options, key=f"{key_namespace}_monaco_site"
    )
    monaco_directory = site_directories[monaco_site]["monaco"]

    if advanced_mode_local:
        st.write(monaco_directory.resolve())

    patient_id = st.text_input(
        "Patient ID", patient_id, key=f"{key_namespace}_patient_id"
    )
    if advanced_mode_local:
        patient_id
    elif patient_id == "":
        raise st.ScriptRunner.StopException()

    patient_directories = monaco_directory.glob(f"*~{patient_id}")

    patient_names = set()
    for patient_directory in patient_directories:
        patient_names.add(read_monaco_patient_name(str(patient_directory)))

    patient_name = filter_patient_names(patient_names)

    f"Patient Name: `{patient_name}`"

    plan_directories = list(monaco_directory.glob(f"*~{patient_id}/plan"))
    if len(plan_directories) == 0:
        if patient_id != "":
            st.write(
                NoRecordsFound(
                    f"No Monaco plan directories found for patient ID {patient_id}"
                )
            )
        return {"patient_id": patient_id}
    elif len(plan_directories) > 1:
        raise ValueError(
            "More than one patient plan directory found for this ID, "
            "please only have one directory per patient. "
            "Directories found were "
            f"{', '.join([str(path.resolve()) for path in plan_directories])}"
        )

    plan_directory = plan_directories[0]

    all_tel_paths = list(plan_directory.glob("**/*tel.1"))
    all_tel_paths = sorted(all_tel_paths, key=os.path.getmtime)

    plan_names_to_choose_from = [
        str(path.relative_to(plan_directory)) for path in all_tel_paths
    ]

    if len(plan_names_to_choose_from) == 0:
        if patient_id != "":
            st.write(
                NoRecordsFound(f"No Monaco plans found for patient ID {patient_id}")
            )
        return {"patient_id": patient_id}

    """
    Select the Monaco plan that correspond to a patient's single fraction.
    If a patient has multiple fraction types (such as a plan with a boost)
    then these fraction types need to be analysed separately.
    """

    selected_monaco_plan = st.radio(
        "Select a Monaco plan",
        plan_names_to_choose_from,
        key=f"{key_namespace}_monaco_plans",
    )

    tel_paths = []

    if selected_monaco_plan is not None:
        current_plans = list(
            monaco_directory.glob(f"*~{patient_id}/plan/{selected_monaco_plan}")
        )
        current_plans = [path.resolve() for path in current_plans]
        if len(current_plans) != 1:
            st.write("Plans found:", current_plans)
            raise ValueError("Exactly one plan should have been found")
        tel_paths += current_plans

    if advanced_mode_local:
        [str(path.resolve()) for path in tel_paths]

    deliveries = cached_deliveries_loading(tel_paths, delivery_from_tel)

    if tel_paths:
        plan_names = ", ".join([path.parent.name for path in tel_paths])
        identifier = f"Monaco ({plan_names})"
    else:
        identifier = None

    if len(deliveries) == 1 and len(deliveries[0].mu) == 0:
        st.write(
            NoControlPointsFound(
                "This is likely due to an as of yet unsupported "
                "Monaco file format. At this point in time 3DCRT "
                "is not yet supported for reading directly from "
                "Monaco. DICOM is though, please export the plan "
                "to RT DICOM and import the data that way."
            )
        )

    results = {
        "patient_id": patient_id,
        "patient_name": patient_name,
        "selected_monaco_plan": selected_monaco_plan,
        "data_paths": tel_paths,
        "identifier": identifier,
        "deliveries": deliveries,
    }

    return results


def pydicom_hash_funcion(dicom):
    return hash(dicom.SOPInstanceUID)


@st.cache(hash_funcs={pydicom.dataset.FileDataset: pydicom_hash_funcion})
def load_dicom_file_if_plan(filepath):
    dcm = pydicom.read_file(str(filepath), force=True, stop_before_pixels=True)
    if dcm.SOPClassUID == DICOM_PLAN_UID:
        return dcm

    return None


def dicom_input_method(  # pylint: disable = too-many-return-statements
    key_namespace="", patient_id="", **_
):
    FILE_UPLOAD = "File upload"
    MONACO_SEARCH = "Search Monaco file export location"

    dicom_export_locations = get_dicom_export_locations()

    import_method = st.radio(
        "DICOM import method",
        [FILE_UPLOAD, MONACO_SEARCH],
        key=f"{key_namespace}_dicom_file_import_method",
    )

    if import_method == FILE_UPLOAD:
        dicom_plan_bytes = st.file_uploader(
            "Upload DICOM RT Plan File", key=f"{key_namespace}_dicom_plan_uploader"
        )

        if dicom_plan_bytes is None:
            return {}

        try:
            dicom_plan = pydicom.read_file(dicom_plan_bytes, force=True)
        except:  # pylint: disable = bare-except
            st.write(WrongFileType("Does not appear to be a DICOM file"))
            return {}

        if dicom_plan.SOPClassUID != DICOM_PLAN_UID:
            st.write(WrongFileType("The DICOM type needs to be an RT DICOM Plan file"))
            return {}

        data_paths = ["Uploaded DICOM file"]

    if import_method == MONACO_SEARCH:
        site_options = list(dicom_export_locations.keys())
        monaco_site = st.radio(
            "Monaco Export Location", site_options, key=f"{key_namespace}_monaco_site"
        )
        monaco_export_directory = dicom_export_locations[monaco_site]
        st.write(monaco_export_directory.resolve())

        patient_id = st.text_input(
            "Patient ID", patient_id, key=f"{key_namespace}_patient_id"
        )

        found_dicom_files = list(monaco_export_directory.glob(f"{patient_id}_*.dcm"))

        dicom_plans = {}

        for path in found_dicom_files:
            dcm = load_dicom_file_if_plan(path)
            if dcm is not None:
                dicom_plans[path.name] = dcm

        dicom_plan_options = list(dicom_plans.keys())

        if len(dicom_plan_options) == 0 and patient_id != "":
            st.write(
                NoRecordsFound(
                    f"No exported DICOM RT plans found for Patient ID {patient_id} "
                    f"within the directory {monaco_export_directory}"
                )
            )
            return {"patient_id": patient_id}

        if len(dicom_plan_options) == 1:
            selected_plan = dicom_plan_options[0]
        else:
            selected_plan = st.radio(
                "Select DICOM Plan",
                dicom_plan_options,
                key=f"{key_namespace}_select_monaco_export_plan",
            )

        f"DICOM file being used: `{selected_plan}`"

        dicom_plan = dicom_plans[selected_plan]
        data_paths = [monaco_export_directory.joinpath(selected_plan)]

    patient_id = str(dicom_plan.PatientID)
    f"Patient ID: `{patient_id}`"

    patient_name = str(dicom_plan.PatientName)
    patient_name = utl_patient.convert_patient_name(patient_name)

    f"Patient Name: `{patient_name}`"

    rt_plan_name = str(dicom_plan.RTPlanName)
    f"Plan Name: `{rt_plan_name}`"

    try:
        deliveries_all_fractions = pymedphys.Delivery.from_dicom(
            dicom_plan, fraction_number="all"
        )
    except AttributeError:
        st.write(WrongFileType("Does not appear to be a photon DICOM plan"))
        return {}

    fractions = list(deliveries_all_fractions.keys())
    if len(fractions) == 1:
        delivery = deliveries_all_fractions[fractions[0]]
    else:
        fraction_choices = {}

        for fraction, delivery in deliveries_all_fractions.items():
            rounded_mu = round(delivery.mu[-1], 1)

            fraction_choices[f"Perscription {fraction} with {rounded_mu} MU"] = fraction

        fraction_selection = st.radio(
            "Select relevant perscription",
            list(fraction_choices.keys()),
            key=f"{key_namespace}_dicom_perscription_chooser",
        )

        fraction_number = fraction_choices[fraction_selection]
        delivery = deliveries_all_fractions[fraction_number]

    deliveries = [delivery]

    identifier = f"DICOM ({rt_plan_name})"

    return {
        "patient_id": patient_id,
        "patient_name": patient_name,
        "data_paths": data_paths,
        "identifier": identifier,
        "deliveries": deliveries,
    }


def icom_input_method(patient_id="", key_namespace="", advanced_mode_local=False, **_):
    icom_directories = get_default_icom_directories()

    if advanced_mode_local:
        "iCOM patient directories", icom_directories

    icom_directories = [pathlib.Path(path) for path in icom_directories]

    if advanced_mode_local:
        patient_id = st.text_input(
            "Patient ID", patient_id, key=f"{key_namespace}_patient_id"
        )
        patient_id

    icom_deliveries = []
    for path in icom_directories:
        icom_deliveries += list(path.glob(f"{patient_id}_*/*.xz"))

    icom_deliveries = sorted(icom_deliveries)

    icom_files_to_choose_from = [path.stem for path in icom_deliveries]

    timestamps = list(
        pd.to_datetime(icom_files_to_choose_from, format="%Y%m%d_%H%M%S").astype(str)
    )

    choice_path_map = dict(zip(timestamps, icom_deliveries))

    """
    Here you need to select the timestamps that correspond to a single
    fraction of the plan selected above. Most of the time
    you will only need to select one timestamp here, however in some
    cases you may need to select multiple timestamps.

    This can occur if for example a single fraction was delivered in separate
    beams due to either a beam interrupt, or the fraction being spread
    over multiple energies
    """

    if len(timestamps) == 0:
        if patient_id != "":
            st.write(
                NoRecordsFound(
                    f"No iCOM delivery record found for patient ID {patient_id}"
                )
            )
        return {"patient_id": patient_id}

    if len(timestamps) == 1:
        default_timestamp = timestamps[0]
    else:
        default_timestamp = []

    timestamps = sorted(timestamps, reverse=True)

    selected_icom_deliveries = st.multiselect(
        "Select iCOM delivery timestamp(s)",
        timestamps,
        default=default_timestamp,
        key=f"{key_namespace}_icom_deliveries",
    )

    icom_filenames = [
        path.replace(" ", "_").replace("-", "").replace(":", "")
        for path in selected_icom_deliveries
    ]

    icom_paths = []
    for selected in selected_icom_deliveries:
        icom_paths.append(choice_path_map[selected])

    if advanced_mode_local:
        [str(path.resolve()) for path in icom_paths]

    patient_names = set()
    for icom_path in icom_paths:
        patient_name = str(icom_path.parent.name).split("_")[-1]
        try:
            patient_name = utl_patient.convert_patient_name_from_split(
                *patient_name.split(", ")
            )
        except:  # pylint: disable = bare-except
            pass

        patient_names.add(patient_name)

    patient_name = filter_patient_names(patient_names)

    icom_streams = load_icom_streams(icom_paths)
    deliveries = cached_deliveries_loading(icom_streams, delivery_from_icom)

    if selected_icom_deliveries:
        identifier = f"iCOM ({icom_filenames[0]})"
    else:
        identifier = None

    if len(deliveries) == 0:
        st.write(InputRequired("Please select at least one iCOM delivery"))

    results = {
        "patient_id": patient_id,
        "patient_name": patient_name,
        "selected_icom_deliveries": selected_icom_deliveries,
        "data_paths": icom_paths,
        "identifier": identifier,
        "deliveries": deliveries,
    }

    return results


@st.cache
def read_trf(filepath):
    return pymedphys.read_trf(filepath)


@st.cache
def get_logfile_mosaiq_info(headers):
    machine_centre_map = get_machine_centre_map()
    mosaiq_details = get_mosaiq_details()

    centres = {machine_centre_map[machine_id] for machine_id in headers["machine"]}
    mosaiq_servers = [mosaiq_details[centre]["server"] for centre in centres]

    details = []

    cursors = {server: get_mosaiq_cursor(server) for server in mosaiq_servers}

    for _, header in headers.iterrows():
        machine_id = header["machine"]
        centre = machine_centre_map[machine_id]
        mosaiq_timezone = mosaiq_details[centre]["timezone"]
        server = mosaiq_details[centre]["server"]
        cursor = cursors[server]

        field_label = header["field_label"]
        field_name = header["field_name"]
        utc_date = header["date"]

        current_details = pmp_index.get_logfile_mosaiq_info(
            cursor, machine_id, utc_date, mosaiq_timezone, field_label, field_name
        )
        current_details = pd.Series(data=current_details)

        details.append(current_details)

    details = pd.concat(details, axis=1).T

    return details


def trf_input_method(patient_id="", key_namespace="", **_):
    indexed_trf_directory = get_indexed_trf_directory()

    patient_id = st.text_input(
        "Patient ID", patient_id, key=f"{key_namespace}_patient_id"
    )
    patient_id

    filepaths = list(indexed_trf_directory.glob(f"*/{patient_id}_*/*/*/*/*.trf"))

    raw_timestamps = ["_".join(path.parent.name.split("_")[0:2]) for path in filepaths]
    timestamps = list(
        pd.to_datetime(raw_timestamps, format="%Y-%m-%d_%H%M%S").astype(str)
    )

    timestamp_filepath_map = dict(zip(timestamps, filepaths))

    timestamps = sorted(timestamps, reverse=True)

    if len(timestamps) == 0:
        if patient_id != "":
            st.write(
                NoRecordsFound(f"No TRF log file found for patient ID {patient_id}")
            )
        return {"patient_id": patient_id}

    if len(timestamps) == 1:
        default_timestamp = timestamps[0]
    else:
        default_timestamp = []

    selected_trf_deliveries = st.multiselect(
        "Select TRF delivery timestamp(s)",
        timestamps,
        default=default_timestamp,
        key=f"{key_namespace}_trf_deliveries",
    )

    if not selected_trf_deliveries:
        return {}

    """
    #### TRF filepath(s)
    """

    selected_filepaths = [
        timestamp_filepath_map[timestamp] for timestamp in selected_trf_deliveries
    ]
    [str(path.resolve()) for path in selected_filepaths]

    """
    #### Log file header(s)
    """

    headers = []
    tables = []
    for path in selected_filepaths:
        header, table = read_trf(path)
        headers.append(header)
        tables.append(table)

    headers = pd.concat(headers)
    headers.reset_index(inplace=True)
    headers.drop("index", axis=1, inplace=True)

    headers

    """
    #### Corresponding Mosaiq SQL Details
    """

    mosaiq_details = get_logfile_mosaiq_info(headers)
    mosaiq_details = mosaiq_details.drop("beam_completed", axis=1)

    mosaiq_details

    patient_names = set()
    for _, row in mosaiq_details.iterrows():
        row
        patient_name = utl_patient.convert_patient_name_from_split(
            row["last_name"], row["first_name"]
        )
        patient_names.add(patient_name)

    patient_name = filter_patient_names(patient_names)

    deliveries = cached_deliveries_loading(tables, delivery_from_trf)

    individual_identifiers = [
        f"{path.parent.parent.parent.parent.name} {path.parent.name}"
        for path in selected_filepaths
    ]

    identifier = f"TRF ({individual_identifiers[0]})"

    return {
        "patient_id": patient_id,
        "patient_name": patient_name,
        "data_paths": selected_filepaths,
        "identifier": identifier,
        "deliveries": deliveries,
    }


@st.cache(hash_funcs={pymssql.Cursor: id})
def get_patient_fields(cursor, patient_id):
    return msq_helpers.get_patient_fields(cursor, patient_id)


@st.cache(hash_funcs={pymssql.Cursor: id})
def get_patient_name(cursor, patient_id):
    return msq_helpers.get_patient_name(cursor, patient_id)


def mosaiq_input_method(patient_id="", key_namespace="", **_):
    mosaiq_details = get_mosaiq_details()
    site_options = list(mosaiq_details.keys())

    mosaiq_site = st.radio(
        "Mosaiq Site", site_options, key=f"{key_namespace}_mosaiq_site"
    )
    server = mosaiq_details[mosaiq_site]["server"]
    f"Mosaiq Hostname: `{server}`"

    sql_user = keyring.get_password("MosaiqSQL_username", server)
    f"Mosaiq SQL login being used: `{sql_user}`"

    patient_id = st.text_input(
        "Patient ID", patient_id, key=f"{key_namespace}_patient_id"
    )
    patient_id

    cursor = get_mosaiq_cursor(server)

    if patient_id == "":
        return {}

    patient_name = get_patient_name(cursor, patient_id)

    f"Patient Name: `{patient_name}`"

    patient_fields = get_patient_fields(cursor, patient_id)

    """
    #### Mosaiq patient fields
    """

    patient_fields = patient_fields[patient_fields["monitor_units"] != 0]
    patient_fields

    field_ids = patient_fields["field_id"]
    field_ids = field_ids.values.tolist()

    selected_field_ids = st.multiselect(
        "Select Mosaiq field id(s)", field_ids, key=f"{key_namespace}_mosaiq_field_id"
    )

    cursor_and_field_ids = [(cursor, field_id) for field_id in selected_field_ids]
    deliveries = cached_deliveries_loading(cursor_and_field_ids, delivery_from_mosaiq)
    identifier = f"{mosaiq_site} Mosaiq ({', '.join([str(field_id) for field_id in selected_field_ids])})"

    return {
        "patient_id": patient_id,
        "patient_name": patient_name,
        "data_paths": [],
        "identifier": identifier,
        "deliveries": deliveries,
    }


def display_deliveries(deliveries):
    if not deliveries:
        return 0

    """
    #### Overview of selected deliveries
    """

    data = []
    for delivery in deliveries:
        num_control_points = len(delivery.mu)

        if num_control_points != 0:
            total_mu = delivery.mu[-1]
        else:
            total_mu = 0

        data.append([total_mu, num_control_points])

    columns = ["MU", "Number of Data Points"]
    df = pd.DataFrame(data=data, columns=columns)
    df

    total_mu = round(df["MU"].sum(), 1)

    f"Total MU: `{total_mu}`"

    return total_mu


def get_input_data_ui(
    overview_updater_map,
    data_method_map,
    default_method,
    key_namespace,
    advanced_mode_local,
    **previous_results,
):
    if advanced_mode_local:
        data_method_options = list(data_method_map.keys())
        data_method = st.selectbox(
            "Data Input Method",
            data_method_options,
            index=data_method_options.index(default_method),
        )

    else:
        data_method = default_method

    results = data_method_map[data_method](  # type: ignore
        key_namespace=key_namespace,
        advanced_mode_local=advanced_mode_local,
        **previous_results,
    )

    try:
        total_mu = round(display_deliveries(results["deliveries"]), 1)
    except KeyError:
        total_mu = 0

    try:
        patient_id = results["patient_id"]
    except KeyError:
        patient_id = ""

    try:
        patient_name = results["patient_name"]
    except KeyError:
        patient_name = ""

    overview_updater_map[key_namespace](patient_id, patient_name, total_mu)

    return results


@st.cache
def to_tuple(array):
    return tuple(map(tuple, array))


def plot_gamma_hist(gamma, percent, dist):
    valid_gamma = gamma[~np.isnan(gamma)]

    plt.hist(valid_gamma, 50, density=True)
    pass_ratio = np.sum(valid_gamma <= 1) / len(valid_gamma)

    plt.title(
        "Local Gamma ({0}%/{1}mm) | Percent Pass: {2:.2f} % | Mean Gamma: {3:.2f} | Max Gamma: {4:.2f}".format(
            percent, dist, pass_ratio * 100, np.mean(valid_gamma), np.max(valid_gamma)
        )
    )


def plot_and_save_results(
    reference_mudensity,
    evaluation_mudensity,
    gamma,
    gamma_options,
    png_record_directory,
    header_text="",
    footer_text="",
):
    reference_filepath = png_record_directory.joinpath("reference.png")
    evaluation_filepath = png_record_directory.joinpath("evaluation.png")
    diff_filepath = png_record_directory.joinpath("diff.png")
    gamma_filepath = png_record_directory.joinpath("gamma.png")

    diff = evaluation_mudensity - reference_mudensity

    imageio.imwrite(reference_filepath, reference_mudensity)
    imageio.imwrite(evaluation_filepath, evaluation_mudensity)
    imageio.imwrite(diff_filepath, diff)
    imageio.imwrite(gamma_filepath, gamma)

    largest_mu_density = np.max(
        [np.max(evaluation_mudensity), np.max(reference_mudensity)]
    )
    largest_diff = np.max(np.abs(diff))

    widths = [1, 1]
    heights = [0.5, 1, 1, 1, 0.4]
    gs_kw = dict(width_ratios=widths, height_ratios=heights)

    fig, axs = plt.subplots(5, 2, figsize=(10, 16), gridspec_kw=gs_kw)
    gs = axs[0, 0].get_gridspec()

    for ax in axs[0, 0:]:
        ax.remove()

    for ax in axs[1, 0:]:
        ax.remove()

    for ax in axs[4, 0:]:
        ax.remove()

    ax_header = fig.add_subplot(gs[0, :])
    ax_hist = fig.add_subplot(gs[1, :])
    ax_footer = fig.add_subplot(gs[4, :])

    ax_header.axis("off")
    ax_footer.axis("off")

    ax_header.text(0, 0, header_text, ha="left", wrap=True, fontsize=21)
    ax_footer.text(0, 1, footer_text, ha="left", va="top", wrap=True, fontsize=6)

    plt.sca(axs[2, 0])
    pymedphys.mudensity.display(
        GRID, reference_mudensity, vmin=0, vmax=largest_mu_density
    )
    axs[2, 0].set_title("Reference MU Density")

    plt.sca(axs[2, 1])
    pymedphys.mudensity.display(
        GRID, evaluation_mudensity, vmin=0, vmax=largest_mu_density
    )
    axs[2, 1].set_title("Evaluation MU Density")

    plt.sca(axs[3, 0])
    pymedphys.mudensity.display(
        GRID, diff, cmap="seismic", vmin=-largest_diff, vmax=largest_diff
    )
    plt.title("Evaluation - Reference")

    plt.sca(axs[3, 1])
    pymedphys.mudensity.display(GRID, gamma, cmap="coolwarm", vmin=0, vmax=2)
    plt.title(
        "Local Gamma | "
        f"{gamma_options['dose_percent_threshold']}%/"
        f"{gamma_options['distance_mm_threshold']}mm"
    )

    plt.sca(ax_hist)
    plot_gamma_hist(
        gamma,
        gamma_options["dose_percent_threshold"],
        gamma_options["distance_mm_threshold"],
    )

    return fig


@st.cache(hash_funcs={pymedphys.Delivery: hash})
def calculate_mudensity(delivery):
    return delivery.mudensity(
        max_leaf_gap=MAX_LEAF_GAP,
        grid_resolution=GRID_RESOLUTION,
        leaf_pair_widths=LEAF_PAIR_WIDTHS,
    )


def calculate_batch_mudensity(deliveries):
    mudensity = calculate_mudensity(deliveries[0])

    for delivery in deliveries[1::]:
        mudensity = mudensity + calculate_mudensity(delivery)

    return mudensity


@st.cache
def calculate_gamma(reference_mudensity, evaluation_mudensity, gamma_options):
    gamma = pymedphys.gamma(
        COORDS,
        to_tuple(reference_mudensity),
        COORDS,
        to_tuple(evaluation_mudensity),
        **gamma_options,
    )

    return gamma


def advanced_debugging():
    config = get_config()

    st.sidebar.markdown("# Advanced Debugging")
    if st.sidebar.button("Compare Baseline to Output Directory"):
        """
        ## Comparing Results to Baseline
        """

        baseline_directory = pathlib.Path(
            config["debug"]["baseline_directory"]
        ).resolve()

        png_baseline_directory = baseline_directory.joinpath("png")

        baseline_png_paths = [
            path for path in (png_baseline_directory.rglob("*")) if path.is_file()
        ]

        relative_png_paths = [
            path.relative_to(png_baseline_directory) for path in baseline_png_paths
        ]

        output_dir = pathlib.Path(config["output"]["png_directory"]).resolve()

        evaluation_png_paths = [
            output_dir.joinpath(path) for path in relative_png_paths
        ]

        for baseline, evaluation in zip(baseline_png_paths, evaluation_png_paths):

            f"### {baseline.parent.name}/{baseline.name}"

            f"`{baseline}`\n\n**vs**\n\n`{evaluation}`"

            baseline_image = imageio.imread(baseline)

            try:
                evaluation_image = imageio.imread(evaluation)
            except FileNotFoundError as e:
                """
                #### File was not found
                """
                st.write(e)

                f"""
                For debugging purposes, here are all the files that
                were found within {str(output_dir)}
                """

                [str(path) for path in output_dir.rglob("*") if path.is_file()]

                return

            agree = np.allclose(baseline_image, evaluation_image)
            f"Images Agree: `{agree}`"


def run_calculation(
    reference_results,
    evaluation_results,
    gamma_options,
    escan_directory,
    png_output_directory,
):
    st.write("Calculating Reference MU Density...")
    reference_mudensity = calculate_batch_mudensity(reference_results["deliveries"])

    st.write("Calculating Evaluation MU Density...")
    evaluation_mudensity = calculate_batch_mudensity(evaluation_results["deliveries"])

    st.write("Calculating Gamma...")
    gamma = calculate_gamma(reference_mudensity, evaluation_mudensity, gamma_options)

    patient_id = reference_results["patient_id"]

    st.write("Creating figure...")
    output_base_filename = (
        f"{patient_id} {reference_results['identifier']} vs "
        f"{evaluation_results['identifier']}"
    )
    pdf_filepath = str(
        escan_directory.joinpath(f"{output_base_filename}.pdf").resolve()
    )
    png_record_directory = png_output_directory.joinpath(output_base_filename)
    png_record_directory.mkdir(exist_ok=True)
    png_filepath = str(png_record_directory.joinpath("report.png").resolve())

    try:
        patient_name_text = f"Patient Name: {reference_results['patient_name']}\n"
    except KeyError:
        patient_name_text = ""

    header_text = (
        f"Patient ID: {patient_id}\n"
        f"{patient_name_text}"
        f"Reference: {reference_results['identifier']}\n"
        f"Evaluation: {evaluation_results['identifier']}\n"
    )

    reference_path_strings = "\n    ".join(
        [str(path.resolve()) for path in reference_results["data_paths"]]
    )
    evaluation_path_strings = "\n    ".join(
        [str(path.resolve()) for path in evaluation_results["data_paths"]]
    )

    footer_text = (
        f"reference path(s): {reference_path_strings}\n"
        f"evaluation path(s): {evaluation_path_strings}\n"
        f"png record: {png_filepath}"
    )

    fig = plot_and_save_results(
        reference_mudensity,
        evaluation_mudensity,
        gamma,
        gamma_options,
        png_record_directory,
        header_text=header_text,
        footer_text=footer_text,
    )

    fig.tight_layout()

    st.write("Saving figure...")
    plt.savefig(png_filepath, dpi=100)
    try:
        subprocess.check_call(
            f'magick convert "{png_filepath}" "{pdf_filepath}"', shell=True
        )
    except subprocess.CalledProcessError:
        st.write(
            UnableToCreatePDF(
                "Please install Image Magick to create PDF reports "
                "<https://imagemagick.org/script/download.php#windows>."
            )
        )

    st.write("## Results")
    st.pyplot()


def main():
    config = get_config()

    st.sidebar.markdown(
        """
        # Overview
        """
    )

    st.sidebar.markdown(
        """
        ## Reference
        """
    )

    set_reference_overview = sidebar_overview()

    st.sidebar.markdown(
        """
        ## Evaluation
        """
    )

    set_evaluation_overview = sidebar_overview()

    overview_updater_map = {
        "reference": set_reference_overview,
        "evaluation": set_evaluation_overview,
    }

    st.sidebar.markdown(
        """
        # Status indicators
        """
    )

    show_status_indicators()

    st.sidebar.markdown(
        """
        # Advanced options

        Enable advanced functionality by ticking the below.
        """
    )
    advanced_mode = st.sidebar.checkbox("Run in Advanced Mode")

    gamma_options = get_gamma_options(advanced_mode)

    data_option_functions = {
        "monaco": monaco_input_method,
        "dicom": dicom_input_method,
        "icom": icom_input_method,
        "trf": trf_input_method,
        "mosaiq": mosaiq_input_method,
    }

    default_reference_id = config["data_methods"]["default_reference"]
    default_evaluation_id = config["data_methods"]["default_evaluation"]
    available_data_methods = config["data_methods"]["available"]

    default_reference = DATA_OPTION_LABELS[default_reference_id]
    default_evaluation = DATA_OPTION_LABELS[default_evaluation_id]

    data_method_map = {}
    for method in available_data_methods:
        data_method_map[DATA_OPTION_LABELS[method]] = data_option_functions[method]

    """
    ### Reference
    """

    reference_results = get_input_data_ui(
        overview_updater_map,
        data_method_map,
        default_reference,
        "reference",
        advanced_mode,
    )

    """
    ### Evaluation
    """

    evaluation_results = get_input_data_ui(
        overview_updater_map,
        data_method_map,
        default_evaluation,
        "evaluation",
        advanced_mode,
        **reference_results,
    )

    """
    ## Output Locations
    """

    """
    ### eSCAN Directory

    The location to save the produced pdf report.
    """

    site_directories = get_site_directories()

    site_options = list(site_directories.keys())
    escan_site = st.radio("eScan Site", site_options)
    escan_directory = site_directories[escan_site]["escan"]

    if advanced_mode:
        st.write(escan_directory.resolve())

    default_png_output_directory = config["output"]["png_directory"]

    if advanced_mode:
        """
        ### Image record

        Path to save the image of the results for posterity
        """

        png_output_directory = pathlib.Path(
            st.text_input("png output directory", default_png_output_directory)
        )
        st.write(png_output_directory.resolve())

    else:
        png_output_directory = pathlib.Path(default_png_output_directory)

    """
    ## Calculation
    """

    if st.button("Run Calculation"):
        run_calculation(
            reference_results,
            evaluation_results,
            gamma_options,
            escan_directory,
            png_output_directory,
        )

    if advanced_mode:
        advanced_debugging()


if __name__ == "__main__":
    main()
