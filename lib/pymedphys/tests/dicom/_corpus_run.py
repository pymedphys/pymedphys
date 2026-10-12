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

"""A policy run over the synthetic corpus, and what the run must do.

The end-to-end tests (``test_deidentify_corpus_end_to_end.py``) and the
independent validators' tests (``test_deidentify_dicom_validation_corpus.py``)
each run the engine over the synthetic corpus once for each
:class:`CorpusRun` in :data:`~pymedphys.tests.dicom.corpus_runs.CORPUS_RUNS`,
in a module-scoped fixture. A run is a policy, either a preset or a custom
option set, with its inputs and what it must do: which instances it
withholds and why, which planted markers it keeps, which CID 7050 codes its
released instances claim, and the names its released structure set gives
its ROIs.

Each run is a module of its own in :mod:`pymedphys.tests.dicom.corpus_runs`,
and each option joins as one new module once the engine applies it, so that
a pull request adds one corpus run to each test module, no fixture, and no
line that another option's pull request also changes. What follows from the standard is derived here from PS3.15, not
from the engine's composition of the policy: the markers kept are those in
the rows of Table E.1-1 that the selected options keep (action K), the codes
are CID 7050's, and Longitudinal Temporal Information Modified follows
E.2 and E.3.6. An entry overrides an expectation only where the standard
leaves its value to the engine, such as a cleaner's output, and says why.
"""

import contextlib
import dataclasses
import functools
import types
from collections.abc import Callable, Iterator, Mapping
from typing import Any

from pymedphys._imports import pydicom, pytest

from pymedphys._nomenclature import tg263

from pymedphys._dicom.deidentify import pixel_decoding, roi_names, run, standard
from pymedphys._dicom.deidentify import synthetic_corpus as corpus_module
from pymedphys._dicom.deidentify.descriptor_cleaning import DescriptorCleaning
from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.instance_transform import InstanceTransform
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.policy import (
    PRESETS,
    Policy,
    compose_custom_policy,
    compose_policy,
)
from pymedphys._dicom.deidentify.release_gate import (
    Decision,
    ReasonCode,
    ReleaseReason,
)
from pymedphys._dicom.deidentify.reviewed_roi_names import (
    Review,
    ReviewedName,
    ReviewedNames,
)
from pymedphys._dicom.deidentify.walker import SequesterReason, Sequestration

from . import _synthetic_compressed as compressed

KEY = DeidKey(bytes(range(32)))

# The CID 7050 code of the Basic Application Level Confidentiality Profile
# and of each option of Table E.1-1 (PS3.16 CID 7050), written out here
# rather than read from the engine, and their Coding Scheme Designator.
DCM = "DCM"
BASIC_PROFILE_CODE = "113100"
OPTION_CODES: Mapping[str, str] = types.MappingProxyType(
    {
        "retain_safe_private": "113111",
        "retain_uids": "113110",
        "retain_device_identity": "113109",
        "retain_institution_identity": "113112",
        "retain_patient_characteristics": "113108",
        "retain_longitudinal_full_dates": "113106",
        "retain_longitudinal_modified_dates": "113107",
        "clean_descriptors": "113105",
        "clean_structured_content": "113104",
        "clean_graphics": "113103",
    }
)
FULL_DATES = "retain_longitudinal_full_dates"
MODIFIED_DATES = "retain_longitudinal_modified_dates"

# The generic parts of every marker.
MARKER_SIGNATURES = (
    corpus_module.MARKER_PREFIX,
    corpus_module.MARKER_UID_ROOT,
    corpus_module.LINKED_UID_ROOT,
    ".424242",
    "MARKER",
    "synmk.invalid",
)

