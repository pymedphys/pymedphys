"""Fetch MIDI-B's answer keys from TCIA's own Aspera packages, and list them.

Usage:

- ``python midi_b_tcia_answer_keys.py fetch DEST [--user-agent-note NOTE]``:
  read the public Faspex links on TCIA's MIDI-B page and receive each
  package into ``DEST/<n>`` with IBM's ``ascli``, which must be on the path
  with its transfer daemon installed. A note, such as the runner's address
  and the run, is added to the page request's User-Agent header, so that
  TCIA can find the run's requests in its logs.
- ``python midi_b_tcia_answer_keys.py list DEST``: print each file's
  package, name, size, and SHA-256; for a ZIP file, each member's name,
  size, and SHA-256; and, for an SQLite database, its tables and their row
  counts.
- ``python midi_b_tcia_answer_keys.py network [--github-env FILE]``: print
  the time, in UTC, the runner's public address, as a web service sees it,
  and, for each of TCIA's hosts that the workflow uses, the addresses it
  resolves to and whether a TCP connection to each opens on port 443, and
  how fast. TCIA's site sometimes stops answering a runner, and TCIA can
  match these with its own logs. With ``--github-env``, it also appends
  ``MIDI_B_RUNNER_ADDRESS=<address>`` to that file, GitHub's
  ``GITHUB_ENV``, when the address is known. It never fails.

TCIA publishes MIDI-B's answer keys (https://doi.org/10.7937/cf2p-aw56,
CC BY 4.0) only as Faspex packages. The MIDI-B Benchmark workflow uses this
to check, from the source, that the copy it pins is TCIA's file. The links
are read from the page at run time, so none is stored here, and neither the
links nor ``ascli``'s output are printed: ``ascli``'s output goes to
``DEST/ascli.log``. The listing names no value from the files.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import http.client
import ipaddress
import random
import re
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

PAGE = "https://www.cancerimagingarchive.net/collection/midi-b-test-midi-b-validation/"
USER_AGENT = "pymedphys-midi-b"
# What a note in the User-Agent header may hold: characters that an RFC 9110
# comment allows unquoted.
_AGENT_NOTE = re.compile(r"[A-Za-z0-9 .:;/_=,+-]{1,200}")
_FASPEX = re.compile(r'href="(https://faspex\.cancerimagingarchive\.net/[^"]+)"')
_SAFE_NAME = re.compile(r"[A-Za-z0-9 ._()+-]{1,200}")
_SQLITE = b"SQLite format 3\x00"
CHUNK = 1 << 20
# TCIA's site sometimes stops answering the runners for many minutes: up
# to ten tries over about 40 minutes, 30 s to 5 min apart, with jitter, so
# that the jobs of one run do not ask together.
ATTEMPTS = 10
PAUSE = 30.0
LONGEST_PAUSE = 300.0
HOSTS = (
    "www.cancerimagingarchive.net",
    "services.cancerimagingarchive.net",
    "faspex.cancerimagingarchive.net",
)
PORT = 443
CONNECT_TIMEOUT = 10.0
# Services that answer with the address that a request came from.
ADDRESS_SERVICES = ("https://checkip.amazonaws.com/", "https://api.ipify.org/")


def utc_now() -> str:
    """The time, in UTC, to the second."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def user_agent(note: str | None = None) -> str:
    """The User-Agent header, with ``note`` as a comment if given.

    >>> user_agent("runner 192.0.2.1; run 7/1")
    'pymedphys-midi-b (runner 192.0.2.1; run 7/1)'
    >>> user_agent("a) b")
    Traceback (most recent call last):
    ...
    ValueError: a user agent note may hold only up to 200 letters, digits, spaces, and . : ; / _ = , + -
    """
    if note is None:
        return USER_AGENT
    if not _AGENT_NOTE.fullmatch(note):
        raise ValueError(
            "a user agent note may hold only up to 200 letters, digits, "
            "spaces, and . : ; / _ = , + -"
        )
    return f"{USER_AGENT} ({note})"


def failure(error: BaseException) -> str:
    """Name an error by its type, and by its reason's type for a URL error.

    >>> import urllib.error
    >>> failure(urllib.error.URLError(TimeoutError("timed out")))
    'URLError: TimeoutError'
    >>> failure(ConnectionRefusedError())
    'ConnectionRefusedError'
    """
    reason = getattr(error, "reason", None)
    if isinstance(reason, BaseException):
        return f"{type(error).__name__}: {type(reason).__name__}"
    return type(error).__name__


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


def _page(
    attempts: int = ATTEMPTS, pause: float = PAUSE, agent: str = USER_AGENT
) -> str:
    """Return TCIA's MIDI-B page, trying again after a network error."""
    request = urllib.request.Request(PAGE, headers={"User-Agent": agent})
    for attempt in range(1, attempts + 1):
        try:
            # A constant HTTPS URL.
            with urllib.request.urlopen(request, timeout=60) as response:  # nosec B310
                return response.read().decode("utf-8", "replace")
        except OSError as error:
            if attempt == attempts:
                raise
            wait = min(pause * 2 ** (attempt - 1), LONGEST_PAUSE)
            wait *= random.uniform(0.75, 1.25)  # nosec B311
            print(
                f"Reading TCIA's MIDI-B page: attempt {attempt} of {attempts} "
                f"failed at {utc_now()} ({failure(error)}); trying again in "
                f"{wait:.0f} s.",
                flush=True,
            )
            time.sleep(wait)
    raise AssertionError("unreachable")


