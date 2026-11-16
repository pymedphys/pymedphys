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

"""The redaction review app's page script (D-059), driven in Node.js.

``_redaction_review_page.cjs`` runs the page's script against a minimal
stand-in for the browser and a fake server, and drives the handlers that
the script registers. Each scenario checks one property that the server
and the attestation cannot check for themselves: a region stays on the
frame where it was drawn, the page reports work saved only once the server
has confirmed its latest revision, and a frame counts as shown only while
the page is visible.
"""

import pathlib
import shutil
import subprocess

from pymedphys._imports import pytest

HERE = pathlib.Path(__file__).parent
HARNESS = HERE / "_redaction_review_page.cjs"
APP = HERE.parents[1] / "_dicom" / "deidentify" / "redaction_review_static" / "app.js"
NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="needs Node.js to run the page's script")
@pytest.mark.parametrize(
    "scenario",
    [
        "draw-then-change-frame",
        "draw-then-change-instance",
        "resize-then-change-frame",
        "save-indicator",
        "shown-only-when-visible",
    ],
)
def test_page(scenario):
    assert NODE is not None
    result = subprocess.run(
        [NODE, str(HARNESS), str(APP), scenario],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == f"{scenario}: passed\n"
