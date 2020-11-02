from pymedphys._imports import pymssql
from pymedphys._imports import streamlit as st

import pymedphys


@st.cache(allow_output_mutation=True)
def delivery_from_trf(pandas_table):
    return pymedphys.Delivery._from_pandas(  # pylint: disable = protected-access
        pandas_table
    )


@st.cache(allow_output_mutation=True)
def delivery_from_icom(icom_stream):
    return pymedphys.Delivery.from_icom(icom_stream)


@st.cache(allow_output_mutation=True)
def delivery_from_tel(tel_path):
    return pymedphys.Delivery.from_monaco(tel_path)


@st.cache(hash_funcs={pymssql.Cursor: id}, allow_output_mutation=True)
def delivery_from_mosaiq(cursor_and_field_id):
    cursor, field_id = cursor_and_field_id
    return pymedphys.Delivery.from_mosaiq(cursor, field_id)


def cached_deliveries_loading(inputs, method_function):
    deliveries = []

    for an_input in inputs:
        deliveries += [method_function(an_input)]

    return deliveries
