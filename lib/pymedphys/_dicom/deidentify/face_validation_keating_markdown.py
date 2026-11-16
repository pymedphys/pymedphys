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

"""The Keating face block check's measures as CommonMark (D-058).

:func:`markdown` renders
:func:`~pymedphys._dicom.deidentify.face_validation_keating.check_keating`'s
summary, and nothing else, so the page shows no more than the JSON does.
Each series' sections are the Visible Human check's.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .face_validation_vhp_markdown import _head


def markdown(summary: Mapping[str, Any]) -> str:
    """Render the summary as a CommonMark page."""
    source = summary["source"]
    reference = summary["reference"]
    lines = [
        "# Face block check on Steven Keating's cranial CT",
        "",
        f"**{source['attribution']}** {source['notice']}",
        "",
        f"{summary['held_out']}",
        "",
        "Each CT series is given to the face block finder three ways: as a "
        "de-identification run under the Clean Recognizable Visual Features "
        "Option gives it a series (*engine*); each stack of slices that share "
        "a geometry as a series of its own (*by stack*); and the slices within "
        "the head reach resampled onto one grid (*resampled*), which a run "
        "does not do. Each block found, and a *reference* block placed from "
        "globe centres placed by hand, is given to the CT defacer slice by "
        "slice.",
        "",
        "| About | |",
        "| --- | --- |",
        f"| Record | <{source['record']}>, doi:{source['record_doi']} |",
        f"| File | `{source['file']}`, {source['size']} bytes, MD5 "
        f"`{source['md5']}`, SHA-256 `{source['sha256']}` |",
        f"| Licence | {source['licence']}, <{source['licence_url']}> |",
        f"| Reference globes | placed by hand within {reference['tolerance_mm']} "
        f"mm; spheres of {reference['radius_mm']} mm |",
        "| Software | "
        + ", ".join(
            f"{name} {version}" for name, version in summary["software"].items()
        )
        + " |",
        "",
        "## Outcomes",
        "",
        "| Series | Covers | Files | Engine | By stack | Resampled |",
        "| --- | --- | ---: | --- | --- | --- |",
    ]
    for each in summary["series"]:
        if "crashed" in each:
            lines.append(
                f"| `{each['series']}` | {each['description']} | {each['files']} "
                f"| crashed: `{each['crashed']}` | | |"
            )
            continue
        stacks = ", ".join(
            f"{stack['stack']}: `{stack['outcome']}`" for stack in each["by_stack"]
        )
        lines.append(
            f"| `{each['series']}` | {each['description']} | {each['files']} "
            f"| `{each['engine']['outcome']}` | {stacks} "
            f"| `{each['resampled']['outcome']}` |"
        )
    for each in summary["series"]:
        if "crashed" not in each:
            lines += _head(each)
    lines += [
        "## Settings",
        "",
        "| Setting | Value |",
        "| --- | --- |",
        *(f"| `{name}` | {value} |" for name, value in summary["settings"].items()),
        "",
        f"{source['attribution']} {source['notice']}",
        "",
    ]
    # Each series' sections begin and end with a blank line, so two can
    # meet; one is kept, as markdownlint's MD012 asks.
    kept = [
        line
        for index, line in enumerate(lines)
        if line or index == 0 or lines[index - 1]
    ]
    return "\n".join(kept)