CLEAN_DESCRIPTORS = "basic-clean-descriptors"
# The basic preset over the corpus with its images compressed, and text
# planted in their codestreams' metadata segments.
COMPRESSED = "basic-compressed"
ROI_SEQUENCE = "(3006,0020)"
ROI_NAME = "(3006,0026)"
# The second ROI's name, which the automatic tier renames, and what it and
# the reviewer write.
UNCLEANED_NAME = "lung l"
VOCABULARY_NAME = "Lung_L"
MAPPED_NAME = "GTV_Primary"
VOCABULARY = tg263.Nomenclature(
    source=tg263.Source(file="invented.xls", sha256="0" * 64, sheet="Invented"),
    attribution=tg263.ATTRIBUTION,
    structures=(
        tg263.Structure(
            target_type="Anatomic",
            major_category="Invented",
            minor_category="",
            anatomic_group="",
            primary_name=VOCABULARY_NAME,
            reverse_order_name="L_Lung",
            description="",
            fma_id=None,
        ),
    ),
)


@contextlib.contextmanager
def published_vocabulary() -> Iterator[None]:
    """Treat the invented vocabulary as a published edition, so nothing is downloaded."""
    entries = [dataclasses.asdict(s) for s in VOCABULARY.structures]
    with pytest.MonkeyPatch.context() as patch:
        patch.setitem(
            roi_names.PUBLISHED_TG263, "TG263 vInvented", tg263.content_sha256(entries)
        )
        yield


def reason_key(reason: object) -> object:
    """Return what a run's reason for withholding an instance is compared by.

    A walker's sequestration by its path and reason, a release gate's reason
    by its decision, code, and path, and any other reason as itself.
    """
    if isinstance(reason, Sequestration):
        return (reason.path, reason.reason)
    if isinstance(reason, ReleaseReason):
        return (reason.decision, reason.code, reason.path)
    return reason


@dataclasses.dataclass(frozen=True)
class Withheld:
    """An instance a run must withhold, and why.

    Attributes
    ----------
    status : run.Status
        :attr:`run.Status.SEQUESTERED` or :attr:`run.Status.HELD_FOR_REVIEW`.
    reasons : frozenset
        Every reason of the instance's outcome, each as :func:`reason_key`
        gives it.
    """

    status: run.Status
    reasons: frozenset


def sequestered(reason: SequesterReason, *tags: str) -> Withheld:
    """Return a walker's sequestration of the top-level attributes ``tags``."""
    return Withheld(
        run.Status.SEQUESTERED,
        frozenset((ElementPath((), tag), reason) for tag in tags),
    )


def held(decision: Decision, code: ReasonCode, *tags: str) -> Withheld:
    """Return the release gate's hold of the top-level attributes ``tags``."""
    return Withheld(
        run.Status.HELD_FOR_REVIEW,
        frozenset((decision, code, ElementPath((), tag)) for tag in tags),
    )


# What every run of the corpus withholds under the Basic Profile: the
# instance whose Responsible Person and Responsible Organization its IOD
# requires (Type 1C), which the profile removes, and the RT Dose that holds
# the plan's RT Plan Label in its Manufacturer's Model Name, which the
# residual search finds.
BASIC_WITHHELD: Mapping[str, Withheld] = types.MappingProxyType(
    {
        corpus_module.SEQUESTERED_FILE: sequestered(
            SequesterReason.REQUIRED_BY_IOD, "(0010,2297)", "(0010,2299)"
        ),
        corpus_module.REVIEW_FILE: held(
            Decision.QC_REVIEW, ReasonCode.RESIDUAL_TEXT, "(300A,0002)"
        ),
    }
)


@functools.cache
def _rows() -> tuple[standard.ProfileAttribute, ...]:
    return standard.load_table_e1_1().attributes


@functools.cache
def _listed() -> frozenset[str]:
    return frozenset(row.tag for row in _rows())


@functools.cache
def kept_rows(options: tuple[str, ...]) -> frozenset[str]:
    """Return the tags of the rows of Table E.1-1 that the options keep.

    A row is kept when every selected option that gives it an action gives
    K. Where options give a row different actions, a custom option set is
    refused, and ``tps-import`` applies Modified Dates' C, so the row is not
    kept.
    """
    kept = set()
    for row in _rows():
        actions = {row.options[o] for o in options if o in row.options}
        if actions == {"K"}:
            kept.add(row.tag)
    return frozenset(kept)


