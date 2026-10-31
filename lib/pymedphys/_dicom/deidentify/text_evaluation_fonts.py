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

"""Fonts that draw synthetic text for the text detector's evaluation (D-056).

A font gives the **coverage** of a string: for each pixel of a frame, the
share of its area that the glyphs' ink covers, from 0 to 1. A crisp font
gives only 0 and 1; an anti-aliased one gives shares between, at the edges of
its strokes, as a device that smooths its annotations does.

:class:`BitmapFont`
    A 5 by 7 bitmap font defined here, of capitals, small letters, digits,
    and the punctuation that annotations use, drawn crisply at whole multiples
    of its size, as many modalities draw their annotations. It needs no font
    file or rasteriser.
:class:`SmoothBitmapFont`
    The same glyphs scaled to any height by exact area sampling, at a
    sub-pixel offset, so that each pixel's coverage is the share of its area
    under the scaled glyphs' ink: an anti-aliased font without a font file.
:class:`PillowFont`
    Any TrueType or OpenType font file that the caller names, drawn by
    Pillow's FreeType rasteriser at four times the height and area sampled
    down. PyMedPhys ships no font file; which fonts to evaluate is a
    parameter, as are their files and licences.

Every font measures height as the rows from the top of a capital to the
baseline, the cap height, so that heights compare across fonts.
"""

from __future__ import annotations

import dataclasses
import functools
import importlib
import math
import os
from typing import Any, Protocol, runtime_checkable

from pymedphys._imports import numpy as np

GLYPH_ROWS = 7
GLYPH_COLUMNS = 5

# Each glyph is 7 rows of 5 columns, "#" for ink. Capitals sit on rows 0 to
# 6; small letters on rows 2 to 6, with ascenders from row 0, and those that
# descend in print are drawn within the same rows.
GLYPHS: dict[str, tuple[str, ...]] = {
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
    "a": (".....", ".....", ".###.", "....#", ".####", "#...#", ".####"),
    "b": ("#....", "#....", "#.##.", "##..#", "#...#", "#...#", "####."),
    "c": (".....", ".....", ".###.", "#....", "#....", "#...#", ".###."),
    "d": ("....#", "....#", ".##.#", "#..##", "#...#", "#...#", ".####"),
    "e": (".....", ".....", ".###.", "#...#", "#####", "#....", ".###."),
    "f": ("..##.", ".#..#", ".#...", "###..", ".#...", ".#...", ".#..."),
    "g": (".....", ".####", "#...#", "#...#", ".####", "....#", ".###."),
    "h": ("#....", "#....", "#.##.", "##..#", "#...#", "#...#", "#...#"),
    "i": ("..#..", ".....", ".##..", "..#..", "..#..", "..#..", ".###."),
    "j": ("...#.", ".....", "..##.", "...#.", "...#.", "#..#.", ".##.."),
    "k": ("#....", "#....", "#..#.", "#.#..", "##...", "#.#..", "#..#."),
    "l": (".##..", "..#..", "..#..", "..#..", "..#..", "..#..", ".###."),
    "m": (".....", ".....", "##.#.", "#.#.#", "#.#.#", "#...#", "#...#"),
    "n": (".....", ".....", "#.##.", "##..#", "#...#", "#...#", "#...#"),
    "o": (".....", ".....", ".###.", "#...#", "#...#", "#...#", ".###."),
    "p": (".....", ".....", "####.", "#...#", "####.", "#....", "#...."),
    "q": (".....", ".....", ".##.#", "#..##", ".####", "....#", "....#"),
    "r": (".....", ".....", "#.##.", "##..#", "#....", "#....", "#...."),
    "s": (".....", ".....", ".###.", "#....", ".###.", "....#", "####."),
    "t": (".#...", ".#...", "###..", ".#...", ".#...", ".#..#", "..##."),
    "u": (".....", ".....", "#...#", "#...#", "#...#", "#..##", ".##.#"),
    "v": (".....", ".....", "#...#", "#...#", "#...#", ".#.#.", "..#.."),
    "w": (".....", ".....", "#...#", "#...#", "#.#.#", "#.#.#", ".#.#."),
    "x": (".....", ".....", "#...#", ".#.#.", "..#..", ".#.#.", "#...#"),
    "y": (".....", ".....", "#...#", "#...#", ".####", "....#", ".###."),
    "z": (".....", ".....", "#####", "...#.", "..#..", ".#...", "#####"),
    ":": (".....", "..#..", "..#..", ".....", "..#..", "..#..", "....."),
    "-": (".....", ".....", ".....", "#####", ".....", ".....", "....."),
    "/": ("....#", "....#", "...#.", "..#..", ".#...", "#....", "#...."),
    "^": ("..#..", ".#.#.", "#...#", ".....", ".....", ".....", "....."),
    ".": (".....", ".....", ".....", ".....", ".....", ".##..", ".##.."),
    ",": (".....", ".....", ".....", ".....", ".##..", "..#..", ".#..."),
    "'": ("..#..", "..#..", ".#...", ".....", ".....", ".....", "....."),
    "(": ("...#.", "..#..", ".#...", ".#...", ".#...", "..#..", "...#."),
    ")": (".#...", "..#..", "...#.", "...#.", "...#.", "..#..", ".#..."),
    "[": (".###.", ".#...", ".#...", ".#...", ".#...", ".#...", ".###."),
    "]": (".###.", "...#.", "...#.", "...#.", "...#.", "...#.", ".###."),
    "<": ("...#.", "..#..", ".#...", "#....", ".#...", "..#..", "...#."),
    ">": (".#...", "..#..", "...#.", "....#", "...#.", "..#..", ".#..."),
    "#": (".#.#.", ".#.#.", "#####", ".#.#.", "#####", ".#.#.", ".#.#."),
    "%": ("##...", "##..#", "...#.", "..#..", ".#...", "#..##", "...##"),
    "+": (".....", "..#..", "..#..", "#####", "..#..", "..#..", "....."),
    "=": (".....", ".....", "#####", ".....", "#####", ".....", "....."),
    "*": (".....", "..#..", "#.#.#", ".###.", "#.#.#", "..#..", "....."),
    "_": (".....", ".....", ".....", ".....", ".....", ".....", "#####"),
    " ": (".....", ".....", ".....", ".....", ".....", ".....", "....."),
}

