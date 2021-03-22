# Copyright (C) 2021 Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import contextlib
import functools
import hashlib
import pathlib
import re
from typing import List

from pymedphys._imports import pydicom, pynetdicom
from pymedphys._imports import streamlit as st

from pymedphys._dicom import orientation
from pymedphys._dicom.ct import extend as _extend
from pymedphys._streamlit import categories
from pymedphys._streamlit.utilities import config as st_config

CATEGORY = categories.ALPHA
TITLE = "Monaco Extend CT"


def main():
    config = st_config.get_config()

    site_config_map = {}
    for site_config in config["site"]:
        site = site_config["name"]
        try:
            site_config_map[site] = {
                "focal_data": site_config["monaco"]["focaldata"],
                "hostname": site_config["monaco"]["hostname"],
                "port": site_config["monaco"]["dicom_port"],
            }
        except KeyError:
            continue

    chosen_site = st.radio("Site", list(site_config_map.keys()))
    site_config = site_config_map[chosen_site]

    focal_data = pathlib.Path(site_config["focal_data"])
    dicom_export = focal_data.joinpath("DCMXprtFile")
    hostname = site_config["hostname"]
    port = site_config["port"]

    # Caps or not within glob doesn't matter on Windows, but it does
    # matter on *nix systems.
    dicom_files = dicom_export.glob("*.DCM")

    patient_id_pattern = re.compile(r"(\d+)_.*_image\d\d\d\d\d.DCM")
    patient_ids = list(
        {
            patient_id_pattern.match(path.name).group(1)
            for path in dicom_files
            if patient_id_pattern.match(path.name)
        }
    )

    st.write(
        """
        ## Select patient

        For a patient to show up below, make sure to run a DICOM export
        to file within Monaco first.
        """
    )
    chosen_patient_id = st.radio("Patient ID", patient_ids)

    ct_dicom_files = list(dicom_export.glob(f"{chosen_patient_id}_*_image*.DCM"))
    _stop_button_if_cache_miss("Load files", _load_dicom_files, ct_dicom_files)

    ct_series = _cached_load_dicom_files(ct_dicom_files)
    patient_names_found = {header.PatientName for header in ct_series}
    st.write(patient_names_found)

    if len(patient_names_found) != 1:
        raise ValueError("Expected exactly one patient name to be found.")

    try:
        for ds in ct_series:
            orientation.require_dicom_patient_position(ds, "HFS")
    except ValueError as e:
        st.error(
            'The provided CT Series is not `"HFS"`. Only patient '
            'orientations of precisely `"HFS"` are supported.'
        )
        st.write(e)
        st.stop()

    st.write(
        """
        ## Extension of CT scan
        """
    )

    chosen_number_of_slices = st.number_input(
        "Number of slices to extend by (both sup and inf)", min_value=0, value=20
    )

    if not st.button("Extend CT and send back to Monaco"):
        st.stop()

    extended_ct_series = _extend.extend(ct_series, chosen_number_of_slices)
    _send_datasets(hostname, port, extended_ct_series)

    st.success(
        """
        The CT expansion and DICOM send to Monaco process was successful.
        Now use the import new DICOM files functionality within Monaco
        to retrieve the new extended dataset.
        """
    )


def _make_status_readable(returned_status):
    return pynetdicom.status.code_to_category(returned_status.Status)


def _send_datasets(hostname, port, datasets):
    connection_status = st.empty()
    status = st.empty()
    progress_bar = st.progress(0)

    total_number_of_datasets = len(datasets)

    with association(hostname, port) as assoc:
        returned_echo_status = _make_status_readable(assoc.send_c_echo())
        connection_status.write(f"DICOM connection status: `{returned_echo_status}`")

        for i, ds in enumerate(datasets):
            ds.TransferSyntaxUID = pydicom.uid.ImplicitVRLittleEndian
            ds.fix_meta_info(enforce_standard=True)

            returned_status = _make_status_readable(assoc.send_c_store(ds))
            slice_location = ds.ImagePositionPatient[-1]

            status.write(
                f"* Slice location: `{slice_location:.1f}`\n"
                f"* CT send status: `{returned_status}`"
            )

            progress_bar.progress((i + 1) / total_number_of_datasets)


@contextlib.contextmanager
def association(hostname, port):
    try:
        assoc = _get_association(hostname, port)
        yield assoc
    finally:
        assoc.release()


def _get_association(hostname, port):
    ae = _get_ae()
    assoc = ae.associate(hostname, int(port))

    return assoc


@st.cache(allow_output_mutation=True)
def _get_ae():
    ae = pynetdicom.AE()
    ae.network_timeout = None
    ae.acse_timeout = None
    ae.dimse_timeout = None
    ae.maximum_pdu_size = 0

    ae.add_requested_context(
        pynetdicom.sop_class.CTImageStorage  # pylint: disable=no-member
    )
    ae.add_requested_context(
        pynetdicom.sop_class.VerificationSOPClass  # pylint: disable=no-member
    )

    return ae


def _stop_button_if_cache_miss(button_text, func, *args, **kwargs):
    cache_key, mem_cache = _get_function_cache(func)
    value_key = _get_args_kwargs_hash(cache_key, func, *args, **kwargs)

    if not value_key in mem_cache:
        if not st.button(button_text):
            st.stop()


def _load_dicom_files(files):
    ct_series: List[pydicom.Dataset] = [
        pydicom.dcmread(path, force=True) for path in files
    ]

    return ct_series


@functools.lru_cache()
def _get_function_cache(
    func,
    hash_funcs=None,
    max_entries=None,
    ttl=None,
):
    from streamlit.caching import _mem_caches

    func_hasher = hashlib.new("md5")
    st.hashing.update_hash(
        (func.__module__, func.__qualname__),
        hasher=func_hasher,
        hash_funcs=None,
        hash_reason=st.hashing.HashReason.CACHING_FUNC_BODY,
        hash_source=func,
    )

    st.hashing.update_hash(
        func,
        hasher=func_hasher,
        hash_funcs=hash_funcs,
        hash_reason=st.hashing.HashReason.CACHING_FUNC_BODY,
        hash_source=func,
    )

    cache_key = func_hasher.hexdigest()
    mem_cache = _mem_caches.get_cache(cache_key, max_entries, ttl)

    return cache_key, mem_cache


def _get_args_kwargs_hash(cache_key, func, *args, hash_funcs=None, **kwargs):
    value_hasher = hashlib.new("md5")

    if args:
        st.hashing.update_hash(
            args,
            hasher=value_hasher,
            hash_funcs=hash_funcs,
            hash_reason=st.hashing.HashReason.CACHING_FUNC_ARGS,
            hash_source=func,
        )

    if kwargs:
        st.hashing.update_hash(
            kwargs,
            hasher=value_hasher,
            hash_funcs=hash_funcs,
            hash_reason=st.hashing.HashReason.CACHING_FUNC_ARGS,
            hash_source=func,
        )

    value_key = value_hasher.hexdigest()
    value_key = "%s-%s" % (value_key, cache_key)

    return value_key


_cached_load_dicom_files = st.cache(_load_dicom_files, allow_output_mutation=True)
