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

import functools
import hashlib
import pathlib
import re
from typing import List

from pymedphys._imports import pydicom
from pymedphys._imports import streamlit as st

from pymedphys._dicom.ct import extend as _extend
from pymedphys._streamlit import categories
from pymedphys._streamlit.utilities import config as st_config

CATEGORY = categories.PLANNING
TITLE = "Monaco Extend CT"


def main():
    config = st_config.get_config()

    site_directory_map = {}
    for site_config in config["site"]:
        site = site_config["name"]
        try:
            site_directory_map[site] = {
                "focal_data": site_config["monaco"]["focaldata"],
                "hostname": site_config["monaco"]["hostname"],
                "port": site_config["monaco"]["dicom_port"],
            }
        except KeyError:
            continue

    chosen_site = st.radio("Site", list(site_directory_map.keys()))
    directories = site_directory_map[chosen_site]

    focal_data = pathlib.Path(directories["focal_data"])
    dicom_export = focal_data.joinpath("DCMXprtFile")

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

    chosen_patient_id = st.radio("Patient ID", patient_ids)

    ct_dicom_files = list(dicom_export.glob(f"{chosen_patient_id}_*_image*.DCM"))
    _stop_button_if_cache_miss("Load files", _load_dicom_files, ct_dicom_files)

    ct_datasets = _cached_load_dicom_files(ct_dicom_files)
    patient_name = {header.PatientName for header in ct_datasets}
    st.write(patient_name)

    # slice_locations = [dataset.SliceLocation for dataset in ct_datasets]
    # st.write(slice_locations)

    chosen_number_of_slices = st.number_input(
        "Number of slices to extend by", min_value=0, value=20
    )

    extended_ct_datasets = _extend_datasets(ct_datasets, chosen_number_of_slices)


@st.cache
def _extend_datasets(datasets, number_of_slices):
    deque_datasets = _extend.convert_datasets_to_deque(datasets)
    _extend.extend_datasets(deque_datasets, 0, number_of_slices)
    _extend.extend_datasets(deque_datasets, -1, number_of_slices)

    return deque_datasets


def _stop_button_if_cache_miss(button_text, func, *args, **kwargs):
    cache_key, mem_cache = _get_function_cache(func)
    value_key = _get_args_kwargs_hash(cache_key, func, *args, **kwargs)

    if not value_key in mem_cache:
        if not st.button(button_text):
            st.stop()


def _load_dicom_files(files):
    ct_datasets: List[pydicom.Dataset] = [
        pydicom.dcmread(path, force=True) for path in files
    ]

    return ct_datasets


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