CHARACTERS = frozenset(GLYPHS)


class FontRefused(ValueError):
    """A font cannot draw a string; the message quotes no character."""


@runtime_checkable
class Font(Protocol):
    """Draws strings as coverage, as the module describes."""

    @property
    def name(self) -> str:
        """What the summary calls the font: not a path."""

    def coverage(
        self, text: str, height: float, phase: tuple[float, float] = (0.0, 0.0)
    ) -> np.ndarray:
        """Return the coverage of ``text`` with a cap height of ``height``
        pixels, offset by ``phase`` of a pixel down and right, as floats from
        0 to 1, rows by columns.

        Raises
        ------
        FontRefused
            If the font has no glyph for a character, or the height is not
            a positive number.
        """


def glyph_mask(text: str) -> np.ndarray:
    """The ink of ``text`` in the bitmap font at one pixel a font pixel, one
    column between glyphs.

    Raises
    ------
    FontRefused
        If a character has no glyph, or the text is empty.
    """
    if not text:
        raise FontRefused("There is no text to draw.")
    if not set(text) <= CHARACTERS:
        raise FontRefused("The bitmap font has no glyph for a character.")
    columns = []
    for index, character in enumerate(text):
        glyph = np.array([[cell == "#" for cell in row] for row in GLYPHS[character]])
        if index:
            columns.append(np.zeros((GLYPH_ROWS, 1), bool))
        columns.append(glyph)
    return np.concatenate(columns, axis=1)


def _checked_height(height: float) -> float:
    if not (isinstance(height, (int, float)) and math.isfinite(height) and height > 0):
        raise FontRefused("A height must be a positive number of pixels.")
    return float(height)


@dataclasses.dataclass(frozen=True)
class BitmapFont:
    """The 5 by 7 bitmap font, each font pixel a whole number of frame
    pixels a side: the height, in pixels, over 7, rounded, and at least 1.
    The phase is ignored, as a crisp font has none."""

    @property
    def name(self) -> str:
        return "bitmap-5x7"

    def coverage(
        self, text: str, height: float, phase: tuple[float, float] = (0.0, 0.0)
    ) -> np.ndarray:
        del phase
        scale = max(1, round(_checked_height(height) / GLYPH_ROWS))
        mask = glyph_mask(text)
        return np.kron(mask, np.ones((scale, scale))).astype(np.float64)


@dataclasses.dataclass(frozen=True)
class SmoothBitmapFont:
    """The 5 by 7 bitmap font scaled to any cap height by exact area
    sampling, as the module describes."""

    @property
    def name(self) -> str:
        return "bitmap-5x7-smooth"

    def coverage(
        self, text: str, height: float, phase: tuple[float, float] = (0.0, 0.0)
    ) -> np.ndarray:
        scale = _checked_height(height) / GLYPH_ROWS
        mask = glyph_mask(text).astype(np.float64)
        return area_resampled(mask, scale, phase)


