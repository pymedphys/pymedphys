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

"""Benchmark-only text detectors, for the evaluation alone (D-056).

As the maintainer chose on 1 November 2026, models are measured in two
tiers. The adoptable tier is :mod:`.text_evaluation_models`: ONNX models
whose code and weights are under the Apache License 2.0 or a licence at
least as permissive, pinned by URL and SHA-256, any of which could become
the detector. The benchmark-only tier, here, measures other detectors
through the same harness, so that the adoptable ones are judged against
the field: detectors with runners of their own, such as EasyOCR's CRAFT,
OpenCV's EAST, MMOCR's detectors, docTR in PyTorch, Surya, Tesseract's
layout analysis, and Florence-2. A :class:`BenchmarkModel` may be under any
licence that permits its use on CI, as its evidence shows, but is still
pinned: each package its runner needs by version and the SHA-256 of each of
its files, and each file of weights by URL and SHA-256. Its results are
marked ``benchmark-only``, in the method, the summary, its page, and every
assessment, and none can be adopted.

A runner runs on the machine that measures, never as a service: frames of
T4 are real patients' images, so no runner may send an image anywhere.

Runners are optional and for CI alone. Their packages are never among
PyMedPhys's dependencies or in its lock file: :func:`requirements` gives a
runner's pinned packages for ``pip install --require-hashes`` into an
environment of their own, and a runner's module, inside this package,
imports its packages only when it is made. Nothing outside the evaluation
library imports this module.
"""

from __future__ import annotations

import dataclasses
import importlib
import importlib.metadata
import math
import re
import urllib.parse
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol

from pymedphys._imports import numpy as np

from .text_detection import RENDERINGS, Download, TextBox
from .text_evaluation_detector import DetectorVariant, variant_renderings
from .text_evaluation_frames import EvaluationFrame, EvaluationRefused
from .text_evaluation_models import ModelFile, frame_boxes, model_file_path

TIER = "benchmark-only"
PACKAGE_KINDS = ("pypi", "system")
# Licences that grant nothing, so cannot permit use on CI.
_NO_LICENCE = frozenset({"", "none", "noassertion", "unknown", "unlicensed"})
_SHA256 = re.compile(r"[0-9a-f]{64}")
# A runner's module must be in the evaluation library.
_RUNNER_PREFIX = "pymedphys._dicom.deidentify.text_evaluation_runner_"


@dataclasses.dataclass(frozen=True)
class RunnerPackage:
    """A package that a runner needs, pinned.

    Attributes
    ----------
    name : str
        Its distribution name, on the Python Package Index for ``"pypi"``,
        or its package name in the runner image's system for ``"system"``.
    version : str
    sha256 : tuple of str
        The SHA-256 of each file that may install it, such as a wheel for
        each platform.
    kind : str
        One of :data:`PACKAGE_KINDS`.
    """

    name: str
    version: str
    sha256: tuple[str, ...]
    kind: str = "pypi"

    def __post_init__(self):
        if not (self.name and self.version and self.sha256):
            raise EvaluationRefused("A package is pinned by version and hash.")
        if not all(_SHA256.fullmatch(each) for each in self.sha256):
            raise EvaluationRefused("A package's hashes are full SHA-256s.")
        if self.kind not in PACKAGE_KINDS:
            raise EvaluationRefused("A package's kind must be a known one.")