def removed_rows(options: tuple[str, ...]) -> frozenset[str]:
    """Return the tags of the rows of Table E.1-1 removed under the options.

    Those whose Basic Profile action is X and to which no selected option
    gives an action, since an option's action is K or C.
    """
    return frozenset(
        row.tag
        for row in _rows()
        if row.basic_profile == "X" and not any(o in row.options for o in options)
    )


def temporal_value(options: tuple[str, ...]) -> str:
    """Return Longitudinal Temporal Information Modified under the options.

    UNMODIFIED under Full Dates and MODIFIED under Modified Dates (PS3.15
    E.3.6), and otherwise REMOVED (E.2).
    """
    if FULL_DATES in options:
        return "UNMODIFIED"
    return "MODIFIED" if MODIFIED_DATES in options else "REMOVED"


def _unchanged(
    corpus: corpus_module.SyntheticCorpus,
) -> corpus_module.SyntheticCorpus:
    return corpus


@dataclasses.dataclass(frozen=True)
class CorpusRun:
    """A policy run over the synthetic corpus, with what the run must do.

    Attributes
    ----------
    name : str
        The test ID, and the name of the run's validation report directory,
        such as ``"basic"``. A preset's own run takes the preset's name.
    preset : str or None
        The preset, composed with
        :func:`~pymedphys._dicom.deidentify.policy.compose_policy`; or None
        for the custom option set ``options``.
    options : tuple of str
        A custom option set, composed with
        :func:`~pymedphys._dicom.deidentify.policy.compose_custom_policy`;
        empty with a preset.
    corpus : callable
        Returns the variant of the synthetic corpus to run over, given it.
    reviewed_roi_names : callable or None
        Returns the reviewed-names list for the corpus it is given, to clean
        ROI Names with the invented vocabulary; or None to run without
        descriptor cleaning.
    withheld : Mapping of str to Withheld
        Each instance the run must withhold, by its file name in the
        corpus. Every other instance must be released.
    kept : frozenset of str or None
        The rows of Table E.1-1, by tag, whose planted markers the run must
        keep at their place in every released instance, where no sequence
        that holds them is removed (:meth:`keeps`), and which no other
        released place may hold. None for the rows that the selected options
        keep (:func:`kept_rows`).
    codes : frozenset of str or None
        The CID 7050 code values that every released instance claims. None
        for the Basic Profile's and each selected option's.
    roi_names : tuple of str or None
        The ROI Names of the released structure set, in order; or None where
        the run withholds it.
    marks : tuple
        pytest marks of the run's parameter, such as a skip.
    """

    name: str
    preset: str | None = None
    options: tuple[str, ...] = ()
    corpus: Callable[[corpus_module.SyntheticCorpus], corpus_module.SyntheticCorpus] = (
        _unchanged
    )
    reviewed_roi_names: (
        Callable[[corpus_module.SyntheticCorpus], ReviewedNames] | None
    ) = None
    # A factory, since dataclasses refuse a default they cannot hash, which
    # a mapping proxy is before Python 3.12.
    withheld: Mapping[str, Withheld] = dataclasses.field(
        default_factory=lambda: BASIC_WITHHELD
    )
    kept: frozenset[str] | None = None
    codes: frozenset[str] | None = None
    roi_names: tuple[str, ...] | None = ("",)
    marks: tuple = ()

    def __post_init__(self):
        if isinstance(self.options, str):
            raise TypeError("options must be a tuple of option names")
        if self.preset is not None and self.options:
            raise ValueError(f"{self.name}: give a preset or options, not both")

    @property
    def selected(self) -> tuple[str, ...]:
        """The selected options, the preset's or the custom option set."""
        return PRESETS[self.preset] if self.preset is not None else self.options

    def policy(self) -> Policy:
        """Compose the run's policy."""
        if self.preset is not None:
            return compose_policy(self.preset)
        return compose_custom_policy(self.options)

    def kept_rows(self) -> frozenset[str]:
        """The rows whose planted markers the run keeps (:attr:`kept`)."""
        return kept_rows(self.selected) if self.kept is None else self.kept

    def keeps(self, placement: corpus_module.Placement) -> bool:
        """Whether the run keeps a placement's marker at its place.

        Its row must be kept (:meth:`kept_rows`), and so must every sequence
        of Table E.1-1 that holds it, since a sequence's other actions
        remove, empty, replace, or clean what it holds.
        """
        kept = self.kept_rows()
        return placement.profile_tag in kept and all(
            tag in kept or tag not in _listed() for tag, _ in placement.path.items
        )

    def method_codes(self) -> frozenset[tuple[str, str]]:
        """The codes every released instance claims, with their designator."""
        values = (
            {BASIC_PROFILE_CODE, *(OPTION_CODES[o] for o in self.selected)}
            if self.codes is None
            else self.codes
        )
        return frozenset((value, DCM) for value in values)

    def temporal_value(self) -> str:
        """Longitudinal Temporal Information Modified under the run's options."""
        return temporal_value(self.selected)

    def param(self) -> Any:
        """The run as a pytest parameter."""
        return pytest.param(self, id=self.name, marks=self.marks)


