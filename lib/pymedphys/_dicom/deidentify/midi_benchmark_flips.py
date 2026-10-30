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

"""Compare two MIDI benchmark runs check by check: the flip check (D-018).

A Retain option of PS3.15 Table E.1-1 keeps the attributes of its rows and
changes nothing else. Its flip check runs the benchmark under ``basic`` and
under the option alone over the same test data set, and compares the
outcome of each answer-key check between the two runs. A check counts as
**governed** by the option where an element of its place, the attribute or
a sequence that holds it, takes its rule from a row of Table E.1-1 that
gives the option an action, or from a supplementary rule that does
(:mod:`~pymedphys._dicom.deidentify.supplementary_actions`), or is one of
the markers that record the options (:data:`MARKERS`). The check:

- compares outcomes only over the instances that both runs released, and
  counts the checks of instances that only one run released apart, as
  release changes, since a check that one run did not score has no outcome
  to compare;
- **fails** where a check that the option does not govern changed outcome,
  which the option should not have caused;
- finds **no effect** where the option governs checks that both runs scored
  but none of them changed, which suggests the option was not applied;
- passes otherwise, or finds the option **not exercised** where the answer
  key checks none of its rows in instances both runs released, which is no
  evidence either way.

Not every governed check need change. A check can score the same under both
actions: a date that the Basic Profile empties and Modified Dates shifts
passes ``date_shifted`` either way, and its ``text_retained`` check fails
either way, as a deliberate difference. So the governed checks that change
are counted, by category, action, attribute, and outcome, rather than
required to change; Modified Dates' are mostly TCIA's MOD-C and HIPAA-C
date checks.

Each run writes the outcome of every check of the answer key, in the key's
order, to ``check-outcomes.txt`` (:func:`write_check_outcomes`): one letter
for each, after a line of JSON that names the answer key's SHA-256 and the
run's policy. It holds no identifier, attribute, or value; the comparison
reads the answer key again for each check's place and category. The
results hold only counts, the option, answer-key category codes and action
names, and attribute tags.
"""

from __future__ import annotations

import collections
import dataclasses
import json
from collections.abc import Mapping
from pathlib import Path

from .element_rules import ElementRule, ElementRules, RuleSource
from .midi_answer_key import AnswerKey, AttributePath, Element
from .policy import (
    DEVICE_IDENTITY,
    FULL_DATES,
    INSTITUTION_IDENTITY,
    MODIFIED_DATES,
    PATIENT_CHARACTERISTICS,
    SAFE_PRIVATE,
    UIDS,
    Policy,
    compose_policy,
)
from .standard import load_table_e1_1
from .supplementary_actions import load_supplementary_actions

FORMAT = "pymedphys-deid-midi-flip-check/1"
OUTCOMES_FORMAT = "pymedphys-deid-midi-check-outcomes/1"
CHECK_OUTCOMES = "check-outcomes.txt"

# The Retain options of Table E.1-1, in its order: the options that a flip
# check compares with basic.
RETAIN_OPTIONS = (
    SAFE_PRIVATE,
    UIDS,
    DEVICE_IDENTITY,
    INSTITUTION_IDENTITY,
    PATIENT_CHARACTERISTICS,
    FULL_DATES,
    MODIFIED_DATES,
)

# The markers that record the options (PS3.15 E.3): Patient Identity
# Removed, De-identification Method and its Code Sequence, and Longitudinal
# Temporal Information Modified, whose values change with the options
# selected.
MARKERS = frozenset({"(0012,0062)", "(0012,0063)", "(0012,0064)", "(0028,0303)"})

# A letter for each outcome of a check, by the name of the benchmark's count
# that it adds to; the first five are of released instances.
_CODES: Mapping[str, str] = {
    "passed": "P",
    "failed": "F",
    "deliberate": "D",
    "source_gap": "G",
    "not_evaluated": "N",
    "withheld": "W",
    "outside_coverage": "O",
    "not_in_input": "I",
}
_NAMES = {code: name for name, code in _CODES.items()}
_RELEASED = frozenset("PFDGN")

PASSED = "passed"
FAILED = "failed"
NO_EFFECT = "no effect"
NOT_EXERCISED = "not exercised"


class FlipCheckError(Exception):
    """Runs that cannot be compared. The message quotes no value or path."""


def outcome_code(outcome: str) -> bytes:
    """Return the letter of a check's outcome, by the benchmark count it adds to.

    Parameters
    ----------
    outcome : str
        The name of a field of the benchmark's counts, such as ``"passed"``,
        ``"deliberate"``, or ``"withheld"``.
    """
    return _CODES[outcome].encode("ascii")


@dataclasses.dataclass(frozen=True)
class CheckOutcomes:
    """The outcome of each check of an answer key in one run.

    Attributes
    ----------
    answer_key_sha256 : str
    preset : str or None
        The run's preset, or ``None`` for a custom option set.
    options : tuple of str
        The run's options.
    codes : bytes
        One letter for each check, in the answer key's order.
    """

    answer_key_sha256: str
    preset: str | None
    options: tuple[str, ...]
    codes: bytes


