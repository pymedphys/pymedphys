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

# pylint: disable = protected-access

from pymedphys._imports import streamlit as st

from . import patches


def main(args):
    start_streamlit_server(args.path, {})


def start_streamlit_server(script_path, config):
    st.bootstrap.load_config_options(flag_options=config)
    patches.apply_streamlit_server_patches()

    st._is_running_with_streamlit = True
    st.bootstrap.run(script_path, "", [], flag_options={})
