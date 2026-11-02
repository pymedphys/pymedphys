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

"""Pillow's bitmap font, and the font files pinned for synthetic text.

Tests that draw a pinned font fetch it the first time, and are skipped
where it cannot be fetched, such as offline."""

import base64
import hashlib
import importlib.util
import io
import lzma
import pathlib
import urllib.error
import zipfile

from pymedphys._imports import numpy as np
from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import text_evaluation_font_files as font_files
from pymedphys._dicom.deidentify import text_evaluation_fonts as fonts

PACKAGE = pathlib.Path(font_files.__file__).parents[2]


def _skip_without_pillow():
    if importlib.util.find_spec("PIL") is None:
        pytest.skip("needs Pillow")


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _cap_rows(coverage):
    rows = np.flatnonzero(coverage.max(axis=1) > 0.5)
    return rows[-1] - rows[0] + 1


# -- Pillow's bitmap font -----------------------------------------------------


def test_pillows_bitmap_font_is_crisp_at_whole_multiples():
    _skip_without_pillow()
    font = fonts.PillowBitmapFont(crisp=True)
    assert font.name == "pillow-bitmap"
    _, cap = fonts._bitmap_drawn("H")  # pylint: disable = protected-access
    for multiple in (1, 2, 3):
        coverage = font.coverage("H", cap * multiple + 0.4)
        assert set(np.unique(coverage)) <= {0.0, 1.0}
        assert _cap_rows(coverage) == cap * multiple


def test_pillows_bitmap_font_is_smooth_at_any_height():
    _skip_without_pillow()
    font = fonts.PillowBitmapFont()
    assert font.name == "pillow-bitmap-smooth"
    for height in (9.0, 14.5, 25.0):
        coverage = font.coverage("HHH", height, phase=(0.5, 0.25))
        assert _cap_rows(coverage) == pytest.approx(height, abs=1.5)
        assert ((coverage > 0.05) & (coverage < 0.95)).any()
        assert font.coverage("Smith, J 12/03/1961", height).any()
    with pytest.raises(fonts.FontRefused):
        font.coverage("", 10)


# -- Pins -----------------------------------------------------------------------


def test_every_pinned_font_is_open_font_licensed_and_pinned_twice():
    names = [font.name for font in font_files.PINNED_FONTS]
    assert len(names) == len(set(names))
    assert {font.style for font in font_files.PINNED_FONTS} == set(font_files.STYLES)
    for font in font_files.PINNED_FONTS:
        assert font.licence == "SIL Open Font License 1.1"
        assert font.url.startswith("https://files.pythonhosted.org/")
        assert font.copyright
    page = font_files.licences()
    assert all(font.name in page for font in font_files.PINNED_FONTS)


def test_no_font_file_ships_in_the_package():
    shipped = [
        path
        for path in PACKAGE.rglob("*")
        if path.suffix.lower() in (".ttf", ".otf", ".ttc", ".woff", ".woff2")
    ]
    assert not shipped


@pytest.mark.parametrize(
    "fields",
    [
        {"sha256": "0" * 63},
        {"member_sha256": "A" * 64},
        {"url": "http://files.example.org/fonts.whl"},
        {"encoding": "zip"},
        {"style": "script"},
    ],
)
def test_a_pin_must_be_https_full_digests_and_known_kinds(fields):
    valid = {
        "name": "font",
        "style": "sans",
        "url": "https://files.example.org/fonts.whl",
        "sha256": "0" * 64,
        "member": "font.ttf",
        "member_sha256": "0" * 64,
        "encoding": "file",
        "copyright": "Invented.",
    }
    with pytest.raises(ValueError):
        font_files.PinnedFont(**{**valid, **fields})


# -- Fetching -------------------------------------------------------------------


@pytest.fixture(name="data_dir")
def fixture_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("PYMEDPHYS_DATA_DIR", str(tmp_path / "data"))
    return tmp_path / "data"


FONT = b"\x00\x01\x00\x00 an invented font"
# A module that would fail if it were ever run, holding the font as
# pymupdf-fonts does.
MODULE = (
    "raise SystemExit('never run')\n"
    "fontbuffer = lzma.decompress(base64.b64decode(\n"
    f"    {base64.b64encode(lzma.compress(FONT))!r}\n"
    "))\n"
).encode()


