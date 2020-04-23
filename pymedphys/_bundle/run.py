# Copyright (C) 2019 Simon Biggs
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

import pathlib
import sys

import streamlit
import streamlit.bootstrap as bootstrap
from streamlit import config
from streamlit.ConfigOption import ConfigOption
from streamlit.server.Server import Server

import tornado

streamlit._is_running_with_streamlit = True


def _on_server_start(_):
    print(
        "{"
        f'"ip": "{config.get_option("server.address")}", '
        f'"port": {config.get_option("server.port")}'
        "}"
    )
    sys.stdout.flush()


def main():
    config._set_option("server.address", "127.0.0.1", ConfigOption.STREAMLIT_DEFINITION)
    config._set_option(
        "browser.gatherUsageStats", False, ConfigOption.STREAMLIT_DEFINITION
    )

    here = pathlib.Path(__file__).parent.resolve()

    run(str(here.joinpath("app.py")), "", "")


# ==================================================================================== #

# Copyright 2018-2020 Streamlit Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# ==================================================================================== #

# The following `run()` function is vendored and adjusted from:
# https://github.com/streamlit/streamlit/blob/018f49f5ddb0fa0119c17aaf2bff1bc7f25f70e1/lib/streamlit/bootstrap.py#L206-L240


def run(script_path, command_line, args):
    bootstrap._fix_sys_path(script_path)
    bootstrap._fix_matplotlib_crash()
    bootstrap._fix_tornado_crash()
    bootstrap._fix_sys_argv(script_path, args)
    bootstrap._fix_pydeck_mapbox_api_warning()

    bootstrap._set_up_signal_handler()

    ioloop = tornado.ioloop.IOLoop.current()

    server = Server(ioloop, script_path, command_line)

    server.start(_on_server_start)
    server.add_preheated_report_session()
    ioloop.start()


if __name__ == "__main__":
    main()
