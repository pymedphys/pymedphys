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


from pymedphys._streamlit.server.start import main


def streamlit_cli(subparsers):
    streamlit_parser = subparsers.add_parser(
        "streamlit", help=("Wrapper for streamlit CLI")
    )
    streamlit_subparser = streamlit_parser.add_subparsers()
    streamlit_run = streamlit_subparser.add_parser("run")

    streamlit_run.add_argument("path")
    streamlit_run.set_defaults(func=main)

    return streamlit_parser
