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

"""Synthetic frames with burned-in text at known places, for text detection.

Text is drawn in a 5 by 7 bitmap font defined here, as many modalities draw
their annotations, scaled by whole pixels, so the frames depend on no font
file or rendering library. Backgrounds are geometric phantoms with Gaussian
noise from a seeded generator; no frame holds real data.
"""

from __future__ import annotations

import dataclasses

from pymedphys._imports import numpy as np

# Each glyph is 7 rows of 5 columns, "#" for ink.
_GLYPHS = {
    "0": (".###.", "#...#", "#..##", "#.#.#", "##..#", "#...#", ".###."),
    "1": ("..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."),
    "2": (".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"),
    "3": ("####.", "....#", "....#", ".###.", "....#", "....#", "####."),
    "4": ("...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."),
    "5": ("#####", "#....", "####.", "....#", "....#", "#...#", ".###."),
    "6": (".###.", "#....", "#....", "####.", "#...#", "#...#", ".###."),
    "7": ("#####", "....#", "...#.", "..#..", ".#...", ".#...", ".#..."),
    "8": (".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."),
    "9": (".###.", "#...#", "#...#", ".####", "....#", "....#", ".###."),
    "A": (".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    "B": ("####.", "#...#", "#...#", "####.", "#...#", "#...#", "####."),
    "C": (".###.", "#...#", "#....", "#....", "#....", "#...#", ".###."),
    "D": ("####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."),
    "E": ("#####", "#....", "#....", "####.", "#....", "#....", "#####"),
    "F": ("#####", "#....", "#....", "####.", "#....", "#....", "#...."),
    "G": (".###.", "#...#", "#....", "#.###", "#...#", "#...#", ".####"),
    "H": ("#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    "I": (".###.", "..#..", "..#..", "..#..", "..#..", "..#..", ".###."),
    "J": ("..###", "...#.", "...#.", "...#.", "...#.", "#..#.", ".##.."),
    "K": ("#...#", "#..#.", "#.#..", "##...", "#.#..", "#..#.", "#...#"),
    "L": ("#....", "#....", "#....", "#....", "#....", "#....", "#####"),
    "M": ("#...#", "##.##", "#.#.#", "#.#.#", "#...#", "#...#", "#...#"),
    "N": ("#...#", "#...#", "##..#", "#.#.#", "#..##", "#...#", "#...#"),
    "O": (".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    "P": ("####.", "#...#", "#...#", "####.", "#....", "#....", "#...."),
    "Q": (".###.", "#...#", "#...#", "#...#", "#.#.#", "#..#.", ".##.#"),
    "R": ("####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"),
    "S": (".####", "#....", "#....", ".###.", "....#", "....#", "####."),
    "T": ("#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."),
    "U": ("#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    "V": ("#...#", "#...#", "#...#", "#...#", "#...#", ".#.#.", "..#.."),
    "W": ("#...#", "#...#", "#...#", "#.#.#", "#.#.#", "#.#.#", ".#.#."),
    "X": ("#...#", "#...#", ".#.#.", "..#..", ".#.#.", "#...#", "#...#"),
    "Y": ("#...#", "#...#", ".#.#.", "..#..", "..#..", "..#..", "..#.."),
    "Z": ("#####", "....#", "...#.", "..#..", ".#...", "#....", "#####"),
    ":": (".....", "..#..", "..#..", ".....", "..#..", "..#..", "....."),
    "-": (".....", ".....", ".....", "#####", ".....", ".....", "....."),
    "/": ("....#", "....#", "...#.", "..#..", ".#...", "#....", "#...."),
    "^": ("..#..", ".#.#.", "#...#", ".....", ".....", ".....", "....."),
    ".": (".....", ".....", ".....", ".....", ".....", ".##..", ".##.."),
    " ": (".....", ".....", ".....", ".....", ".....", ".....", "....."),
}

GLYPH_ROWS = 7
GLYPH_COLUMNS = 5


def text_mask(text: str, scale: int = 1) -> np.ndarray:
    """The ink of ``text`` in the bitmap font, one column between glyphs,
    each font pixel ``scale`` frame pixels a side."""
    columns = []
    for index, character in enumerate(text):
        glyph = np.array(
            [[cell == "#" for cell in row] for row in _GLYPHS[character]], dtype=bool
        )
        if index:
            columns.append(np.zeros((GLYPH_ROWS, 1), bool))
        columns.append(glyph)
    mask = np.concatenate(columns, axis=1)
    return np.kron(mask, np.ones((scale, scale), bool))


@dataclasses.dataclass(frozen=True)
class Burned:
    """A string burned into a frame, and the frame pixels of its ink."""

    text: str
    ink: np.ndarray  # bool, the frame's shape


def ct_slice(rng: np.random.Generator, size: int = 512) -> np.ndarray:
    """A 12-bit CT-like axial slice (stored value = HU + 1024): air, a body
    with lungs, a vertebra, a rib ring, and a couch, with noise of 12 HU."""
    y, x = np.indices((size, size), dtype=np.float64)
    y = (y - size / 2) / (size / 2)
    x = (x - size / 2) / (size / 2)
    hu = np.full((size, size), -1000.0)
    body = (x / 0.85) ** 2 + (y / 0.6) ** 2 < 1
    hu[body] = 40
    for centre in (-0.35, 0.35):
        hu[((x - centre) / 0.28) ** 2 + ((y + 0.05) / 0.38) ** 2 < 1] = -850
    hu[(x / 0.08) ** 2 + ((y - 0.4) / 0.08) ** 2 < 1] = 900
    hu[(np.abs(np.hypot(x / 0.8, y / 0.55) - 1) < 0.02) & body] = 700
    hu[(y > 0.72) & (y < 0.76) & (np.abs(x) < 0.95)] = 200
    hu += rng.normal(0, 12, hu.shape)
    return np.clip(np.rint(hu + 1024), 0, 4095)


def burn(
    frame: np.ndarray, text: str, top: int, left: int, value: float, scale: int = 1
) -> tuple[np.ndarray, Burned]:
    """Return a copy of ``frame`` with ``text`` drawn at ``value``."""
    mask = text_mask(text, scale)
    ink = np.zeros(frame.shape, bool)
    ink[top : top + mask.shape[0], left : left + mask.shape[1]] = mask
    burned = frame.copy()
    burned[ink] = value
    return burned, Burned(text, ink)
