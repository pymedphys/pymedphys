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

"""Intervals for the text detector's evaluation (D-056): the Wilson score
interval of a share, and the percentile interval of a ratio of sums from a
bootstrap that resamples clusters (subjects), with its seeds."""

from __future__ import annotations

import hashlib
import math

from pymedphys._imports import numpy as np

_Z = 1.959963984540054


def wilson(successes: int, trials: int) -> tuple[float, float] | None:
    """The 95% Wilson score interval of a share, or None without trials."""
    if trials <= 0:
        return None
    share = successes / trials
    z2 = _Z * _Z
    denominator = 1 + z2 / trials
    centre = (share + z2 / (2 * trials)) / denominator
    half = (
        _Z
        * math.sqrt(share * (1 - share) / trials + z2 / (4 * trials * trials))
        / denominator
    )
    return (max(0.0, centre - half), min(1.0, centre + half))


def cluster_bootstrap(
    numerators: np.ndarray,
    denominators: np.ndarray,
    *,
    replicates: int,
    seed: int,
) -> tuple[float, float] | None:
    """The 95% percentile interval of a ratio of sums, resampling clusters
    with replacement; None with fewer than two clusters that count.

    The clusters are put in the order of their counts before they are
    resampled, so that the interval depends on their counts alone, not on
    the order in which they are given."""
    numerators = np.asarray(numerators, dtype=np.float64)
    denominators = np.asarray(denominators, dtype=np.float64)
    counted = denominators > 0
    if int(np.count_nonzero(counted)) < 2 or replicates < 1:
        return None
    numerators, denominators = numerators[counted], denominators[counted]
    order = np.lexsort((numerators, denominators))
    numerators, denominators = numerators[order], denominators[order]
    rng = np.random.default_rng(seed)
    chosen = rng.integers(0, numerators.size, size=(replicates, numerators.size))
    ratios = numerators[chosen].sum(axis=1) / denominators[chosen].sum(axis=1)
    low, high = np.percentile(ratios, [2.5, 97.5])
    return (float(low), float(high))


def seed_of(*parts: object) -> int:
    """A 64-bit seed from the parts, joined by NUL, by SHA-256."""
    digest = hashlib.sha256("\0".join(str(each) for each in parts).encode()).digest()
    return int.from_bytes(digest[:8], "big")