def area_resampled(
    image: np.ndarray, scale: float, phase: tuple[float, float] = (0.0, 0.0)
) -> np.ndarray:
    """Scale an image of coverage by ``scale``, offset by ``phase`` of an
    output pixel down and right, giving each output pixel the mean of the
    input over its area: exact box filtering, which keeps the total coverage
    times ``scale`` squared.

    Parameters
    ----------
    image : numpy.ndarray
        Coverage, rows by columns.
    scale : float
        Output pixels to an input pixel, more than 0.
    phase : tuple of float
        Each from 0 up to 1.
    """
    if not (math.isfinite(scale) and scale > 0):
        raise FontRefused("A scale must be a positive number.")
    if not all(0.0 <= each < 1.0 for each in phase):
        raise FontRefused("A phase must be from 0 up to 1 of a pixel.")
    rows = _weights(image.shape[0], scale, phase[0])
    columns = _weights(image.shape[1], scale, phase[1])
    return np.clip(rows @ image @ columns.T, 0.0, 1.0)


def _weights(length: int, scale: float, phase: float) -> np.ndarray:
    """The share of each output pixel's length that each input pixel
    covers, output pixels by input pixels."""
    edges = phase + scale * np.arange(length + 1, dtype=np.float64)
    size = math.ceil(edges[-1] - 1e-9)
    low = np.arange(size, dtype=np.float64)[:, None]
    overlap = np.minimum(low + 1, edges[None, 1:]) - np.maximum(low, edges[None, :-1])
    return np.clip(overlap, 0.0, None)


# Pillow draws at this many times the height, and the result is area sampled
# down, so that its coverage is sampled as the smooth bitmap font's is.
_SUPERSAMPLE = 4


@dataclasses.dataclass(frozen=True)
class PillowFont:
    """A TrueType or OpenType font file drawn by Pillow, as the module
    describes.

    Parameters
    ----------
    name : str
        What the summary calls the font, such as its family and style; the
        path is never published.
    path : str or os.PathLike, optional
        The font file. None draws Pillow's own default font, which Pillow
        builds with FreeType.
    index : int
        Which face of a font collection to draw.
    """

    name: str
    path: str | os.PathLike | None = None
    index: int = 0

    def coverage(
        self, text: str, height: float, phase: tuple[float, float] = (0.0, 0.0)
    ) -> np.ndarray:
        if not text:
            raise FontRefused("There is no text to draw.")
        height = _checked_height(height)
        size = max(1, round(height * _SUPERSAMPLE / self._cap_ratio()))
        image_module, draw_module = _pillow("PIL.Image"), _pillow("PIL.ImageDraw")
        font = self._font(size)
        left, top, right, bottom = font.getbbox(text)
        _, cap_top, _, baseline = font.getbbox("H")
        if right <= left or bottom <= top:
            raise FontRefused("The font draws nothing for the text.")
        # Rows from the top of a capital, so that the cap height is the
        # height asked for and descenders fall below it.
        top = min(top, cap_top)
        bottom = max(bottom, baseline)
        canvas = image_module.new("L", (right - left, bottom - top), 0)
        draw_module.Draw(canvas).text((-left, -top), text, fill=255, font=font)
        drawn = np.asarray(canvas, dtype=np.float64) / 255.0
        return area_resampled(drawn, 1.0 / _SUPERSAMPLE, phase)

    def _font(self, size: int) -> Any:
        return _loaded(self.path, self.index, size)

    def _cap_ratio(self) -> float:
        """The cap height over the font size."""
        reference = 400
        _, top, _, bottom = self._font(reference).getbbox("H")
        if bottom <= top:
            raise FontRefused("The font has no capital H to measure.")
        return (bottom - top) / reference


@functools.lru_cache(maxsize=64)
def _loaded(path: str | os.PathLike | None, index: int, size: int) -> Any:
    image_font = _pillow("PIL.ImageFont")
    if path is None:
        return image_font.load_default(size)
    return image_font.truetype(os.fspath(path), size, index=index)


def _pillow(module: str) -> Any:
    """A module of Pillow, imported when a Pillow font first draws, since
    only that needs it."""
    try:
        return importlib.import_module(module)
    except ImportError:
        raise FontRefused(
            'Pillow fonts need Pillow: install "pymedphys[user]"'
        ) from None
