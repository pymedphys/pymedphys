# Copyright (C) 2026 Matthew Jennings

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Bound benchmark subprocesses, including Windows virtualenv launchers."""

import os
import signal
import subprocess
import time


class StudyStopped(Exception):
    """A user requested that the active measurement be discarded."""


def start_process(command, *, new_group=True, **kwargs):
    options = (
        {"creationflags": subprocess.CREATE_NO_WINDOW}
        if os.name == "nt"
        else {"start_new_session": new_group}
    )
    return subprocess.Popen(command, **options, **kwargs)


def terminate_process(process, *, new_group=True):
    """Kill the worker behind a Windows Python launcher, not just its parent.

    POSIX measurement workers inherit the driver's process group, so the
    supervisor can also stop them if the driver stalls. A measurement worker
    itself runs only threads; it does not create subprocesses.
    """
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
            timeout=3,
            check=False,
        )
    elif new_group:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    else:
        process.kill()
    process.wait(timeout=2)


def run_command(command, *, timeout, stop_file=None, **kwargs):
    """Run one measurement, polling its shared deadline and stop request."""
    deadline = time.monotonic() + timeout
    process = start_process(
        command,
        new_group=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        **kwargs,
    )
    try:
        while True:
            if stop_file is not None and stop_file.exists():
                raise StudyStopped
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(command, timeout)
            try:
                stdout, stderr = process.communicate(timeout=min(0.2, remaining))
                break
            except subprocess.TimeoutExpired:
                continue
    except BaseException:
        terminate_process(process, new_group=False)
        process.communicate(timeout=5)
        raise
    result = subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
    result.check_returncode()
    return result