@dataclasses.dataclass(frozen=True)
class Prepared:
    """A run's corpus, and what its transform cleans descriptors with."""

    corpus: corpus_module.SyntheticCorpus
    reviewed: ReviewedNames | None
    cleaning: DescriptorCleaning | None

    def transform(self, policy: Policy) -> InstanceTransform:
        """The run's instance transform, which applies a policy not yet enabled."""
        return InstanceTransform(
            policy, KEY, cleaning=self.cleaning, unvalidated_policy=True
        )


def prepare(corpus_run: CorpusRun) -> Prepared:
    """Build the corpus a run is over, and its reviewed-names list."""
    corpus = corpus_run.corpus(corpus_module.build_corpus())
    if corpus_run.reviewed_roi_names is None:
        return Prepared(corpus, None, None)
    reviewed = corpus_run.reviewed_roi_names(corpus)
    return Prepared(corpus, reviewed, DescriptorCleaning(VOCABULARY, reviewed))


def structure_set(corpus: corpus_module.SyntheticCorpus) -> corpus_module.CorpusFile:
    (file,) = [file for file in corpus.files if file.manifest.iod == "RT Structure Set"]
    return file


def planted_roi_name(corpus: corpus_module.SyntheticCorpus) -> str:
    (placement,) = [
        placement
        for placement in structure_set(corpus).manifest.placements
        if placement.path.tag == ROI_NAME
    ]
    return placement.values[0]


def with_a_second_roi(
    corpus: corpus_module.SyntheticCorpus,
) -> corpus_module.SyntheticCorpus:
    """Return the corpus with a second ROI, named for the automatic tier.

    pydicom writes the structure set again, which keeps every planted value.
    """
    file = structure_set(corpus)
    dataset = pydicom.dcmread(pydicom.filebase.DicomBytesIO(file.data))
    first = dataset.StructureSetROISequence[0]
    item = pydicom.Dataset()
    item.ROINumber = max(each.ROINumber for each in dataset.StructureSetROISequence) + 1
    item.ReferencedFrameOfReferenceUID = first.ReferencedFrameOfReferenceUID
    item.ROIName = UNCLEANED_NAME
    item.ROIGenerationAlgorithm = "MANUAL"
    dataset.StructureSetROISequence.append(item)
    buffer = pydicom.filebase.DicomBytesIO()
    dataset.save_as(buffer, enforce_file_format=True)
    data = buffer.getvalue()
    return dataclasses.replace(
        corpus,
        files=tuple(
            dataclasses.replace(each, data=data) if each is file else each
            for each in corpus.files
        ),
    )


def mapped_planted_name(corpus: corpus_module.SyntheticCorpus) -> ReviewedNames:
    """Return a reviewed-names list that maps the planted ROI Name."""
    reviewed = ReviewedNames.empty()
    reviewed.record(planted_roi_name(corpus), ReviewedName(Review.MAP, MAPPED_NAME))
    return reviewed


def decoders_installed() -> bool:
    """Whether a decoding plugin of every syntax of the compressed corpus is installed."""
    return all(
        pixel_decoding.decoder_available(syntax)
        for syntax in compressed.CORPUS_SYNTAXES
    )
