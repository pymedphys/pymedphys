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

"""The attribution of the DICOM Standard, in each file drawn from it and in the
package's notices and documentation (D-001)."""

import importlib.metadata
import json
import pathlib
import shutil
import tomllib

from pymedphys._imports import pytest

import pymedphys
from pymedphys._dicom.deidentify import (
    attribution,
    pixel_risk,
    requirements,
    safe_private,
    standard,
    supplementary_actions,
    supplementary_concepts,
    temporal_roles,
    uid_roles,
)

NOTICE_FILE = "lib/pymedphys/_dicom/deidentify/_standard/NOTICE-DICOM.txt"
USER_GUIDE = (
    pathlib.Path(pymedphys.__file__).parent
    / "docs"
    / "users"
    / "background"
    / "dicom-deidentification.md"
)
PARTS = ("PS3.3", "PS3.4", "PS3.6", "PS3.15", "PS3.16")

# Each rule file curated by hand for one edition of a part, with its part and
# its loader.
RULE_FILES = {
    "head_and_neck_regions.toml": ("PS3.16", pixel_risk.load_head_and_neck_regions),
    "requirements.toml": ("PS3.15", requirements.load_requirements),
    "safe_private.toml": ("PS3.15", safe_private.load_safe_private_rules),
    "supplementary_actions.toml": (
        "PS3.6",
        supplementary_actions.load_supplementary_actions,
    ),
    "supplementary_concepts.toml": (
        "PS3.16",
        supplementary_concepts.load_supplementary_concepts,
    ),
    "temporal_roles.toml": ("PS3.6", temporal_roles.load_temporal_roles),
    "uid_roles.toml": ("PS3.6", uid_roles.load_uid_roles),
}
RULE_DIR = pathlib.Path(requirements.__file__).resolve().parent


def _words(text):
    return " ".join(text.split())


def _edition():
    return standard.load_table_e1_1().edition


def test_the_notice_names_the_trademark_and_disclaims_endorsement():
    assert attribution.LINK == "https://www.dicomstandard.org/"
    assert attribution.NOTICE.startswith("DICOM® is the registered trademark ")
    assert attribution.NOTICE.endswith(
        "NEMA does not endorse, sponsor, or certify PyMedPhys."
    )
    assert attribution.acknowledgement("PS3.15", "2026d") == (
        "DICOM PS3.15 2026d, © NEMA"
    )


def test_every_generated_table_carries_the_attribution_of_its_part_and_edition():
    names = sorted(path.name for path in standard.STANDARD_DIR.glob("*.json"))

    assert names
    for name in names:
        document = json.loads(
            (standard.STANDARD_DIR / name).read_text(encoding="utf-8")
        )
        part = document["table"].split(" ", 1)[0]
        assert part in PARTS
        assert document["edition"] == _edition()
        assert {
            key: document[key] for key in ("acknowledgement", "link", "notice")
        } == attribution.fields(part, _edition()), name


@pytest.mark.parametrize("name", sorted(RULE_FILES))
def test_every_rule_file_carries_the_attribution_of_its_part_and_edition(name):
    part, _ = RULE_FILES[name]
    document = tomllib.loads((RULE_DIR / name).read_text(encoding="utf-8"))

    assert document["edition"] == _edition()
    assert {
        key: document[key] for key in ("acknowledgement", "link", "notice")
    } == attribution.fields(part, _edition())


def test_every_rule_file_with_an_acknowledgement_is_checked_here():
    acknowledged = {
        path.name
        for path in RULE_DIR.glob("*.toml")
        if "acknowledgement" in tomllib.loads(path.read_text(encoding="utf-8"))
    }

    assert acknowledged == set(RULE_FILES)


def _without(text, field):
    lines = [line for line in text.splitlines() if not line.startswith(f"{field} =")]
    assert len(lines) == len(text.splitlines()) - 1
    return "\n".join(lines) + "\n"


@pytest.mark.parametrize("field", ["link", "notice"])
@pytest.mark.parametrize("name", sorted(RULE_FILES))
def test_a_rule_file_without_the_link_or_notice_is_rejected(tmp_path, name, field):
    _, load = RULE_FILES[name]
    path = tmp_path / name
    path.write_text(
        _without((RULE_DIR / name).read_text(encoding="utf-8"), field),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=rf"^{name} (lacks|is not)"):
        load(path)


@pytest.mark.parametrize(
    "change",
    [
        {"link": "https://dicom.nema.org/"},
        {"notice": "DICOM is a trademark."},
        {"link": None},
        {"notice": None},
    ],
)
def test_a_generated_table_without_the_link_or_notice_is_rejected(tmp_path, change):
    path = tmp_path / "e1_1.json"
    shutil.copy(standard.STANDARD_DIR / "e1_1.json", path)
    document = json.loads(path.read_text(encoding="utf-8"))
    for key, value in change.items():
        if value is None:
            del document[key]
        else:
            document[key] = value
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(
        standard.StandardTableError,
        match="lacks (the link to the DICOM Standard|NEMA's trademark notice)",
    ):
        standard.load_table_e1_1(path)


def test_the_notice_file_names_each_part_s_attribution():
    text = attribution.NOTICE_PATH.read_text(encoding="utf-8")
    words = _words(text)

    assert f"edition {_edition()}" in words
    for part in PARTS:
        assert attribution.acknowledgement(part, _edition()) in words
    assert attribution.LINK in words
    assert _words(attribution.NOTICE) in words
    assert _words(attribution.DISCLAIMER) in words
    for path in standard.STANDARD_DIR.glob("*.json"):
        assert f"\n{path.name}\n" in text


# Installed metadata and package files, not pyproject.toml and the README, so
# that these also run from an installed wheel, as the published-release tests
# do.


def test_the_package_s_description_carries_the_attribution():
    # The description, from the README, is the package's PyPI page.
    description = _words(importlib.metadata.metadata("pymedphys").get_payload())

    for part in PARTS:
        assert attribution.acknowledgement(part, _edition()) in description
    assert attribution.LINK in description
    assert _words(attribution.NOTICE) in description
    assert _words(attribution.DISCLAIMER) in description


def test_the_package_lists_the_notice_among_its_licence_files():
    metadata = importlib.metadata.metadata("pymedphys")

    assert NOTICE_FILE in metadata.get_all("License-File")
    assert NOTICE_FILE.endswith(f"/_standard/{attribution.NOTICE_FILE}")


def test_the_user_guide_carries_the_attribution():
    text = _words(USER_GUIDE.read_text(encoding="utf-8"))

    for part in PARTS:
        assert attribution.acknowledgement(part, _edition()) in text
    assert attribution.LINK in text
    assert _words(attribution.NOTICE) in text
    assert _words(attribution.DISCLAIMER) in text
