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


import streamlit as st

from pymedphys._streamlit import mosaiq as st_mosaiq
from pymedphys._streamlit import rerun as st_rerun

st_rerun.autoreload([st_mosaiq, st_rerun])


st.write("hoo moo boo")


# cursor = st_mosaiq.get_mosaiq_cursor("msqsql")