@dataclasses.dataclass(frozen=True)
class BenchmarkModel:
    """A benchmark-only detector, as the module describes.

    Attributes
    ----------
    name : str
        What the summary calls it.
    runner : str
        The name of its runner's module in the evaluation library, after
        ``text_evaluation_runner_``; the module's ``make`` makes the runner.
    packages : tuple of RunnerPackage
        Every package that the runner needs, its dependencies among them,
        so that pip can install them with ``--require-hashes``.
    weights : tuple of ModelFile
        Each file of weights, pinned by URL and SHA-256.
    code_licence, weights_licence : str
        As their authors state them, each permitting use on CI.
    licence_evidence : tuple of str
        Where each licence was read first-hand, over HTTPS.
    copyright : str
    homepage : str
    training_data : str
        What it was trained on, as its authors state it.
    """

    name: str
    runner: str
    packages: tuple[RunnerPackage, ...]
    weights: tuple[ModelFile, ...]
    code_licence: str
    weights_licence: str
    licence_evidence: tuple[str, ...]
    copyright: str
    homepage: str
    training_data: str

    def __post_init__(self):
        if not (self.name and self.copyright and self.training_data):
            raise EvaluationRefused(
                "A benchmark needs a name, its copyright, and its training data."
            )
        if not re.fullmatch(r"[a-z][a-z0-9_]*", self.runner):
            raise EvaluationRefused("A runner is named by its module's suffix.")
        if not self.packages:
            raise EvaluationRefused("A runner's packages must be pinned.")
        if not all(isinstance(each, ModelFile) for each in self.weights):
            raise EvaluationRefused("A benchmark's weights must be pinned files.")
        for licence in (self.code_licence, self.weights_licence):
            if licence.strip().lower() in _NO_LICENCE:
                raise EvaluationRefused(
                    "A benchmark's code and weights each need a licence."
                )
        if not self.licence_evidence or not all(
            _https(each) for each in (*self.licence_evidence, self.homepage)
        ):
            raise EvaluationRefused(
                "A benchmark's licences need evidence and its home, over HTTPS."
            )

    def described(self) -> dict[str, object]:
        """The benchmark, for the method."""
        return {
            "tier": TIER,
            "name": self.name,
            "runner": self.runner,
            "packages": {each.name: each.version for each in self.packages},
            "weights_sha256": [each.sha256 for each in self.weights],
            "code_licence": self.code_licence,
            "weights_licence": self.weights_licence,
            "copyright": self.copyright,
            "homepage": self.homepage,
        }


def _https(url: str) -> bool:
    parts = urllib.parse.urlsplit(url)
    return parts.scheme == "https" and bool(parts.netloc)


# The benchmark-only detectors that have passed their checks; each joins
# with its runner's module as it does.
BENCHMARK_MODELS: tuple[BenchmarkModel, ...] = ()


def requirements(model: BenchmarkModel) -> str:
    """The runner's Python packages, pinned by version and hash, as a pip
    requirements file for ``pip install --require-hashes --no-deps``."""
    lines = [
        f"{each.name}=={each.version} "
        + " ".join(f"--hash=sha256:{digest}" for digest in each.sha256)
        for each in model.packages
        if each.kind == "pypi"
    ]
    return "".join(f"{line}\n" for line in lines)


def check_packages(
    model: BenchmarkModel, version: Callable[[str], str] = importlib.metadata.version
) -> None:
    """Refuse a runner whose installed Python packages are not the
    versions pinned.

    Raises
    ------
    EvaluationRefused
        Naming the first package missing or of another version.
    """
    for each in model.packages:
        if each.kind != "pypi":
            continue
        try:
            installed = version(each.name)
        except importlib.metadata.PackageNotFoundError:
            raise EvaluationRefused(
                f"The runner needs {each.name} {each.version}, not installed."
            ) from None
        if installed != each.version:
            raise EvaluationRefused(
                f"The runner needs {each.name} {each.version}, not {installed}."
            )


class Runner(Protocol):
    """A benchmark's detector: an 8-bit grey image, rows by columns, and the
    setting's options, to boxes, each top, left, bottom, right in the
    image's pixels, and a score."""

    def __call__(
        self, image: np.ndarray, options: Mapping[str, object]
    ) -> Sequence[tuple[float, float, float, float, float]]:
        """The boxes of an image."""
        ...  # pylint: disable = unnecessary-ellipsis


@dataclasses.dataclass(frozen=True)
class BenchmarkPoint:
    """One setting of a benchmark-only detector.

    Attributes
    ----------
    score : float
        The least score of a box kept.
    renderings : tuple of str
        The renderings whose boxes are joined.
    margin : int
        Frame pixels added to every side of each box.
    options : tuple of tuple
        The runner's own settings, as name and value pairs, which reach the
        runner, so that each distinct set is a pass of its own.
    """

    score: float = 0.5
    renderings: tuple[str, ...] = RENDERINGS
    margin: int = 2
    options: tuple[tuple[str, object], ...] = ()

    def __post_init__(self):
        if not (math.isfinite(self.score) and 0 <= self.score <= 1):
            raise EvaluationRefused("A score must be a share.")
        if not self.renderings or not set(self.renderings) <= set(RENDERINGS):
            raise EvaluationRefused("A point must join known renderings.")
        if not isinstance(self.margin, int) or self.margin < 0:
            raise EvaluationRefused("A margin must be a whole number of pixels.")
        names = [name for name, _ in self.options]
        if len(names) != len(set(names)):
            raise EvaluationRefused("A runner's option is set once.")

    def described(self) -> dict[str, object]:
        """The setting, for the summary."""
        return {
            "score": self.score,
            "renderings": list(self.renderings),
            "margin": self.margin,
            **{f"option.{name}": value for name, value in self.options},
        }


