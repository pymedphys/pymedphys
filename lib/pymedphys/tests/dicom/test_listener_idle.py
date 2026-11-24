# Copyright (C) 2026 Jeff

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""The DICOM listener CLI must yield while its server handles requests."""

import subprocess
import sys
import textwrap


def test_listener_cli_yields_after_starting_server():
    # Use a child process so a regression to a busy loop is terminated rather
    # than leaving a background thread spinning in the test runner.
    program = textwrap.dedent("""
        from types import SimpleNamespace
        import time
        from pymedphys._dicom.connect import listen

        class Listener:
            port = 0
            started = False
            def __init__(self, **kwargs):
                pass
            def start(self):
                Listener.started = True
            def stop(self):
                pass

        def wait(seconds):
            assert Listener.started
            assert seconds > 0
            raise InterruptedError("synthetic stop")

        listen.DicomListener = Listener
        time.sleep = wait
        args = SimpleNamespace(host="127.0.0.1", port=0, aetitle="TEST",
                               storage_directory=None)
        try:
            listen.listen_cli(args)
        except InterruptedError:
            print("yielded after startup")
    """)
    result = subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "yielded after startup"
