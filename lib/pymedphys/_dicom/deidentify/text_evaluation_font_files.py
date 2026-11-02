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

"""Font files for the text detector's synthetic text, each pinned (D-056).

PyMedPhys ships no font file. The fonts here are fetched when a test or
check first draws with one, from a wheel on the Python Package Index named
by its URL, and are used only if the wheel and the font in it have the
SHA-256 digests pinned here; both are kept in PyMedPhys's data directory.
Each is licensed under the SIL Open Font License, version 1.1, as the
copyright and licence in its own name table say, recorded with it
(:attr:`PinnedFont.copyright`).

Three wheels hold a font as a file. One, ``pymupdf-fonts``, holds each font
as an LZMA-compressed, base64-encoded bytes literal in a Python module; that
module is parsed as data, by :mod:`ast`, and never imported or run.

:func:`pinned_font` gives a :class:`~.text_evaluation_fonts.PillowFont` that
draws one; :data:`PINNED_FONTS` lists them, as sans-serif, serif, and
monospaced faces in regular and bold weights, beside the bitmap fonts that
need no file.
"""

from __future__ import annotations

import ast
import base64
import dataclasses
import hashlib
import io
import lzma
import os
import pathlib
import posixpath
import re
import urllib.parse
import zipfile
from collections.abc import Callable

from pymedphys._data.download import (
    download_lock,
    download_with_progress,
    get_data_dir,
)

from .text_evaluation_fonts import FontRefused, PillowFont

CACHE_DIRECTORY = "text-evaluation-fonts"
ENCODINGS = ("file", "pymupdf-fonts-module")
STYLES = ("sans", "serif", "mono")
OFL = "SIL Open Font License 1.1"
OFL_URL = "https://openfontlicense.org/open-font-license-official-text/"
_SHA256 = re.compile(r"[0-9a-f]{64}")

Download = Callable[[str, pathlib.Path], None]


@dataclasses.dataclass(frozen=True)
class PinnedFont:
    """A font file in a wheel, pinned by both digests, and its licence.

    Attributes
    ----------
    name : str
        What the summary calls it.
    style : str
        One of :data:`STYLES`.
    url : str
        The wheel's HTTPS URL.
    sha256 : str
        The SHA-256 of the wheel.
    member : str
        The font's path in the wheel.
    member_sha256 : str
        The SHA-256 of the font's own bytes.
    encoding : str
        How the member holds the font, one of :data:`ENCODINGS`.
    copyright : str
        The copyright in the font's name table.
    licence : str
    """

    name: str
    style: str
    url: str
    sha256: str
    member: str
    member_sha256: str
    encoding: str
    copyright: str
    licence: str = OFL

    def __post_init__(self):
        for field in ("sha256", "member_sha256"):
            if not _SHA256.fullmatch(getattr(self, field)):
                raise ValueError(f"{field} must be 64 lowercase hexadecimal digits")
        parts = urllib.parse.urlsplit(self.url)
        if parts.scheme != "https" or not posixpath.basename(parts.path):
            raise ValueError("url must be an https URL that names a file")
        if self.encoding not in ENCODINGS or self.style not in STYLES:
            raise ValueError("encoding and style must be known ones")

    @property
    def file(self) -> str:
        """The wheel's file name, as the last part of its URL."""
        return posixpath.basename(urllib.parse.urlsplit(self.url).path)


_SOURCE_SANS = (
    "https://files.pythonhosted.org/packages/4c/95/"
    "3d29d2f821bd368f74ab5fe5e7d5bf0a55a0a26d3202a56526f475e51c1b/"
    "font_source_sans_pro-0.0.1-py3-none-any.whl",
    "2250396f565a0fea35726e56059216d1d5d75071d64d075ebdfec183b4b85765",
)
_SOURCE_SERIF = (
    "https://files.pythonhosted.org/packages/5d/06/"
    "bbb42742135b3fc99cf330dfcc47701d46967aae602f29f4b52b5967a912/"
    "font_source_serif_pro-0.0.1-py3-none-any.whl",
    "38dd9a8d8027d22aa8ef2d10d27d7c558701b32772ff9f3790f509577e91dca4",
)
_LATO = (
    "https://files.pythonhosted.org/packages/d1/eb/"
    "4422409b5a32ab9a2f420188740ac00019385a84783ecde1a1ec35e4d349/"
    "font_lato-0.1.0-py3-none-any.whl",
    "ff74f2d4647187bac4b853ab8215e6b2afe124fcd01c809629aadd8f4356e959",
)
_PYMUPDF_FONTS = (
    "https://files.pythonhosted.org/packages/80/a3/"
    "1701c6109a1cf31f4c24156f3242db0afe669fecedf4d27c72e3b7e67591/"
    "pymupdf_fonts-1.0.5-py3-none-any.whl",
    "8e4bb70a4a8f6bb895ef8f3b77b98f6c43e2f39c31cfdec5fd21c3d512c38b25",
)
_ADOBE_SANS = (
    "Copyright 2010, 2012, 2014 Adobe Systems Incorporated "
    "(http://www.adobe.com/), with Reserved Font Name 'Source'."
)
_ADOBE_SERIF = (
    "© 2014 - 2018 Adobe Systems Incorporated (http://www.adobe.com/), "
    "with Reserved Font Name 'Source'."
)
_LATO_COPYRIGHT = (
    "Copyright (c) 2010-2011 by tyPoland Lukasz Dziedzic with Reserved Font "
    'Name "Lato".'
)
_NOTO = "Copyright 2015 Google Inc. All Rights Reserved."
_FIRA_MONO = (
    "Digitized data copyright © 2012-2015, The Mozilla Foundation and Telefonica S.A."
)
_FIRAGO = (
    "Digitized data copyright 2012–2018 for FiraGO, bBox Type GmbH and HERE "
    'Europe B.V. All rights reserved, with Reserved Font Name "Fira" / '
    "Digitized data copyright 2012–2018 for Fira Sans The Mozilla "
    "Foundation, Telefonica S.A., Carrois Corporate GbR and bBox Type GmbH, "
    'with Reserved Font Name "Fira"'
)
_SPACE_MONO = "Copyright 2016 Google Inc. All Rights Reserved."


