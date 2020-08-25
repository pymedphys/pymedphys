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

import streamlit as st

from pymedphys._mosaiq import connect as msq_connect


def create_user_input(server, input_type="default"):
    def user_input():
        result = st.text_input(label=server, type=input_type)
        if not result:
            st.stop()

        return result

    return user_input


@st.cache(allow_output_mutation=True, suppress_st_warning=True)
def get_mosaiq_cursor(server):
    return uncached_get_mosaiq_cursor(server)


@st.cache(allow_output_mutation=True, suppress_st_warning=True)
def get_mosaiq_cursor_in_bucket(server):
    """This allows the output cursor cache to be mutated by the user code
    """
    return {"cursor": uncached_get_mosaiq_cursor(server)}


def uncached_get_mosaiq_cursor(server):
    password_input = create_user_input(server, input_type="password")
    user_input = create_user_input(server)

    _, cursor = msq_connect.single_connect(
        server, user_input=user_input, password_input=password_input, output=st.write
    )
    return cursor