def write_check_outcomes(
    path: str | Path, answer_key_sha256: str, policy: Policy, codes: bytes
) -> None:
    """Write a run's check outcomes, for :func:`flip_check`."""
    header = {
        "format": OUTCOMES_FORMAT,
        "answer_key_sha256": answer_key_sha256,
        "preset": policy.preset,
        "options": list(policy.options),
        "checks": len(codes),
    }
    Path(path).write_bytes(json.dumps(header).encode("ascii") + b"\n" + codes)


def read_check_outcomes(path: str | Path) -> CheckOutcomes:
    """Read the check outcomes that :func:`write_check_outcomes` wrote.

    Raises
    ------
    FlipCheckError
        If the file cannot be read, or is not a run's check outcomes.
    """
    try:
        first, _, codes = Path(path).read_bytes().partition(b"\n")
        header = json.loads(first)
    except (OSError, ValueError):
        raise FlipCheckError("a run's check outcomes could not be read") from None
    if not isinstance(header, dict) or header.get("format") != OUTCOMES_FORMAT:
        raise FlipCheckError("a file is not a run's check outcomes")
    if (
        header.get("checks") != len(codes)
        or not set(codes.decode("latin-1")) <= set(_NAMES)
        or not isinstance(header.get("answer_key_sha256"), str)
        or not isinstance(header.get("options"), list)
    ):
        raise FlipCheckError("a file is not a run's check outcomes")
    return CheckOutcomes(
        header["answer_key_sha256"],
        header.get("preset"),
        tuple(header["options"]),
        codes,
    )


def governed_entries(option: str) -> frozenset[str]:
    """Return the rules that give ``option`` an action, by their entries.

    That is the tag of each row of Table E.1-1 that gives the option an
    action, such as ``"(0008,0080)"`` or the Private Attributes row, and of
    each supplementary rule that does, as
    :attr:`~pymedphys._dicom.deidentify.element_rules.ElementRule.entry`
    names them.
    """
    rows = {row.tag for row in load_table_e1_1().attributes if option in row.options}
    rules = load_supplementary_actions().rules
    return frozenset(
        rows | {tag for tag, rule in rules.items() if option in rule.options}
    )


def _rule_tag(element: Element) -> str:
    """Return the tag that an element takes its rule by, as the benchmark does."""
    if element.is_private:
        # Any element of a private block takes the Private Attributes row.
        return f"({element.group:04X},10{element.element:02X})"
    return str(element)


_GOVERNING_SOURCES = frozenset(
    {RuleSource.TABLE, RuleSource.PRIVATE, RuleSource.SUPPLEMENTARY}
)


class _Governance:
    """Whether the option governs a check's place, cached by place."""

    def __init__(self, option: str) -> None:
        self._entries = governed_entries(option)
        self._rules = ElementRules(compose_policy("basic"))
        self._cache: dict[str, bool] = {}

    def governs(self, path: AttributePath | None) -> bool:
        if path is None:
            return False
        place = str(path)
        if place not in self._cache:
            self._cache[place] = self._governs(path)
        return self._cache[place]

    def _governs(self, path: AttributePath) -> bool:
        if str(path.elements[0]) in MARKERS:
            return True
        tags = [_rule_tag(element) for element in path.elements]
        for depth, tag in enumerate(tags):
            try:
                rule: ElementRule = self._rules.rule(tag, tags[:depth])
            except ValueError:
                continue
            if rule.source in _GOVERNING_SOURCES and rule.entry in self._entries:
                return True
        return False


