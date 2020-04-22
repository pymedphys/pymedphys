# pylint: disable = protected-access

import pathlib
import sys

import streamlit
import streamlit.bootstrap as bootstrap
import tornado
from streamlit import config
from streamlit.ConfigOption import ConfigOption
from streamlit.server.Server import Server

streamlit._is_running_with_streamlit = True


def _on_server_start(_):
    print(
        "{"
        f'"ip": "{config.get_option("server.address")}", '
        f'"port": {config.get_option("server.port")}'
        "}"
    )
    sys.stdout.flush()


def run(script_path, command_line, args):
    """Run a script in a separate thread and start a server for the app.
    This starts a blocking ioloop.
    Parameters
    ----------
    script_path : str
    command_line : str
    args : [str]
    """
    bootstrap._fix_sys_path(script_path)
    bootstrap._fix_matplotlib_crash()
    bootstrap._fix_tornado_crash()
    bootstrap._fix_sys_argv(script_path, args)
    bootstrap._fix_pydeck_mapbox_api_warning()

    # Install a signal handler that will shut down the ioloop
    # and close all our threads
    bootstrap._set_up_signal_handler()

    ioloop = tornado.ioloop.IOLoop.current()

    # Create and start the server.
    server = Server(ioloop, script_path, command_line)

    sys.stdout.flush()
    server.start(_on_server_start)

    # (Must come after start(), because this starts a new thread and start()
    # may call sys.exit() which doesn't kill other threads.
    server.add_preheated_report_session()

    # Start the ioloop. This function will not return until the
    # server is shut down.
    ioloop.start()


def main():
    config._set_option("server.address", "127.0.0.1", ConfigOption.STREAMLIT_DEFINITION)
    config._set_option(
        "browser.gatherUsageStats", False, ConfigOption.STREAMLIT_DEFINITION
    )

    here = pathlib.Path(__file__).parent.resolve()

    run(str(here.joinpath("app.py")), "", "")


if __name__ == "__main__":
    main()
