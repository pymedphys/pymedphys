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

"""The LOINC codes that PyMedPhys includes, with their LOINC names and notice (D-001)."""

import importlib.metadata
import re

from pymedphys._imports import pytest, tomlkit

from pymedphys._dicom.deidentify import (
    loinc_terms,
    structured_content,
    supplementary_concepts,
)

NOTICE_FILE = "lib/pymedphys/_dicom/deidentify/_loinc/LICENSE-LOINC.txt"
# Each code, with its LONG_COMMON_NAME and STATUS in LOINC 2.83's LOINC
# Table, read from the release.
LOINC_2_83 = {
    "11955-2": ("Deprecated Last menstrual period", "DEPRECATED"),
    "11778-8": ("Delivery date Estimated", "ACTIVE"),
    "11951-1": ("Fetal [Identifier] Identifier", "ACTIVE"),
    "11329-0": ("History general Narrative - Reported", "ACTIVE"),
    "18785-6": ("Radiology Reason for study (narrative)", "ACTIVE"),
    "18118-0": ("Left ventricular Segmental wall motion Narrative by US", "ACTIVE"),
    "74711-3": ("Unique device identifier", "ACTIVE"),
    "8302-2": ("Body height", "ACTIVE"),
    "29463-7": ("Body weight", "ACTIVE"),
    "8277-6": ("Body surface area", "ACTIVE"),
}


def _words(text):
    return re.sub(r"\s+", " ", text).strip()


def test_the_shipped_terms_are_those_of_loinc_2_83():
    loaded = loinc_terms.load_loinc_terms()

    assert loaded.loinc_version == "2.83"
    assert {
        code: (term.long_common_name, term.status)
        for code, term in loaded.terms.items()
    } == LOINC_2_83
    assert all(code == term.loinc_num for code, term in loaded.terms.items())


def test_the_terms_are_exactly_the_loinc_codes_that_the_engine_looks_up():
    table = {
        concept.code_value
        for concept in structured_content.load_table_e3_4_1().concepts
        if concept.scheme_designator == "LN"
    }
    rows = {
        concept.code_value
        for concept in supplementary_concepts.load_supplementary_concepts().concepts
        if concept.scheme_designator == "LN"
    }

    assert len(table) == 7
    assert rows == {"8302-2", "29463-7", "8277-6"}
    assert set(loinc_terms.load_loinc_terms().terms) == table | rows


def test_the_notice_file_carries_loinc_s_notice_and_licence():
    text = _words(loinc_terms.NOTICE_PATH.read_text(encoding="utf-8"))

    assert loinc_terms.NOTICE_PATH.parent == loinc_terms.LOINC_TERMS_PATH.parent
    assert loinc_terms.NOTICE in text
    assert "LOINC version 2.83" in text
    # Section 10.1 of the licence gives the notice, which the file holds
    # twice: as the notice, and in the licence.
    assert text.count(loinc_terms.NOTICE.removesuffix(" Inc.")) == 2


# Installed metadata, not pyproject.toml and the README, so that these also
# run from an installed wheel, as the published-release tests do.


def test_the_package_s_description_carries_loinc_s_notice():
    # The description, from the README, is the package's PyPI page.
    description = importlib.metadata.metadata("pymedphys").get_payload()

    assert loinc_terms.NOTICE in _words(description)


def test_the_package_declares_loinc_s_licence():
    metadata = importlib.metadata.metadata("pymedphys")

    assert "LicenseRef-LOINC" in metadata["License-Expression"].split(" AND ")
    assert NOTICE_FILE in metadata.get_all("License-File")


@pytest.mark.parametrize(
    "code, valid",
    [
        ("29463-7", True),
        ("8302-2", True),
        ("8277-6", True),
        ("11955-2", True),
        ("29463-6", False),
        ("29463", False),
        ("029463-7", False),
        ("12345678-0", False),
        (" 29463-7", False),
        (29463, False),
    ],
)
def test_a_loinc_code_has_a_valid_check_digit(code, valid):
    assert loinc_terms.is_loinc_num(code) is valid


def _document(terms=None, **changes):
    document = {
        "schema": loinc_terms.SCHEMA,
        "loinc_version": "2.83",
        "term": terms
        if terms is not None
        else [
            {
                "LOINC_NUM": "29463-7",
                "LONG_COMMON_NAME": "Body weight",
                "STATUS": "ACTIVE",
            }
        ],
    }
    document.update(changes)
    return {key: value for key, value in document.items() if value is not None}


def _write(tmp_path, document):
    path = tmp_path / "loinc_terms.toml"
    path.write_text(tomlkit.dumps(document), encoding="utf-8")
    return path


def _term(**changes):
    term = {
        "LOINC_NUM": "29463-7",
        "LONG_COMMON_NAME": "Body weight",
        "STATUS": "ACTIVE",
    }
    term.update(changes)
    return {key: value for key, value in term.items() if value is not None}


def test_a_valid_file_loads(tmp_path):
    loaded = loinc_terms.load_loinc_terms(_write(tmp_path, _document()))

    assert loaded.terms["29463-7"] == loinc_terms.LoincTerm(
        "29463-7", "Body weight", "ACTIVE"
    )
    with pytest.raises(TypeError):
        loaded.terms["8302-2"] = loaded.terms["29463-7"]


@pytest.mark.parametrize(
    "document, message",
    [
        (_document(schema="other/1"), "schema"),
        (_document(loinc_version=None), "LOINC version"),
        (_document(loinc_version="2.83a"), "LOINC version"),
        (_document(terms=[]), "array of tables"),
        (_document(terms=[_term(DisplayName="Weight")]), "exactly the fields"),
        (_document(terms=[_term(STATUS=None)]), "exactly the fields"),
        (_document(terms=[_term(LOINC_NUM="29463-6")]), "check digit"),
        (_document(terms=[_term(LONG_COMMON_NAME="")]), "long common name"),
        (_document(terms=[_term(LONG_COMMON_NAME=" Body weight")]), "long common"),
        (_document(terms=[_term(LONG_COMMON_NAME="x" * 256)]), "long common name"),
        (_document(terms=[_term(STATUS="RETIRED")]), "status"),
        (_document(terms=[_term(), _term()]), "term 2 repeats 29463-7"),
    ],
)
def test_a_malformed_file_is_refused(tmp_path, document, message):
    with pytest.raises(loinc_terms.LoincTermsError, match=message):
        loinc_terms.load_loinc_terms(_write(tmp_path, document))


def test_an_unreadable_file_is_refused(tmp_path):
    path = tmp_path / "loinc_terms.toml"
    path.write_text("term = [", encoding="utf-8")

    with pytest.raises(loinc_terms.LoincTermsError, match="could not be read"):
        loinc_terms.load_loinc_terms(path)
