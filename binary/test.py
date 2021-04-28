# Copyright (C) 2020 Simon Biggs

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import pathlib
import subprocess
import sys
import time
import socket
from contextlib import contextmanager

import psutil


HERE = pathlib.Path("__file__").parent.resolve()

BUILD = HERE.joinpath("build")
BUILD_DIST = BUILD.joinpath("dist")

REPO_ROOT = HERE.parent
CYPRESS = REPO_ROOT.joinpath("lib", "pymedphys", "tests", "e2e")


def main():
    if sys.platform == "win32":
        prepend = ""
    else:
        prepend = "wine "

    built_executables = list(BUILD_DIST.glob("pyinstaller-bundle-script/*.exe")) + list(
        BUILD_DIST.glob("*.exe")
    )
    if len(built_executables) != 1:
        raise ValueError("There should be only one executable.")

    exe = built_executables[0]

    with _process(f"{prepend}{exe}", cwd=BUILD_DIST, shell=True):
        subprocess.check_call("yarn", cwd=CYPRESS, shell=True)

        _wait_for_port(8501, timeout=300)

        # Given these commands are undergone also within the workflow,
        # should look to refactor these out.
        subprocess.check_call(
            f"{prepend}cmd.exe /C pymedphys dev tests --cypress",
            cwd=BUILD_DIST,
            shell=True,
        )

    # TODO: Re-enable lint.

    # subprocess.check_call(
    #     f"{prepend}cmd.exe /C pymedphys dev lint -v", cwd=BUILD_DIST, shell=True
    # )

    subprocess.check_call(
        f"{prepend}cmd.exe /C pymedphys dev tests -v", cwd=BUILD_DIST, shell=True
    )

    subprocess.check_call(
        f"{prepend}cmd.exe /C pymedphys dev tests -v --slow", cwd=BUILD_DIST, shell=True
    )


@contextmanager
def _process(*args, **kwargs):
    """Provides a process running with the provided arguments, useful for CLI unit tests

    Yields
    -------
    subprocess.Popen
        The process being run

    """
    proc = subprocess.Popen(*args, **kwargs)
    try:
        yield proc
    finally:
        for child in psutil.Process(proc.pid).children(recursive=True):
            child.kill()
        proc.kill()


def _wait_for_port(port, host="localhost", timeout=5.0):
    """Wait until a port starts accepting TCP connections.

    Args
    ----
        port : int
            Port number.
        host : str
            Host address on which the port should exist.
        timeout : float
            In seconds. How long to wait before raising errors.

    Raises
    ------
        TimeoutError
            The port isn't accepting connection after time specified in `timeout`.

    """
    start_time = time.perf_counter()
    while True:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                break
        except OSError as ex:
            time.sleep(0.01)
            if time.perf_counter() - start_time >= timeout:
                raise TimeoutError(
                    "Waited too long for the port {} on host {} to start accepting "
                    "connections.".format(port, host)
                ) from ex


if __name__ == "__main__":
    main()
