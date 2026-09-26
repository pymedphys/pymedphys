"""Protect background runs from concurrent writers and oversized uploads."""

import tempfile
import unittest
import zipfile
from pathlib import Path

from gamma_scaling_background import RunLock, bundle, busy


class BackgroundIntegrityTests(unittest.TestCase):
    def test_lock_blocks_another_writer_and_releases_on_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            self.assertFalse(busy(output))
            with RunLock(output):
                self.assertTrue(busy(output))
                with self.assertRaises(OSError):
                    with RunLock(output):
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