class BenchmarkDetector:
    """A benchmark-only detector through the harness, each of its settings
    a point.

    Parameters
    ----------
    model : BenchmarkModel
    variant : DetectorVariant, optional
        Its renderings apply; its network input and post-processing do not,
        since the runner scales and post-processes as its authors made it.
    runner : Runner, optional
        Runs in place of the model's own runner, for tests. It needs
        ``runner_name``.
    runner_name : str, optional
    download : callable, optional
        Writes the file at a URL to a path, for the weights.

    Raises
    ------
    EvaluationRefused
        Where the runner's packages are not the versions pinned, or its
        module is not in the evaluation library.
    TextDetectionError
        Where weights do not have their pinned SHA-256.
    """

    def __init__(
        self,
        model: BenchmarkModel,
        variant: DetectorVariant | None = None,
        *,
        runner: Runner | None = None,
        runner_name: str | None = None,
        download: Download | None = None,
    ):
        self._model = model
        self._variant = DetectorVariant() if variant is None else variant
        if runner is not None:
            if not runner_name:
                raise EvaluationRefused("A runner given for tests needs a name.")
            self._runner = runner
            self._made: dict[str, object] = {"runner": runner_name}
            return
        check_packages(model)
        paths = tuple(
            model_file_path(each, download=download) for each in model.weights
        )
        module = importlib.import_module(_RUNNER_PREFIX + model.runner)
        self._runner = module.make(model, paths)
        self._made = {"runner": model.runner}

    @property
    def method(self) -> Mapping[str, object]:
        """What decides the boxes, marked benchmark-only."""
        return {
            "tier": TIER,
            **self._made,
            "model": self._model.described(),
            "variant": self._variant.described(),
            "numpy": np.__version__,
        }

    def boxes_of_points(
        self, frame: EvaluationFrame, points: Sequence[Any]
    ) -> list[tuple[TextBox, ...]]:
        """The boxes of each setting, for one frame, each once, sorted.

        Raises
        ------
        EvaluationRefused
            For a point that is not a :class:`BenchmarkPoint`, or that joins
            a rendering that the variant does not compute.
        """
        if not all(isinstance(point, BenchmarkPoint) for point in points):
            raise EvaluationRefused("A point is not one of the benchmark's.")
        renderings = variant_renderings(frame, self._variant)
        found_by: dict[tuple, list[tuple[float, float, float, float, float]]] = {}
        found = []
        for point in points:
            if not set(point.renderings) <= set(renderings):
                raise EvaluationRefused(
                    "A point joins a rendering that was not computed."
                )
            boxes: set[TextBox] = set()
            for name in point.renderings:
                key = (name, point.options)
                if key not in found_by:
                    found_by[key] = [
                        _checked(each)
                        for each in self._runner(renderings[name], dict(point.options))
                    ]
                kept = [each[:4] for each in found_by[key] if each[4] >= point.score]
                boxes.update(frame_boxes(kept, frame.shape, frame.shape, point.margin))
            found.append(tuple(sorted(boxes)))
        return found


def _checked(
    box: Sequence[float],
) -> tuple[float, float, float, float, float]:
    values = tuple(float(each) for each in box)
    if len(values) != 5 or not all(math.isfinite(each) for each in values):
        raise EvaluationRefused(
            "A runner gave a box that is not four sides and a score."
        )
    top, left, bottom, right, score = values
    return top, left, bottom, right, score


def tier_of(method: Mapping[str, Any]) -> str:
    """``"benchmark-only"`` where any part of a detector's method is, such
    as a benchmark joined with the rule; otherwise ``"adoptable"``."""

    def marked(value: object) -> bool:
        if isinstance(value, Mapping):
            return value.get("tier") == TIER or any(
                marked(each) for each in value.values()
            )
        if isinstance(value, (list, tuple)):
            return any(marked(each) for each in value)
        return False

    return TIER if marked(method) else "adoptable"
