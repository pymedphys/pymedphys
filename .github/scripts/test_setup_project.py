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

"""Exercise the setup shell and dependency overlays without network access."""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ACTION = Path(__file__).resolve().parents[1] / "actions/setup-project/action.yml"
BASH = shutil.which("bash") or shutil.which("sh")
UV = shutil.which("uv")


class SetupProjectTests(unittest.TestCase):
    @unittest.skipUnless(BASH, "The setup action requires Bash")
    def test_requested_environment_is_reused_only_after_a_successful_sync(self):
        step = (
            ACTION.read_text(encoding="utf-8")
            .split("    - name: Install dependencies\n", 1)[1]
            .split("\n    # Jobs", 1)[0]
        )
        self.assertIn("if: inputs.install-project == 'true'", step)
        mappings = dict(
            re.findall(r"^        (\w+): \$\{\{ inputs\.(\w+) \}\}", step, re.M)
        )
        script = "\n".join(
            line[8:] for line in step.split("      run: |\n", 1)[1].splitlines()
        )
        for status in (0, 7):
            with (
                self.subTest(sync_status=status),
                tempfile.TemporaryDirectory() as directory,
            ):
                directory = Path(directory)
                args = directory / "args"
                github_env = directory / "environment"
                env = dict(
                    os.environ,
                    GITHUB_ENV=github_env.as_posix(),
                    SYNC_LOG=args.as_posix(),
                    SYNC_STATUS=str(status),
                )
                env.update(
                    {
                        key: {"extras": "tests ai", "groups": "lint docs"}[value]
                        for key, value in mappings.items()
                    }
                )
                mock = 'uv() { printf "%s\\n" "$@" > "$SYNC_LOG"; return "$SYNC_STATUS"; }\n'
                result = subprocess.run(
                    [BASH, "-c", mock + script],
                    env=env,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, status, result.stderr)
                self.assertEqual(
                    args.read_text().splitlines(),
                    [
                        "sync",
                        "--frozen",
                        "--no-default-groups",
                        "--extra",
                        "tests",
                        "--extra",
                        "ai",
                        "--group",
                        "lint",
                        "--group",
                        "docs",
                    ],
                )
                if status:
                    self.assertFalse(github_env.exists())
                else:
                    self.assertEqual(
                        github_env.read_text().splitlines(),
                        ["UV_NO_SYNC=1", "UV_NO_DEFAULT_GROUPS=1"],
                    )

    @unittest.skipUnless(UV, "The dependency overlay requires uv")
    def test_no_sync_keeps_dependency_overlays_available(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            # Resolving this project's dependency would fail offline. Reusing
            # its prepared environment must still permit the local overlay.
            (directory / "pyproject.toml").write_text(
                '[project]\nname="setup-test"\nversion="0"\ndependencies=["unavailable-setup-test-package"]\n'
            )
            wheel = directory / "setup_overlay-1.0-py3-none-any.whl"
            with zipfile.ZipFile(wheel, "w") as archive:
                archive.writestr("setup_overlay.py", "VALUE = 42\n")
                archive.writestr(
                    "setup_overlay-1.0.dist-info/METADATA",
                    "Metadata-Version: 2.3\nName: setup-overlay\nVersion: 1.0\n",
                )
                archive.writestr(
                    "setup_overlay-1.0.dist-info/WHEEL",
                    "Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
                )
                archive.writestr("setup_overlay-1.0.dist-info/RECORD", "")
            command = [UV, "--offline", "--cache-dir", str(directory / "cache")]
            subprocess.run(
                [
                    *command,
                    "venv",
                    "--python",
                    sys.executable,
                    str(directory / ".venv"),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            result = subprocess.run(
                [
                    *command,
                    "run",
                    "--project",
                    str(directory),
                    "--with",
                    str(wheel),
                    "python",
                    "-c",
                    "import setup_overlay; print(setup_overlay.VALUE)",
                ],
                env=dict(os.environ, UV_NO_SYNC="1", UV_NO_DEFAULT_GROUPS="1"),
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.stdout.strip(), "42")
            self.assertFalse((directory / "uv.lock").exists())


if __name__ == "__main__":
    unittest.main()
