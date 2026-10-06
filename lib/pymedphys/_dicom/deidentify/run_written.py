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

"""The reference graph's second pass in a run, which fails closed.

:mod:`~pymedphys._dicom.deidentify.run` calls :func:`second_pass` once its
gate has decided every staged file, with each file that the gate released,
as read back from the staging area one at a time. Each file is recorded as
the first pass recorded its input before the next is read, so only one
file's bytes are held at once, and the run's
:class:`~pymedphys._dicom.deidentify.run_results.WrittenCheck` compares the
records with the first pass's graph.

A finding of what was written, other than a reference to an input that was
not written, is a fault of the engine, so the instances that it names are
withheld and the rest are checked again, until no such finding remains. A
reference to an input that was withheld names nothing that was written, as
the first pass's dangling reference names nothing that was given, and is
reported only. Of the findings at fault, those that name a written
reference that resolves to nothing written are acted on only where no other
finding at fault remains, since an instance whose reference names one that
was itself written wrongly is sound once that one is withheld. A check that
raises, or a finding at fault that names no instance still released,
withholds the whole release (:class:`ReleaseWithheld`).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable

from .reasons import RunReason
from .reference_graph import ReferenceGraph
from .references import InstanceRecord
from .run_results import WrittenCheck
from .written_references import WrittenFinding, WrittenFindingKind

# The findings that are reported only.
_REPORTED_ONLY = frozenset({WrittenFindingKind.UNWRITTEN_TARGET})


class ReleaseWithheld(Exception):
    """A run whose second reference pass found a fault it could not isolate.

    Nothing is published, and no QC pack is written. Its message gives only
    the number of findings.

    Attributes
    ----------
    findings : tuple of WrittenFinding
        The second pass's findings that withheld the release, by run
        position; empty if the check itself failed.
    """

    def __init__(self, findings: tuple[WrittenFinding, ...] = ()) -> None:
        super().__init__(findings)
        self.findings = findings

    def __str__(self) -> str:
        if not self.findings:
            return "the second reference pass failed, so nothing was published"
        return (
            "the second reference pass found faults in what was written that "
            f"no instance could be withheld for ({len(self.findings)} "
            f"finding{'' if len(self.findings) == 1 else 's'}), so nothing was "
            "published"
        )


def second_pass(
    graph: ReferenceGraph,
    positions: tuple[int, ...],
    written: Iterable[tuple[int, bytes]],
    written_check: WrittenCheck,
) -> tuple[tuple[WrittenFinding, ...], dict[int, RunReason]]:
    """Check what was written against the first pass, and fail closed.

    Parameters
    ----------
    graph : ReferenceGraph
        The first pass's graph.
    positions : tuple of int
        The run position of each of the graph's positions.
    written : iterable of (int, bytes)
        The run position of each released file's input, with the file as
        read back. Each file is recorded before the next is taken, so it
        can be read as it is taken.
    written_check : WrittenCheck
        The run's second pass.

    Returns
    -------
    findings : tuple of WrittenFinding
        By run position, once each: those that withheld the instances they
        name, check by check, then those of the last check, which are
        reported only.
    withheld : dict of int to RunReason
        The :attr:`~.reasons.RunReason.INCONSISTENT_REFERENCES` of each run
        position whose file cannot be recorded, or that a finding withheld.

    Raises
    ------
    ReleaseWithheld
        If the check raises, or a finding at fault names no instance that
        is still released.
    """
    index = {position: at for at, position in enumerate(positions)}
    withheld: dict[int, RunReason] = {}
    records: dict[int, InstanceRecord] = {}
    for position, data in written:
        try:
            records[index[position]] = InstanceRecord.from_file(data)
        # What was written cannot be shown to refer as its input did, and
        # pydicom's message could quote a value, so none is kept.
        except Exception:  # pylint: disable = broad-exception-caught
            withheld[position] = RunReason.INCONSISTENT_REFERENCES

    found: dict[WrittenFinding, None] = {}
    while True:
        try:
            findings = tuple(
                _by_run_position(finding, positions)
                for finding in written_check(graph, dict(records))
            )
        # The check is the run's own, but its message could still quote a
        # value, so none is kept, and nothing is published.
        except Exception:  # pylint: disable = broad-exception-caught
            raise ReleaseWithheld() from None
        faults = [finding for finding in findings if finding.kind not in _REPORTED_ONLY]
        if not faults:
            found.update(dict.fromkeys(findings))
            return tuple(found), withheld
        acted = [
            finding
            for finding in faults
            if finding.kind is not WrittenFindingKind.UNRESOLVED_REFERENCE
        ] or faults
        named = {
            position
            for finding in acted
            for group in finding.instances
            for position in group
            if index.get(position) in records
        }
        if not named:
            raise ReleaseWithheld(tuple(faults))
        found.update(dict.fromkeys(acted))
        for position in named:
            del records[index[position]]
            withheld[position] = RunReason.INCONSISTENT_REFERENCES


def _by_run_position(
    finding: WrittenFinding, positions: tuple[int, ...]
) -> WrittenFinding:
    """Return a finding of the graph's positions by the run's positions."""
    return dataclasses.replace(
        finding,
        instances=tuple(
            tuple(positions[at] for at in group) for group in finding.instances
        ),
    )
