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

"""Protect background runs from concurrent writers and oversized uploads."""

import json
import subprocess
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from gamma_scaling_background import RunLock, bundle, busy, remaining_budget, supervise
from gamma_scaling_process import StudyStopped, run_command


class BackgroundIntegrityTests(unittest.TestCase):
    def test_resuming_does_not_reset_the_wall_clock_budget(self):
        config = {"deadline_unix": 7300, "max_seconds": 7200}
        with patch("gamma_scaling_background.time.time", return_value=7000):
            self.assertEqual(remaining_budget(config), 300)
        with patch("gamma_scaling_background.time.time", return_value=7400):
            self.assertEqual(remaining_budget(config), 0)

    def test_worker_timeout_kills_the_virtualenv_python(self):
        with tempfile.TemporaryDirectory() as directory:
            started, finished = (
                Path(directory) / "started",
                Path(directory) / "finished",
            )
            code = (
                f"from pathlib import Path; import time; Path({str(started)!r}).touch(); "
                f"time.sleep(2); Path({str(finished)!r}).touch()"
            )
            with self.assertRaises(subprocess.TimeoutExpired):
                run_command([sys.executable, "-c", code], timeout=0.8)
            self.assertTrue(started.exists())
            time.sleep(1.5)
            self.assertFalse(
                finished.exists(), "The actual Python worker survived its launcher"
            )

    def test_stop_request_interrupts_an_active_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            stop = Path(directory) / "stop.request"
            code = f"from pathlib import Path; import time; Path({str(stop)!r}).touch(); time.sleep(30)"
            before = time.monotonic()
            with self.assertRaises(StudyStopped):
                run_command([sys.executable, "-c", code], timeout=30, stop_file=stop)
            self.assertLess(time.monotonic() - before, 3)

    def test_supervisor_watchdog_stops_descendants_and_bundles_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            source = output / "benchmark-source"
            source.mkdir()
            (output / "study").mkdir()
            (output / "study/results.json").write_text('{"complete": false}')
            # A stalled report from an older attempt must not be bundled.
            (output / "study/summary.csv").write_text("stale table")
            started, finished = output / "started", output / "finished"
            child = (
                f"from pathlib import Path; import time; Path({str(started)!r}).touch(); "
                f"time.sleep(3); Path({str(finished)!r}).touch()"
            )
            (source / "gamma_scaling.py").write_text(
                f"import subprocess,sys,time\nsubprocess.Popen([sys.executable, '-c', {child!r}])\ntime.sleep(30)\n"
            )
            config = {
                "repo": str(output),
                "previous": "old",
                "current": "new",
                "threads": 1,
                "worker_timeout": 30,
                "quick": True,
                "max_seconds": 20,
                "deadline_unix": time.time() + 4,
            }
            (output / "run-config.json").write_text(json.dumps(config))
            before = time.monotonic()
            self.assertEqual(supervise(output), 0)
            self.assertLess(time.monotonic() - before, 4.5)
            state = json.loads((output / "run.json").read_text())
            self.assertEqual(state["state"], "budget_exhausted")
            self.assertTrue(state["watchdog"])
            self.assertFalse(state["report_complete"])
            # This deliberately tiny remaining budget preserves raw evidence
            # rather than attempting compression without termination time.
            self.assertFalse((output / "gamma-scaling-upload.zip").exists())
            with zipfile.ZipFile(bundle(output)) as archive:
                self.assertIn("study/results.json", archive.namelist())
                self.assertNotIn("study/summary.csv", archive.namelist())
            self.assertTrue(started.exists())
            time.sleep(1.5)
            self.assertFalse(finished.exists(), "The watchdog left a child running")

    def test_lock_blocks_another_writer_and_releases_on_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            self.assertFalse(busy(output))
            with RunLock(output):
                self.assertTrue(busy(output))
                with self.assertRaises(OSError), RunLock(output):
                    self.fail("A second writer acquired the active study")
            self.assertFalse(busy(output))

    def test_bundle_includes_evidence_and_excludes_working_arrays(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            arrays = output / "study/arrays"
            arrays.mkdir(parents=True)
            (arrays / "unfinished.npy").write_bytes(b"temporary array")
            (output / "study/results.json").write_text('{"complete": false}')
            (output / "run.log").write_text("A useful diagnostic\n")
            (output / "run.json").write_text('{"state": "stopped"}')
            with zipfile.ZipFile(bundle(output)) as archive:
                self.assertEqual(
                    set(archive.namelist()),
                    {"study/results.json", "run.log", "run.json"},
                )
                self.assertEqual(
                    archive.read("run.log"), (output / "run.log").read_bytes()
                )


if __name__ == "__main__":
    unittest.main()
