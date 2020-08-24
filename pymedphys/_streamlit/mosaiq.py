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

import functools

import streamlit as st

from pymedphys._mosaiq import connect as msq_connect

generic_password_input = functools.partial(st.text_input, type="password")


def add_label(function, label):
    return functools.partial(function, label=label)


def create_user_input():
    # TODO: Wrap st.text_input and call st.stop() if it is empty
    pass


@st.cache(allow_output_mutation=True, suppress_st_warning=True)
def get_mosaiq_cursor(server):

    password_input = add_label(generic_password_input, server)
    user_input = add_label(st.text_input, server)

    _, cursor = msq_connect.single_connect(
        server, user_input=user_input, password_input=password_input, output=st.write
    )
    return cursor
