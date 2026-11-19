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

"""The links between an implantation plan's components under Clean Structured Content.

An Implantation Plan SR Document can select several implant components and
connect them in assemblies. PS3.16 2026d TID 7000 row 9 gives each Selected
Implant Component a Component ID, and row 17 names each Connected
Implantation Plan Component of a Component Connection by an identifier
"Defined in the Implant Component List CONTAINER". These tests show that
each Component ID, at either place, takes the dummy value of its
component's rank, so that each connection joins the same components in a
written plan, and that a plan whose connections cannot be kept is
sequestered (D-022). The plan is synthetic, built by
:func:`._synthetic_procedure_reports.implantation_plan_of_components`.
"""

import io

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import run
from pymedphys._dicom.deidentify.file_layout import ElementPath

from . import _synthetic_procedure_reports as reports
from . import _synthetic_structured_reports as general

# The procedure report module's fixture, which adds the option to a preset.
from .test_deidentify_procedure_report_content import (  # noqa: F401  # pylint: disable = unused-import
    _with_option,
)
from .test_deidentify_procedure_report_content import (
    CONTENT,
    PRESETS,
    _items,
    _planned,
    _released,
)

pytestmark = [pytest.mark.pydicom, pytest.mark.usefixtures("pydicom_behaviour")]

STEM = f"{general.SENTINEL} STEM"
HEAD = f"{general.SENTINEL} HEAD"
CUP = f"{general.SENTINEL} CUP"
# Three components, and two connections that name them in an order other
# than the list's, so that no position matches an end to its component.
THREE_COMPONENTS = (
    (STEM, reports.FEMORAL_STEM),
    (HEAD, reports.FEMORAL_HEAD_BALL),
    (CUP, reports.ACETABULAR_CUP_SHELL),
)
TWO_CONNECTIONS = ((CUP, STEM), (STEM, HEAD))


def _plan(components=THREE_COMPONENTS, connections=TWO_CONNECTIONS):
    return reports.implantation_plan_of_components(components, connections)


def _meaning(each):
    names = each.get("ConceptNameCodeSequence")
    return names[0].CodeMeaning if names else None


def _child(each, concept):
    (found,) = [
        child for child in each.ContentSequence if _meaning(child) == concept.meaning
    ]
    return found


def _components(dataset):
    """Return each component's identifier and type, and each connection's ends.

    Each is in the order of the tree, and each end is the identifier that
    its Connected Implantation Plan Component writes.
    """
    found = {"components": [], "connections": []}
    for each in _items(dataset):
        meaning = _meaning(each)
        if meaning == reports.SELECTED_IMPLANT_COMPONENT.meaning:
            identifier = _child(each, reports.COMPONENT_ID).TextValue
            kind = _child(each, reports.COMPONENT_TYPE).ConceptCodeSequence[0]
            found["components"].append((identifier, kind.CodeMeaning))
        elif meaning == reports.COMPONENT_CONNECTION.meaning:
            found["connections"].append(
                tuple(
                    _child(end, reports.COMPONENT_ID).TextValue
                    for end in each.ContentSequence
                )
            )
    return found


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
@pytest.mark.parametrize("preset", PRESETS)
def test_each_connection_still_joins_its_own_components(with_option, preset):
    # TID 7000 row 17 names each end of a connection by its component's
    # Component ID, so the table's one dummy value for every Component ID
    # would leave each connection joining any two components.
    data, decision = _released(with_option(preset), _plan())

    written = _components(pydicom.dcmread(io.BytesIO(data)))
    assert written["components"] == [
        ("DEIDENTIFIED 1", "Femoral Stem"),
        ("DEIDENTIFIED 2", "Femoral Head Ball Component"),
        ("DEIDENTIFIED 3", "Acetabular Cup Shell"),
    ]
    kinds = dict(written["components"])
    assert [tuple(kinds[end] for end in pair) for pair in written["connections"]] == [
        ("Acetabular Cup Shell", "Femoral Stem"),
        ("Femoral Stem", "Femoral Head Ball Component"),
    ]
    assert isinstance(decision, run.Release), decision


@pytest.mark.parametrize(
    "components, connections",
    [
        # Two components with one identifier, which row 17 cannot tell apart.
        (
            (*THREE_COMPONENTS[:2], (STEM, reports.ACETABULAR_CUP_SHELL)),
            TWO_CONNECTIONS[1:],
        ),
        # An end that names no component, which row 17 forbids.
        (THREE_COMPONENTS, (*TWO_CONNECTIONS, (CUP, f"{general.SENTINEL} LINER"))),
    ],
)
def test_a_connection_whose_components_are_ambiguous_sequesters_the_plan(
    with_option, components, connections
):
    composed = with_option("public-release")

    actions, plan = _planned(
        _plan(components, connections), reports.IMPLANTATION_PLAN_IOD, composed
    )

    assert ElementPath((), CONTENT) not in actions
    assert {s.path for s in plan.sequestrations} == {ElementPath((), CONTENT)}


def test_a_components_dummy_value_is_never_a_source_identifier(with_option):
    # As D's second constant does, the series moves on by its length where a
    # dummy value would equal a source Component ID, as D compares them: so
    # a second run over a written plan writes new values, not its own.
    components = (("Deidentified 1", reports.FEMORAL_STEM), *THREE_COMPONENTS[1:])
    connections = (("Deidentified 1", HEAD),)

    actions, _ = _planned(
        _plan(components, connections),
        reports.IMPLANTATION_PLAN_IOD,
        with_option("public-release"),
    )

    assert sorted(set(actions.dummy_texts.values())) == [
        "DEIDENTIFIED 4",
        "DEIDENTIFIED 5",
        "DEIDENTIFIED 6",
    ]
    assert len(actions.dummy_texts) == 5
    assert all(actions[path] == "D" for path in actions.dummy_texts)


def test_a_component_id_elsewhere_keeps_the_tables_constant(with_option):
    # Only a Selected Implant Component's Component ID identifies a
    # component, and only a Connected Implantation Plan Component's names
    # one; the mating features' identifiers name features of an implant
    # template that the plan does not hold, and keep D's constant.
    actions, _ = _planned(
        _plan(), reports.IMPLANTATION_PLAN_IOD, with_option("public-release")
    )
    texts = [path for path in actions if path.tag == "(0040,A160)"]

    # Three components, two ends of each of two connections, and a mating
    # feature set and feature at each end.
    assert len(texts) == 3 + 2 * 2 + 2 * 2 * 2
    assert all(actions[path] == "D" for path in texts)
    assert len([path for path in texts if path in actions.dummy_texts]) == 3 + 2 * 2
