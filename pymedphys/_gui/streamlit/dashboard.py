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

import importlib

import streamlit as st

from pymedphys._streamlit import misc as st_misc
from pymedphys._streamlit import mosaiq as st_mosaiq

THIS = importlib.import_module(__name__)

wait_for_rerun = st_misc.auto_reload_on_module_changes(THIS, [st_mosaiq, st_misc])

st.write("hoo foo moo")

# goo gg aa

wait_for_rerun()

cursor = st_mosaiq.get_mosaiq_cursor("msqsql")