def _pin(name, style, wheel, member, member_sha256, encoding, copyright_):
    url, sha256 = wheel
    return PinnedFont(
        name=name,
        style=style,
        url=url,
        sha256=sha256,
        member=member,
        member_sha256=member_sha256,
        encoding=encoding,
        copyright=copyright_,
    )


PINNED_FONTS: tuple[PinnedFont, ...] = (
    _pin(
        "source-sans-pro",
        "sans",
        _SOURCE_SANS,
        "font_source_sans_pro/files/SourceSansPro-Regular.ttf",
        "b77f3a700edd0fc0dec73258f882d5c3926c77f5caf6800a201d2166568d2309",
        "file",
        _ADOBE_SANS,
    ),
    _pin(
        "source-sans-pro-bold",
        "sans",
        _SOURCE_SANS,
        "font_source_sans_pro/files/SourceSansPro-Bold.ttf",
        "2efc3a95d076f2d04c5928c0ad698b7c61cc302d6f6e79e9643cd3722f7becc2",
        "file",
        _ADOBE_SANS,
    ),
    _pin(
        "source-serif-pro",
        "serif",
        _SOURCE_SERIF,
        "font_source_serif_pro/files/SourceSerifPro-Regular.ttf",
        "b4e0771f06d8f6573a535312762b0b2f4fb9a03372239e39b0e7cf203da8ea9a",
        "file",
        _ADOBE_SERIF,
    ),
    _pin(
        "source-serif-pro-bold",
        "serif",
        _SOURCE_SERIF,
        "font_source_serif_pro/files/SourceSerifPro-Bold.ttf",
        "78041207a9c5166a82d41676d4c87f4c5ba4e1c13ac654e6e9e3538a5a0b0525",
        "file",
        _ADOBE_SERIF,
    ),
    _pin(
        "lato",
        "sans",
        _LATO,
        "font_lato/files/Lato-Regular.ttf",
        "e82542aed8293f49fc83c4aaea566b1f6b4fc7a9ab5da11e6fb9bc0973b5324b",
        "file",
        _LATO_COPYRIGHT,
    ),
    _pin(
        "lato-bold",
        "sans",
        _LATO,
        "font_lato/files/Lato-Bold.ttf",
        "d7f0b7f2570f2f28b504da1181b4d71b1420b10be2c4fd690927f1c8ee3b19c3",
        "file",
        _LATO_COPYRIGHT,
    ),
    _pin(
        "noto-sans",
        "sans",
        _PYMUPDF_FONTS,
        "pymupdf_fonts/NotoSans_Regular.py",
        "6b04c8dd65af6b73eb4279472ed1580b29102d6496a377340e80a40cdb3b22c9",
        "pymupdf-fonts-module",
        _NOTO,
    ),
    _pin(
        "noto-sans-bold",
        "sans",
        _PYMUPDF_FONTS,
        "pymupdf_fonts/NotoSans_Bold.py",
        "7c15ac396d2ce6bc33a3b4efacdbd322c9e46376599a725c6f790d8036052cab",
        "pymupdf-fonts-module",
        _NOTO,
    ),
    _pin(
        "firago",
        "sans",
        _PYMUPDF_FONTS,
        "pymupdf_fonts/FiraGO_Regular.py",
        "495901c0c608ea265f4c31aa2a4c7a313e5cc2a3dd610da78a447fe8e07454a2",
        "pymupdf-fonts-module",
        _FIRAGO,
    ),
    _pin(
        "fira-mono",
        "mono",
        _PYMUPDF_FONTS,
        "pymupdf_fonts/FiraMono_Regular.py",
        "1783904b9a03d1852ed185549d74526d9f6a4a643181eb591c3a69993ae42ced",
        "pymupdf-fonts-module",
        _FIRA_MONO,
    ),
    _pin(
        "fira-mono-bold",
        "mono",
        _PYMUPDF_FONTS,
        "pymupdf_fonts/FiraMono_Bold.py",
        "12b994171a99952fead7756658dfcf3dc69d79e07fff3303444f003580df9a19",
        "pymupdf-fonts-module",
        _FIRA_MONO,
    ),
    _pin(
        "space-mono",
        "mono",
        _PYMUPDF_FONTS,
        "pymupdf_fonts/SpaceMono_Regular.py",
        "d0855b0c557b78ea0449762b25ccca018880f483e56ff9a69e7cbde1dc12fa3a",
        "pymupdf-fonts-module",
        _SPACE_MONO,
    ),
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _wheel(font: PinnedFont, download: Download | None) -> bytes:
    """The pinned wheel's bytes, downloaded into the cache once."""
    path = get_data_dir() / CACHE_DIRECTORY / font.file
    path.parent.mkdir(parents=True, exist_ok=True)
    with download_lock(path):
        if not (path.exists() and _sha256(path.read_bytes()) == font.sha256):
            # Download beside the cache and move into place only once the
            # digest matches, so that the cache never holds another file.
            partial = path.with_name(f".{path.name}.download")
            try:
                (download_with_progress if download is None else download)(
                    font.url, partial
                )
                if _sha256(partial.read_bytes()) != font.sha256:
                    raise FontRefused(
                        f"the file downloaded from {font.url} does not have "
                        f"the pinned SHA-256 {font.sha256}"
                    )
                os.replace(partial, path)
            finally:
                partial.unlink(missing_ok=True)
        return path.read_bytes()


def _decoded_module(source: bytes) -> bytes:
    """The font in a ``pymupdf-fonts`` module: its one bytes literal,
    base64-decoded and LZMA-decompressed. The module is parsed, never run."""
    try:
        tree = ast.parse(source.decode("utf-8"))
    except (SyntaxError, UnicodeDecodeError, ValueError) as error:
        raise FontRefused("A font module could not be parsed.") from error
    literals = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, bytes)
    ]
    if len(literals) != 1:
        raise FontRefused("A font module must hold one bytes literal.")
    try:
        return lzma.decompress(base64.b64decode(literals[0], validate=True))
    except (ValueError, lzma.LZMAError) as error:
        raise FontRefused("A font module's literal could not be decoded.") from error


