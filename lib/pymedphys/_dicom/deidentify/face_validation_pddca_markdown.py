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

"""The PDDCA face block check's counts as CommonMark (D-054).

:func:`markdown` renders
:func:`~pymedphys._dicom.deidentify.face_validation_pddca.summarise`'s
counts, and nothing else, so the page shows no more than the JSON does.
From its counts of cases on, the page is the HaN-Seg check's.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .face_validation_markdown import _bins, body


def markdown(summary: Mapping[str, Any]) -> str:
    """Render the counts as a CommonMark page."""
    data = summary["data"]
    software = summary["software"]
    nerves = summary["optic_nerves_of_defaced_series"]
    lines = [
        f"# Face block check on {data['name']}",
        "",
        "Each case's CT, given to the face block finder and the CT defacer "
        "as a de-identification run under the Clean Recognizable Visual "
        "Features Option gives them a CT series, and the globes found "
        "compared with the anterior tips of the case's optic nerve masks. "
        "Only counts are shown: no value, image, or case of the data set.",
        "",
        summary["held_out"],
        "",
        "| About | |",
        "| --- | --- |",
        f"| Data set | {data['name']} {data['version']}, {data['licence']} |",
        *(
            f"| File | `{each['file']}`, doi:{each['doi']}, {each['size']} bytes, "
            f"MD5 `{each['md5']}`, SHA-256 `{each['sha256']}` |"
            for each in data["files"]
        ),
        "| Software | "
        + ", ".join(f"{name} {version}" for name, version in software.items())
        + " |",
        "",
        f"The data set: {data['citation']}.",
        "",
        "## Defaced series against the optic nerves",
        "",
        f"Defaced series with both optic nerves' masks: {nerves['series']}; "
        f"without: {nerves['without_both_nerves']}. Series whose globes found "
        f"are nearer the other side's nerve tip: {nerves['sides_swapped']}.",
        "",
        *_bins(
            "Distance from each globe found to its optic nerve's anterior tip",
            nerves["globe_to_nerve_tip"],
            "Globes",
        ),
        *_bins(
            "Depth of each optic nerve's anterior tip behind its globe found, "
            "along the block's anterior",
            nerves["nerve_tip_behind_globe"],
            "Globes",
        ),
    ]
    return "\n".join(lines + body(summary)) + "\n"