def _wheel(members):
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as wheel:
        for name, content in members.items():
            wheel.writestr(name, content)
    return data.getvalue()


def _serving(content, calls=None):
    def download(url, path):
        if calls is not None:
            calls.append(url)
        pathlib.Path(path).write_bytes(content)

    return download


def _pin(wheel, member, encoding="file", member_sha256=None):
    return font_files.PinnedFont(
        name="invented",
        style="sans",
        url="https://files.example.org/invented-1.0-py3-none-any.whl",
        sha256=_sha256(wheel),
        member=member,
        member_sha256=member_sha256 or _sha256(FONT),
        encoding=encoding,
        copyright="Invented.",
    )


def test_a_font_file_is_fetched_once_and_checked(data_dir):
    wheel = _wheel({"fonts/a.ttf": FONT})
    calls = []
    pin = _pin(wheel, "fonts/a.ttf")
    assert font_files.font_bytes(pin, download=_serving(wheel, calls)) == FONT
    path = font_files.font_path(pin, download=_serving(wheel, calls))
    assert path.read_bytes() == FONT
    assert path.suffix == ".ttf"
    assert path.is_relative_to(data_dir)
    assert len(calls) == 1


def test_a_font_module_is_parsed_and_never_run(data_dir):
    del data_dir
    wheel = _wheel({"pymupdf_fonts/A.py": MODULE})
    pin = _pin(wheel, "pymupdf_fonts/A.py", "pymupdf-fonts-module")
    assert font_files.font_bytes(pin, download=_serving(wheel)) == FONT
    two = _wheel({"pymupdf_fonts/A.py": MODULE + b"other = b'x'\n"})
    with pytest.raises(fonts.FontRefused):
        font_files.font_bytes(
            _pin(two, "pymupdf_fonts/A.py", "pymupdf-fonts-module"),
            download=_serving(two),
        )


def test_a_wheel_or_font_without_its_digest_is_refused(data_dir):
    wheel = _wheel({"fonts/a.ttf": FONT})
    pin = _pin(wheel, "fonts/a.ttf")
    with pytest.raises(fonts.FontRefused):
        font_files.font_bytes(pin, download=_serving(wheel + b"changed"))
    kept = (data_dir / font_files.CACHE_DIRECTORY).iterdir()
    assert not [path for path in kept if not path.name.endswith("-lock")]
    wrong = _pin(wheel, "fonts/a.ttf", member_sha256="0" * 64)
    with pytest.raises(fonts.FontRefused):
        font_files.font_bytes(wrong, download=_serving(wheel))
    missing = _pin(wheel, "fonts/b.ttf")
    with pytest.raises(fonts.FontRefused):
        font_files.font_bytes(missing, download=_serving(wheel))


def test_offline_fetching_raises_os_error(data_dir):
    del data_dir

    def offline(url, path):
        raise OSError("offline")

    pin = _pin(_wheel({"fonts/a.ttf": FONT}), "fonts/a.ttf")
    with pytest.raises(OSError):
        font_files.font_bytes(pin, download=offline)


# -- The pinned fonts themselves ------------------------------------------------


def _pinned(font):
    _skip_without_pillow()
    drawn = None
    try:
        drawn = font_files.pinned_font(font)
    except OSError:
        pytest.skip("the pinned fonts cannot be fetched, such as offline")
    assert drawn is not None
    return drawn


@pytest.mark.parametrize(
    "font", font_files.PINNED_FONTS, ids=[font.name for font in font_files.PINNED_FONTS]
)
def test_each_pinned_font_draws_at_the_cap_height(font):
    drawn = _pinned(font)
    assert drawn.name == font.name
    for height in (8.0, 16.0):
        coverage = drawn.coverage("HHH", height)
        assert _cap_rows(coverage) == pytest.approx(height, abs=2)
    text = drawn.coverage("Smith, J 12/03/1961 (ID #4711)", 12.0)
    assert ((text > 0.05) & (text < 0.95)).any()


def test_drawing_a_pinned_font_offline_skips_cleanly(data_dir, monkeypatch):
    del data_dir
    _skip_without_pillow()

    def offline(url, path):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(font_files, "download_with_progress", offline)
    with pytest.raises(pytest.skip.Exception):
        _pinned(font_files.PINNED_FONTS[0])