def flip_check(
    key: AnswerKey,
    reference: CheckOutcomes,
    compared: CheckOutcomes,
    option: str,
) -> dict[str, object]:
    """Compare a run under ``basic`` with one under a Retain option alone.

    Parameters
    ----------
    key : AnswerKey
        The answer key that both runs were scored against.
    reference : CheckOutcomes
        The run under ``basic``.
    compared : CheckOutcomes
        The run under the custom option set of ``option`` alone.
    option : str
        One of :data:`RETAIN_OPTIONS`.

    Returns
    -------
    dict
        The results, without a value from the test data set: the verdict,
        :data:`PASSED`, :data:`FAILED`, :data:`NO_EFFECT`, or
        :data:`NOT_EXERCISED`, the counts of checks and instances, and the
        checks that changed outcome by whether the option governs them,
        category, action, attribute, and outcome in each run.

    Raises
    ------
    FlipCheckError
        If the option is not a Retain option; the runs were not under
        ``basic`` and under the option alone; or either run's outcomes are
        not of this answer key.
    """
    if option not in RETAIN_OPTIONS:
        raise FlipCheckError(
            "a flip check compares basic with one of the Retain options: "
            + ", ".join(RETAIN_OPTIONS)
        )
    if reference.preset != "basic" or reference.options:
        raise FlipCheckError("the reference run must be under the basic preset")
    if compared.preset is not None or compared.options != (option,):
        raise FlipCheckError(
            "the compared run must be under a custom option set of the option alone"
        )
    total = sum(len(answer.checks) for answer in key.by_sop_instance().values())
    for run in (reference, compared):
        if run.answer_key_sha256 != key.sha256 or len(run.codes) != total:
            raise FlipCheckError("a run's check outcomes are not of this answer key")

    governance = _Governance(option)
    checks: collections.Counter = collections.Counter()
    instances: collections.Counter = collections.Counter()
    changes: collections.Counter = collections.Counter()
    position = 0
    for answer in key.by_sop_instance().values():  # one per instance
        count = len(answer.checks)
        before = reference.codes[position : position + count].decode("ascii")
        after = compared.codes[position : position + count].decode("ascii")
        position += count
        if not count:
            continue
        # Every check of an instance shares its context, so its first tells.
        released = (before[0] in _RELEASED, after[0] in _RELEASED)
        if released != (True, True):
            where = {
                (True, False): "released_in_reference_only",
                (False, True): "released_with_option_only",
                (False, False): "released_in_neither",
            }[released]
            instances[where] += 1
            checks[where] += count
            continue
        instances["released_in_both"] += 1
        for check, was, now in zip(answer.checks, before, after):
            governed = governance.governs(check.path)
            checks["compared"] += 1
            checks["governed"] += governed
            if was == now:
                continue
            checks["governed_changed" if governed else "ungoverned_changed"] += 1
            changes[
                (
                    governed,
                    str(check.category or "unknown"),
                    check.action_name,
                    None if check.path is None else str(check.path),
                    _NAMES[was],
                    _NAMES[now],
                )
            ] += 1
    if checks["ungoverned_changed"]:
        verdict = FAILED
    elif not checks["governed"]:
        verdict = NOT_EXERCISED
    elif not checks["governed_changed"]:
        verdict = NO_EFFECT
    else:
        verdict = PASSED
    check_fields = (
        "compared",
        "governed",
        "governed_changed",
        "ungoverned_changed",
        "released_in_reference_only",
        "released_with_option_only",
        "released_in_neither",
    )
    instance_fields = (
        "released_in_both",
        "released_in_reference_only",
        "released_with_option_only",
        "released_in_neither",
    )
    return {
        "format": FORMAT,
        "option": option,
        "answer_key_sha256": key.sha256,
        "verdict": verdict,
        "checks": {name: checks[name] for name in check_fields},
        "instances": {name: instances[name] for name in instance_fields},
        "changes": [
            {
                "governed": governed,
                "category": category,
                "action": action,
                "attribute": attribute,
                "reference": was,
                "option": now,
                "checks": number,
            }
            for (governed, category, action, attribute, was, now), number in sorted(
                changes.items(), key=_change_order
            )
        ],
    }


def _change_order(item: tuple[tuple, int]) -> tuple:
    (governed, category, action, attribute, was, now), number = item
    # Ungoverned changes first, then the most checks.
    return (governed, -number, category, action, attribute or "", was, now)


def passed(document: Mapping[str, object]) -> bool:
    """Whether a flip check's verdict lets the option through.

    A check that found the option not exercised passes, since it found
    nothing wrong, though it gives no evidence.
    """
    return document["verdict"] in (PASSED, NOT_EXERCISED)


def render_markdown(document: Mapping[str, object]) -> str:
    """Render a flip check's results as CommonMark."""
    checks = document["checks"]
    instances = document["instances"]
    changes = document["changes"]
    assert isinstance(checks, Mapping) and isinstance(instances, Mapping)
    assert isinstance(changes, list)
    lines = [
        f"# Flip check: {document['option']}",
        "",
        f"Verdict: **{document['verdict']}**. The checks of instances that "
        "both runs released are compared; a change in a check that the "
        "option does not govern fails the check.",
        "",
        "| Checks | Count |",
        "| --- | ---: |",
        *(f"| {name.replace('_', ' ')} | {value} |" for name, value in checks.items()),
        "",
        "| Instances | Count |",
        "| --- | ---: |",
        *(
            f"| {name.replace('_', ' ')} | {value} |"
            for name, value in instances.items()
        ),
        "",
        "## Changes",
        "",
    ]
    if not changes:
        lines += ["No check of an instance that both runs released changed.", ""]
        return "\n".join(lines)
    lines += [
        "| Governed | Category | Action | Attribute | Under basic | Under the option | Checks |",
        "| --- | --- | --- | --- | --- | --- | ---: |",
    ]
    for change in changes:
        assert isinstance(change, Mapping)
        cells = [
            "yes" if change["governed"] else "no",
            str(change["category"]),
            str(change["action"]),
            "none" if change["attribute"] is None else str(change["attribute"]),
            str(change["reference"]).replace("_", " "),
            str(change["option"]).replace("_", " "),
            str(change["checks"]),
        ]
        lines.append("| " + " | ".join(c.replace("|", "\\|") for c in cells) + " |")
    lines.append("")
    return "\n".join(lines)
