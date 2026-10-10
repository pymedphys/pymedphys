"""Fetch MIDI-B's answer keys from TCIA's own Aspera packages, and list them.

Usage:

- ``python midi_b_tcia_answer_keys.py fetch DEST``: read the public Faspex
  links on TCIA's MIDI-B page and receive each package into ``DEST/<n>``
  with IBM's ``ascli``, which must be on the path with its transfer daemon
  installed.
- ``python midi_b_tcia_answer_keys.py list DEST``: print each file's
  package, name, size, and SHA-256, and, for an SQLite file, its tables and
  their row counts.

TCIA publishes MIDI-B's answer keys (https://doi.org/10.7937/cf2p-aw56,
CC BY 4.0) only as Faspex packages. The MIDI-B Benchmark workflow uses this
to check, from the source, that the copy it pins is TCIA's file. The links
are read from the page at run time, so none is stored here, and neither the
links nor ``ascli``'s output are printed: ``ascli``'s output goes to
``DEST/ascli.log``. The listing names no value from the files.
"""

from __future__ import annotations

import hashlib
import html
import re
import sqlite3
import subprocess
import sys
import urllib.request
from pathlib import Path

PAGE = "https://www.cancerimagingarchive.net/collection/midi-b-test-midi-b-validation/"
_FASPEX = re.compile(r'href="(https://faspex\.cancerimagingarchive\.net/[^"]+)"')
_SAFE_NAME = re.compile(r"[A-Za-z0-9 ._()+-]{1,200}")
_SQLITE = b"SQLite format 3\x00"
CHUNK = 1 << 20


def public_links(page: str) -> list[str]:
    """The distinct Faspex package links on the page, in order.

    >>> public_links('<a href="https://faspex.cancerimagingarchive.net/p?context=a&amp;x=1">')
    ['https://faspex.cancerimagingarchive.net/p?context=a&x=1']
    """
    links: list[str] = []
    for match in _FASPEX.findall(page):
        link = html.unescape(match)
        if link not in links:
            links.append(link)
    return links


def fetch(destination: Path) -> int:
    """Receive every package that TCIA's MIDI-B page links into ``destination``."""
    request = urllib.request.Request(PAGE, headers={"User-Agent": "pymedphys-midi-b"})
    # A constant HTTPS URL.
    with urllib.request.urlopen(request, timeout=120) as response:  # nosec B310
        links = public_links(response.read().decode("utf-8", "replace"))
    if not links:
        print("TCIA's MIDI-B page links no Faspex package.")
        return 1
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    log = destination / "ascli.log"
    for index, link in enumerate(links, start=1):
        folder = destination / f"{index}"
        folder.mkdir(mode=0o700)
        with log.open("a", encoding="utf-8") as output:
            completed = subprocess.run(
                [
                    "ascli",
                    "faspex5",
                    "packages",
                    "receive",
                    f"--url={link}",
                    f"--to-folder={folder}",
                    "--format=json",
                ],
                stdout=output,
                stderr=subprocess.STDOUT,
                check=False,
            )
        print(
            f"Package {index} of {len(links)}: ascli exited with {completed.returncode}"
        )
        if completed.returncode:
            return completed.returncode
    return 0


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while chunk := file.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _tables(path: Path) -> list[str]:
    with path.open("rb") as file:
        if file.read(len(_SQLITE)) != _SQLITE:
            return []
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        names = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
            )
        ]
        lines = []
        for name in names:
            # The name comes from the file's own schema, quoted as an identifier.
            quoted = '"' + name.replace('"', '""') + '"'
            (count,) = connection.execute(f"SELECT COUNT(*) FROM {quoted}").fetchone()  # nosec B608
            shown = name if _SAFE_NAME.fullmatch(name) else "<table name not shown>"
            lines.append(f"    table {shown}: {count} rows")
        return lines
    finally:
        connection.close()


def listing(destination: Path) -> list[str]:
    """Each received file's package, name, size, and SHA-256."""
    lines = []
    for path in sorted(destination.rglob("*")):
        if not path.is_file() or path.name == "ascli.log":
            continue
        relative = path.relative_to(destination)
        package = relative.parts[0]
        name = "/".join(relative.parts[1:])
        if not all(_SAFE_NAME.fullmatch(part) for part in relative.parts[1:]):
            name = "<name not shown>"
        lines.append(
            f"package {package}: {name} {path.stat().st_size} bytes sha256 {_sha256(path)}"
        )
        lines.extend(_tables(path))
    return lines


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[0] not in {"fetch", "list"}:
        print("usage: midi_b_tcia_answer_keys.py {fetch,list} DEST")
        return 2
    destination = Path(argv[1])
    if argv[0] == "fetch":
        return fetch(destination)
    print("\n".join(listing(destination)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
