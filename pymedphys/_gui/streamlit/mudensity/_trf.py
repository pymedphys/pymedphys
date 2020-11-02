from pymedphys._imports import pandas as pd
from pymedphys._imports import streamlit as st

import pymedphys
from pymedphys._gui.streamlit.mudensity import _config, _exceptions


@st.cache
def read_trf(filepath):
    return pymedphys.read_trf(filepath)


@st.cache(allow_output_mutation=True)
def delivery_from_trf(pandas_table):
    return pymedphys.Delivery._from_pandas(  # pylint: disable = protected-access
        pandas_table
    )


def trf_input_method(patient_id="", key_namespace="", **_):
    """Streamlit GUI method to facilitate TRF data provision.

    Notes
    -----
    TRF files themselves have no innate patient alignment. An option
    for TRF collection is to use the CLI tool
    ``pymedphys trf orchestrate``. This connects to the SAMBA server
    hosted on the Elekta NSS and downloads the diagnostic backup zips.
    It then takes these TRF files and queries the Mosaiq database using
    time of delivery to identify these with a patient id (Ident.Pat_ID1)
    and name.

    As such, all references to patient ID and name within this
    ``trf_input_method`` are actually a reference to their Mosaiq
    database counterparts.
    """
    indexed_trf_directory = _config.get_indexed_trf_directory()

    patient_id = st.text_input(
        "Patient ID", patient_id, key=f"{key_namespace}_patient_id"
    )
    st.write(patient_id)

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
                _exceptions.NoRecordsFound(
                    f"No TRF log file found for patient ID {patient_id}"
                )
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

    deliveries = cached_deliveries_loading(tables, delivery_from_trf)

    individual_identifiers = [
        f"{path.parent.parent.parent.parent.name} {path.parent.name}"
        for path in selected_filepaths
    ]

    identifier = f"TRF ({individual_identifiers[0]})"

    """
    #### Corresponding Mosaiq SQL Details
    """

    try:
        mosaiq_details = get_logfile_mosaiq_info(headers)
        use_mosaiq = True
    except KeyError:
        use_mosaiq = False
        st.write(
            NoMosaiqAccess(
                "Need Mosaiq access to determine patient name. "
                "Patient name set to 'Unknown'."
            )
        )
        patient_name = "Unknown"

    if use_mosaiq:
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

    return {
        "site": None,
        "patient_id": patient_id,
        "patient_name": patient_name,
        "data_paths": selected_filepaths,
        "identifier": identifier,
        "deliveries": deliveries,
    }
