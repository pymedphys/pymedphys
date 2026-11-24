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

"""Write the paragraphs on the dummy values that Clean Structured Content writes.

:func:`paragraphs` gives
:func:`~pymedphys._dicom.deidentify.conformance_values.values_written` the
paragraphs on the values that D writes in a content tree in place of its
constant, from :mod:`~pymedphys._dicom.deidentify.content_items`: the ranked
datetimes of a Procedure Log's entries, and the ranked dummy values of the
linked identifiers of imaging agents and implant components. Each names
tags, concepts, and the engine's constants, never a value from an instance
or a key.
"""

from __future__ import annotations

from collections.abc import Callable

from . import dummy_values
from .conformance import ConformanceStatement
from .content_items import LINK_DUMMY, OBSERVATION_DATETIME, TEXT_VALUE
from .policy import CLEAN_STRUCTURED_CONTENT, FULL_DATES, MODIFIED_DATES


def paragraphs(
    statement: ConformanceStatement, named: Callable[[str], str]
) -> tuple[str, ...]:
    """Return the lines on the dummy values that D writes in a content tree.

    Each paragraph is preceded by an empty line, so that the lines extend
    those of
    :func:`~pymedphys._dicom.deidentify.conformance_values.values_written`.
    """
    if CLEAN_STRUCTURED_CONTENT not in statement.options:
        return ()
    lines: tuple[str, ...] = ()
    if _writes_log_datetimes(statement):
        lines += ("", _log_datetimes(named))
    return lines + ("", _linked_identifiers(named))


def _writes_log_datetimes(statement: ConformanceStatement) -> bool:
    """Return whether D writes the ranked datetimes of a Procedure Log's entries."""
    return CLEAN_STRUCTURED_CONTENT in statement.options and not {
        FULL_DATES,
        MODIFIED_DATES,
    }.intersection(statement.options)


def _log_datetimes(named: Callable[[str], str]) -> str:
    """Return the paragraph on the datetimes that D writes in a Procedure Log."""
    first = dummy_values.CONSTANTS["DT"][0]
    return (
        f"D on {named(OBSERVATION_DATETIME)} of each entry of a Procedure "
        "Log, an item of its Content Sequence that is a target of CONTAINS, "
        "writes in place of "
        "the constant the dummy datetime of its rank among the entries' "
        f"distinct source values: `{first}` for the earliest, and one second "
        "more for each later one, so entries with equal source values share "
        "one and the log keeps the increasing order that PS3.3 Section "
        "A.35.7.3.1.2 requires. Where any of these would equal an entry's "
        "source value, as D compares them, the series moves on by its own "
        "length until none does. A log whose entries are not in increasing "
        "order is sequestered."
    )


def _linked_identifiers(named: Callable[[str], str]) -> str:
    """Return the paragraph on the dummy values of linked identifiers."""
    return (
        f"D on {named(TEXT_VALUE)} of an Imaging Agent Identifier "
        "(130254, DCM), which PS3.16 TID 11002 requires to identify its agent "
        "uniquely in the report, writes in place of the constant the dummy "
        "value of the agent's rank among the report's agents, in the order of "
        f"its content tree: `{LINK_DUMMY.format(1)}` for the first, "
        f"`{LINK_DUMMY.format(2)}` for the second, and so on. D on that of a "
        "Referenced Imaging Agent Identifier (130255, DCM), by which "
        "TID 11003 names the agent of an administration activity, writes its "
        "agent's, so that each activity names the same agent in the output. "
        "The Component ID (112347, DCM) of each Selected Implant Component "
        "(112346, DCM), which PS3.16 TID 7000 lists in an implantation plan, "
        "takes in the same way the dummy value of its component's rank among "
        "the plan's components, and that of a Connected Implantation Plan "
        "Component (112374, DCM), by which TID 7000 names a component that an "
        "assembly connects, its component's, so that each connection names "
        "the same components in the output. Where any agent's or component's "
        "value would equal a source identifier of its kind, as D compares "
        "them, that series moves on by its own length until none does. A "
        "report in which two agents or two components share an identifier, "
        "or a reference names no agent or component that is kept, is "
        "sequestered."
    )