def font_bytes(font: PinnedFont, *, download: Download | None = None) -> bytes:
    """The pinned font's own bytes, fetched and checked as the module
    describes.

    Raises
    ------
    FontRefused
        If the wheel or the font does not have its pinned SHA-256, or the
        wheel does not hold the font.
    OSError
        If the wheel cannot be downloaded or written, such as offline.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(_wheel(font, download))) as wheel:
            content = wheel.read(font.member)
    except (KeyError, zipfile.BadZipFile):
        raise FontRefused(f"{font.file} does not hold {font.member}") from None
    if font.encoding == "pymupdf-fonts-module":
        content = _decoded_module(content)
    if _sha256(content) != font.member_sha256:
        raise FontRefused(
            f"{font.member} does not have the pinned SHA-256 {font.member_sha256}"
        )
    return content


def font_path(font: PinnedFont, *, download: Download | None = None) -> pathlib.Path:
    """A path to the pinned font's file in the cache, written once checked."""
    content = font_bytes(font, download=download)
    suffix = ".otf" if content[:4] == b"OTTO" else ".ttf"
    path = (
        get_data_dir()
        / CACHE_DIRECTORY
        / f"{font.name}-{font.member_sha256[:16]}{suffix}"
    )
    with download_lock(path):
        if not (path.exists() and _sha256(path.read_bytes()) == font.member_sha256):
            partial = path.with_name(f".{path.name}.write")
            try:
                partial.write_bytes(content)
                os.replace(partial, path)
            finally:
                partial.unlink(missing_ok=True)
    return path


def pinned_font(font: PinnedFont, *, download: Download | None = None) -> PillowFont:
    """A font that draws the pinned font, by its name."""
    return PillowFont(font.name, font_path(font, download=download))


def licences() -> str:
    """The licence of every pinned font, for a page of credits."""
    lines = [
        f"- {font.name}: {font.copyright} Licensed under the {font.licence} "
        f"({OFL_URL}). From {font.file}."
        for font in PINNED_FONTS
    ]
    return "\n".join(lines) + "\n"
