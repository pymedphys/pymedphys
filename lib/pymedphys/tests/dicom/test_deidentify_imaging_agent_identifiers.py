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

"""The links between imaging agents and their activities under Clean Structured Content.

A Planned or Performed Imaging Agent Administration SR can give several
agents. PS3.16 2026d TID 11002 row 2 identifies each "uniquely, within the
scope of the root container", and TID 11003 row 2 names the agent of each
activity of an automated administration's phase by that identifier. These
tests show that each identifier, and each reference to it, takes the dummy
value of its agent's rank, so that each activity names the same agent in a
written report, and that a report whose links cannot be kept is
sequestered (D-022). The report is synthetic, built by
:func:`._synthetic_procedure_reports.planned_administration_of_agents`.
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
    _by_meaning,
    _items,
    _planned,
    _released,
)

pytestmark = [pytest.mark.pydicom, pytest.mark.usefixtures("pydicom_behaviour")]

AGENT_A = f"{general.SENTINEL} SYRINGE A"
AGENT_B = f"{general.SENTINEL} SYRINGE B"
# Two agents, and the activities of the one phase that gives them, in the
# other order, so that no position matches an activity to its agent.
TWO_AGENTS = ((AGENT_A, reports.IOHEXOL), (AGENT_B, reports.IOPAMIDOL))
TWO_ACTIVITIES = ((AGENT_B, "27"), (AGENT_A, "11"))


def _agents_report(agents=TWO_AGENTS, activities=TWO_ACTIVITIES):
    return reports.planned_administration_of_agents(agents, activities)


def _agent_identifiers(dataset):
    """Return each agent's identifier and drug, and each activity's reference and volume.

    Each is in the order of the tree.
    """
    found = {"agents": [], "activities": []}
    for each in _items(dataset):
        names = each.get("ConceptNameCodeSequence")
        meaning = names[0].CodeMeaning if names else None
        if meaning == reports.IMAGING_AGENT_INFORMATION.meaning:
            drug = _by_meaning(
                _by_meaning(
                    _by_meaning(each, reports.COMPONENT_USAGE.meaning),
                    reports.IMAGING_AGENT_COMPONENT.meaning,
                ),
                reports.DRUG_ADMINISTERED.meaning,
            )
            identifier = _by_meaning(each, reports.IMAGING_AGENT_IDENTIFIER.meaning)
            found["agents"].append(
                (identifier.TextValue, drug.ConceptCodeSequence[0].CodeMeaning)
            )
        elif meaning == reports.ADMINISTRATION_ACTIVITY.meaning:
            reference = _by_meaning(each, reports.REFERENCED_AGENT.meaning)
            volume = _by_meaning(each, reports.VOLUME_ADMINISTERED.meaning)
            found["activities"].append(
                (reference.TextValue, volume.MeasuredValueSequence[0].NumericValue)
            )
    return found


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
@pytest.mark.parametrize("preset", PRESETS)
def test_each_activity_still_names_its_own_agent(with_option, preset):
    # TID 11002 row 2 identifies each agent uniquely within the tree, and
    # TID 11003 row 2 names an activity's agent by that identifier, so one
    # dummy value for every identifier would leave each activity naming
    # both agents.
    data, decision = _released(with_option(preset), _agents_report())

    written = _agent_identifiers(pydicom.dcmread(io.BytesIO(data)))
    assert written["agents"] == [
        ("DEIDENTIFIED 1", "Iohexol"),
        ("DEIDENTIFIED 2", "Iopamidol"),
    ]
    drugs = dict(written["agents"])
    assert [(drugs[name], volume) for name, volume in written["activities"]] == [
        ("Iopamidol", "27"),
        ("Iohexol", "11"),
    ]
    assert isinstance(decision, run.Release), decision


@pytest.mark.parametrize(
    "agents, activities",
    [
        # Two agents with one identifier, which TID 11002 row 2 forbids.
        ((TWO_AGENTS[0], (AGENT_A, reports.IOPAMIDOL)), TWO_ACTIVITIES[1:]),
        # A reference to no agent, which TID 11003 row 2 forbids.
        (TWO_AGENTS, (*TWO_ACTIVITIES, (f"{general.SENTINEL} SYRINGE C", "5"))),
    ],
)
def test_an_activity_whose_agent_is_ambiguous_sequesters_the_report(
    with_option, agents, activities
):
    composed = with_option("public-release")
    dataset = _agents_report(agents, activities)

    actions, plan = _planned(dataset, reports.PLANNED_ADMINISTRATION_IOD, composed)

    assert ElementPath((), CONTENT) not in actions
    assert {s.path for s in plan.sequestrations} == {ElementPath((), CONTENT)}


def test_an_agents_dummy_value_is_never_a_source_identifier(with_option):
    # As D's second constant does, the series moves on by its length where a
    # dummy value would equal a source identifier, as D compares them: so a
    # second run over a written report writes new values, not its own.
    agents = (("Deidentified 2", reports.IOHEXOL), (AGENT_B, reports.IOPAMIDOL))
    activities = (("Deidentified 2", "11"), (AGENT_B, "27"))
    dataset = _agents_report(agents, activities)

    actions, _ = _planned(
        dataset, reports.PLANNED_ADMINISTRATION_IOD, with_option("public-release")
    )

    assert sorted(set(actions.dummy_texts.values())) == [
        "DEIDENTIFIED 3",
        "DEIDENTIFIED 4",
    ]
    assert all(actions[path] == "D" for path in actions.dummy_texts)