def fetch(destination: Path, agent: str = USER_AGENT) -> int:
    """Receive every package that TCIA's MIDI-B page links into ``destination``."""
    links = public_links(_page(agent=agent))
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
            f"Package {index} of {len(links)}: ascli exited with "
            f"{completed.returncode} at {utc_now()}",
            flush=True,
        )
        if completed.returncode:
            return completed.returncode
    return 0


def public_address() -> str | None:
    """The runner's public address, as a web service sees it, if one answers."""
    for url in ADDRESS_SERVICES:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            # Constant HTTPS URLs.
            with urllib.request.urlopen(  # nosec B310
                request, timeout=CONNECT_TIMEOUT
            ) as response:
                # Only an address is printed, never what else a service sends.
                address = str(ipaddress.ip_address(response.read(64).decode().strip()))
            # A scoped IPv6 address, with its "%", is no public address, and
            # could not go in a User-Agent note.
            if "%" in address:
                raise ValueError("a scoped address")
            return address
        except (OSError, ValueError, http.client.HTTPException) as error:
            print(f"{url} gave no address ({failure(error)}).", flush=True)
    return None


def connect(host: str, port: int = PORT) -> list[str]:
    """Each address that ``host`` resolves to, and how a TCP connection fares."""
    try:
        found = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as error:
        return [f"{host} does not resolve ({failure(error)})"]
    lines = []
    tried: set[str] = set()
    for family, kind, protocol, _, address in found:
        if address[0] in tried:
            continue
        tried.add(address[0])
        started = time.monotonic()
        try:
            with socket.socket(family, kind, protocol) as connection:
                connection.settimeout(CONNECT_TIMEOUT)
                connection.connect(address)
            outcome = f"connected in {(time.monotonic() - started) * 1000:.0f} ms"
        except OSError as error:
            outcome = (
                f"no connection after {time.monotonic() - started:.1f} s "
                f"({failure(error)})"
            )
        lines.append(f"{host} at {address[0]} port {port}: {outcome}")
    return lines


def network(github_env: Path | None = None) -> int:
    """Print the runner's public address, and how each of TCIA's hosts answers.

    Given ``github_env``, also append ``MIDI_B_RUNNER_ADDRESS=<address>`` to
    it when the address is known.
    """
    address = public_address()
    print(
        f"At {utc_now()}, this runner's public address is {address or 'unknown'}.",
        flush=True,
    )
    if address is not None and github_env is not None:
        # A checked IP address: a single line, with nothing to escape.
        with github_env.open("a", encoding="utf-8") as file:
            file.write(f"MIDI_B_RUNNER_ADDRESS={address}\n")
    for host in HOSTS:
        for line in connect(host):
            print(line, flush=True)
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


def _shown(parts: tuple[str, ...] | list[str]) -> str:
    if all(_SAFE_NAME.fullmatch(part) for part in parts):
        return "/".join(parts)
    return "<name not shown>"


def _members(path: Path) -> list[str]:
    lines = []
    with zipfile.ZipFile(path) as zipped, tempfile.TemporaryDirectory() as scratch:
        for info in zipped.infolist():
            if info.is_dir():
                continue
            # The member's name is never used as a path.
            extracted = Path(scratch) / "member"
            with zipped.open(info) as member, extracted.open("wb") as file:
                while chunk := member.read(CHUNK):
                    file.write(chunk)
            name = _shown(info.filename.split("/"))
            lines.append(
                f"  member {name} {info.file_size} bytes sha256 {_sha256(extracted)}"
            )
            lines.extend(_tables(extracted))
            extracted.unlink()
    return lines


def listing(destination: Path) -> list[str]:
    """Each received file's package, name, size, and SHA-256, and its members."""
    lines = []
    for path in sorted(destination.rglob("*")):
        if not path.is_file() or path.name == "ascli.log":
            continue
        relative = path.relative_to(destination)
        package = relative.parts[0]
        name = _shown(relative.parts[1:])
        lines.append(
            f"package {package}: {name} {path.stat().st_size} bytes sha256 {_sha256(path)}"
        )
        lines.extend(_tables(path))
        if zipfile.is_zipfile(path):
            lines.extend(_members(path))
    return lines


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="midi_b_tcia_answer_keys.py")
    commands = parser.add_subparsers(dest="command", required=True)
    fetching = commands.add_parser(
        "fetch", help="Receive the packages that TCIA's MIDI-B page links."
    )
    fetching.add_argument("destination", metavar="DEST", type=Path)
    fetching.add_argument(
        "--user-agent-note",
        help="Text to add to the User-Agent header, such as the runner's address.",
    )
    listed = commands.add_parser("list", help="List the files received.")
    listed.add_argument("destination", metavar="DEST", type=Path)
    probing = commands.add_parser(
        "network", help="Print how this runner reaches TCIA's hosts."
    )
    probing.add_argument(
        "--github-env",
        type=Path,
        help="A file to append MIDI_B_RUNNER_ADDRESS=<address> to.",
    )
    arguments = parser.parse_args(argv)
    if arguments.command == "network":
        return network(arguments.github_env)
    if arguments.command == "fetch":
        try:
            agent = user_agent(arguments.user_agent_note)
        except ValueError as error:
            parser.error(str(error))
        return fetch(arguments.destination, agent)
    print("\n".join(listing(arguments.destination)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
