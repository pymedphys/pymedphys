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

"""The redaction review app, for the Clean Pixel Data Option (D-059).

Run as ``python -m pymedphys._dicom.deidentify.redaction_review_app PACK``,
where ``PACK`` is the directory of a first run's QC pack under the option
that has not been attested. The command starts a web server on this
computer, prints its address, and opens it in the browser; the reviewer
works through each cleaned instance there, and stops the server with
Ctrl+C. It is not registered with the ``pymedphys`` command: nothing
de-identification related joins the public command line before the first
supported release.

In the page, the text finder's regions are proposals, outlined over the
frame as received: the reviewer keeps or drops each, draws a region of their
own over text that the finder missed, and sees the frame as the run given
their verdict would write it. A region that a reviewed region rule gave is
shown, and cannot be dropped (D-037). Every region is drawn on the
full-resolution frame, so none can be given for another frame or with its
coordinates transposed (D-048). An instance can be accepted or revised only
once the reviewer has been shown every frame that its review requires; it
can be rejected at any time. The work is saved to the pack's directory as
it is done (:mod:`~pymedphys._dicom.deidentify.redaction_verdicts`), so a
review can stop and resume, and the attestation command reads it with
``--redaction-verdicts``, which records the verdicts with the rest of the
attestation, once.

The pages show patient pixel data, so the app is local and closed:

- the server listens on 127.0.0.1 only, on a free port, and answers only a
  request whose Host is that address or ``localhost`` at that port, so that
  a web page that rebinds a name of its own to this computer reaches
  nothing;
- every request for data, and every change, must carry the random token
  that the printed address holds after its ``#``, which the browser never
  sends to a server, in a header that no other site's page can send here
  without a preflight that the server never grants;
- the page and its script and style come from the package, with no
  third-party code, font, or service, and a Content Security Policy that
  lets the page reach this server alone;
- no response may be cached, and each frame is checked against the SHA-256
  that the pack records for it before it is sent, so the reviewer sees only
  the pack's own bytes, which the attestation binds.

Neither the server nor its messages name the pack's path, a source path, or
any value.

Exit statuses:

- :data:`EXIT_STOPPED`, 0: the server was stopped;
- :data:`EXIT_NOT_STARTED`, 1: the pack cannot be reviewed;
- :data:`EXIT_USAGE`, 2: the arguments could not be parsed.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import hmac
import http.server
import json
import re
import secrets
import sys
import threading
import typing
import webbrowser
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TextIO

from pymedphys._imports import numpy as np

from . import command, qc_pack, redaction_verdicts
from .command import _Parser, _print
from .qc_attestation import (
    Redaction,
    pack_proposals,
    previewed_redactions,
    ReviewMode,
    required_frames,
    review_mode,
    unattested_pack,
)
from .qc_pack import QcPackError
from .qc_previews import decoded_png
from .redaction_verdicts import Draft, Verdicts
from .text_detection import TextBox

EXIT_STOPPED = 0
EXIT_NOT_STARTED = 1
EXIT_USAGE = command.EXIT_USAGE

TOKEN_HEADER = "X-Review-Token"
_STATIC = Path(__file__).with_name("redaction_review_static")
_STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/app.css": ("app.css", "text/css; charset=utf-8"),
}
_SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'none'; script-src 'self'; style-src 'self'; "
        "img-src 'self' blob:; connect-src 'self'; base-uri 'none'; "
        "form-action 'none'; frame-ancestors 'none'"
    ),
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Cross-Origin-Opener-Policy": "same-origin",
    "X-Frame-Options": "DENY",
}
_FRAME_PATH = re.compile(r"/api/frames/([0-9]{1,9})/([0-9]{1,9})")
_DRAFT_PATH = re.compile(r"/api/drafts/([0-9]{1,9})")
# The most bytes of a request's body that are read.
_MOST_BODY_BYTES = 4 * 1024 * 1024


class ReviewError(Exception):
    """A request that the review refuses; its message names no value."""


@dataclasses.dataclass(frozen=True)
class Cleaned:
    """A cleaned instance that the pack previewed, as the app shows it.

    Attributes
    ----------
    position : int
    frames, rows, columns : int
    reason : str
        Why the run held it, as the pack words it.
    proposals : mapping of int to tuple of TextBox
        The pack's regions of each frame with any, rules' among them.
    rules : frozenset of TextBox
        The regions that region rules gave, which cannot be dropped.
    required : tuple of int
        The frames that the reviewer must be shown to accept or revise it.
    mode : ReviewMode
        Whether its review requires every frame or only the flagged ones.
    review_frames : mapping of int to tuple of (str, str)
        Each frame's review frame, as its file within the pack's directory
        and its SHA-256.
    """

    position: int
    frames: int
    rows: int
    columns: int
    reason: str
    proposals: Mapping[int, tuple[TextBox, ...]]
    rules: frozenset[TextBox]
    required: tuple[int, ...]
    mode: ReviewMode
    review_frames: Mapping[int, tuple[str, str]]


class ReviewSession:
    """A reviewer's work on one QC pack: what it shows, and their drafts.

    Parameters
    ----------
    pack_directory : path-like

    Raises
    ------
    QcPackError
        If the pack cannot be reviewed: it is missing, not of its format,
        changed, or attested, or its saved drafts are for another pack or
        not of their format.
    """

    def __init__(self, pack_directory) -> None:
        self.directory = Path(pack_directory)
        data = unattested_pack(self.directory)
        document = json.loads(data.decode("ascii"))
        self.reference: str = document["reference"]
        self.pack_digest = hashlib.sha256(data).hexdigest()
        self.instances = _cleaned(document, data)
        self._lock = threading.Lock()
        path = self.directory / redaction_verdicts.VERDICTS_FILE
        if path.exists():
            saved = redaction_verdicts.read_redaction_verdicts(
                path, reference=self.reference, pack_digest=self.pack_digest
            )
            unknown = [
                d.position for d in saved.drafts if d.position not in self.instances
            ]
            if unknown:
                raise QcPackError(
                    "the saved redaction verdicts name an instance that the QC "
                    "pack does not list as cleaned and previewed"
                )
            self._drafts = {draft.position: draft for draft in saved.drafts}
        else:
            self._drafts = {}

    def session_document(self) -> dict:
        """Return what the page needs to show the pack: each cleaned instance,
        with its proposals and the frames its review requires, and the
        drafts saved so far."""
        with self._lock:
            drafts = dict(self._drafts)
        return {
            "reference": self.reference,
            "instances": [
                {
                    "position": cleaned.position,
                    "frames": cleaned.frames,
                    "rows": cleaned.rows,
                    "columns": cleaned.columns,
                    "reason": cleaned.reason,
                    "proposals": [
                        {"frame": index, "boxes": _boxes(boxes)}
                        for index, boxes in sorted(cleaned.proposals.items())
                    ],
                    "rules": _boxes(sorted(cleaned.rules)),
                    "required": list(cleaned.required),
                    "mode": cleaned.mode.value,
                    "draft": _draft_document(drafts.get(cleaned.position)),
                }
                for cleaned in self.instances.values()
            ],
        }

    def frame(self, position: int, index: int) -> tuple[bytes, dict[str, str]]:
        """Return a frame's review frame as raw samples, with headers that
        give its shape: 16-bit grey little endian, or 8-bit RGB interleaved.

        Raises
        ------
        ReviewError
            If the pack lists no such frame, or its file is missing or no
            longer has the SHA-256 that the pack records.
        """
        cleaned = self.instances.get(position)
        if cleaned is None or index not in cleaned.review_frames:
            raise ReviewError("the QC pack lists no such frame")
        name, digest = cleaned.review_frames[index]
        try:
            content = (self.directory / name).read_bytes()
        except OSError:
            raise ReviewError("a review frame could not be read") from None
        if not hmac.compare_digest(hashlib.sha256(content).hexdigest(), digest):
            raise ReviewError("a review frame changed after the QC pack was written")
        try:
            image = decoded_png(content)
        except ValueError:
            raise ReviewError("a review frame could not be read") from None
        if image.shape[:2] != (cleaned.rows, cleaned.columns):
            raise ReviewError("a review frame is not of its instance's size")
        samples = 3 if image.ndim == 3 else 1
        raw = (
            image.astype("<u2").tobytes()
            if image.dtype == np.uint16
            else image.tobytes()
        )
        return raw, {
            "X-Rows": str(cleaned.rows),
            "X-Columns": str(cleaned.columns),
            "X-Samples": str(samples),
            "X-Bits": "16" if image.dtype == np.uint16 else "8",
        }

    def save_draft(self, position: int, document: object) -> dict:
        """Check a draft of one instance against the pack, and save every
        draft.

        Raises
        ------
        ReviewError
            If the draft is not of its form, or the pack would refuse it:
            a region drawn past the frame or in a frame that the instance
            does not hold, a region dropped that the pack does not list for
            its frame or that a rule gave, a frame shown that it does not
            hold, or an acceptance or revision before every frame that its
            review requires was shown.
        """
        cleaned = self.instances.get(position)
        if cleaned is None:
            raise ReviewError("the QC pack does not list the instance as cleaned")
        draft = _draft_from(position, document)
        _check_draft(cleaned, draft)
        with self._lock:
            drafts = {**self._drafts, position: draft}
            redaction_verdicts.save_redaction_verdicts(
                self.directory,
                Verdicts(
                    self.reference,
                    self.pack_digest,
                    tuple(drafts[key] for key in sorted(drafts)),
                ),
            )
            self._drafts = drafts
        return _draft_document(draft)


def _cleaned(document: dict, data: bytes) -> dict[int, Cleaned]:
    shapes = previewed_redactions(data)
    proposals = pack_proposals(data)
    reasons = {entry["position"]: entry["reason"] for entry in document["redactions"]}
    frames: dict[int, dict[int, tuple[str, str]]] = {}
    for preview in document["previews"]:
        if preview.get("kind") != qc_pack.PreviewKind.REVIEW_FRAME.value:
            continue
        (shown,) = preview["frames"]  # the pack checks it lists one frame
        frames.setdefault(shown["position"], {})[shown["frame"]] = (
            preview["file"],
            preview["sha256"],
        )
    cleaned = {}
    for position in sorted(shapes):
        shape = shapes[position]
        listed, ruled = proposals[position]
        cleaned[position] = Cleaned(
            position,
            shape.frames,
            shape.rows,
            shape.columns,
            reasons[position],
            listed,
            ruled,
            required_frames(shape, listed),
            review_mode(shape),
            frames.get(position, {}),
        )
    return cleaned


def _boxes(boxes) -> list[list[int]]:
    return [[box.top, box.left, box.bottom, box.right] for box in boxes]


def _draft_document(draft: Draft | None) -> dict | None:
    if draft is None:
        return None
    return {
        "redaction": None if draft.redaction is None else draft.redaction.value,
        "drawn": [
            {"frame": index, "boxes": _boxes(boxes)} for index, boxes in draft.drawn
        ],
        "dropped": [
            {"frame": index, "boxes": _boxes(boxes)} for index, boxes in draft.dropped
        ],
        "seen": list(draft.seen),
    }


def _draft_from(position: int, document: object) -> Draft:
    if not isinstance(document, dict) or set(document) != {
        "redaction",
        "drawn",
        "dropped",
        "seen",
    }:
        raise ReviewError("a draft needs its verdict, regions, and frames shown")
    try:
        return redaction_verdicts.verdicts_from(
            {
                "format": redaction_verdicts.FORMAT,
                "reference": "A-" + "0" * 32,
                "pack_digest": "0" * 64,
                "drafts": [{"position": position, **document}],
            }
        ).drafts[0]
    except QcPackError:
        raise ReviewError(
            "a draft's regions are frames, each once and in order, with sorted, "
            "distinct boxes, and its frames shown are sorted, distinct indices"
        ) from None


def _check_draft(cleaned: Cleaned, draft: Draft) -> None:
    for index, boxes in draft.drawn:
        if index >= cleaned.frames:
            raise ReviewError("a region is drawn in a frame that the instance lacks")
        if any(
            box.bottom > cleaned.rows or box.right > cleaned.columns for box in boxes
        ):
            raise ReviewError("a region is drawn past its frame")
    for index, boxes in draft.dropped:
        if not set(boxes) <= set(cleaned.proposals.get(index, ())) - cleaned.rules:
            raise ReviewError(
                "a region is dropped that the QC pack does not list for its "
                "frame, or that a region rule gave"
            )
    if any(index >= cleaned.frames for index in draft.seen):
        raise ReviewError("a frame is shown that the instance lacks")
    if draft.redaction in (Redaction.ACCEPTED, Redaction.REVISED) and not set(
        cleaned.required
    ) <= set(draft.seen):
        raise ReviewError(
            "the instance cannot be accepted or revised before every frame that "
            "its review requires was shown"
        )
    try:
        draft.verdict()
    except QcPackError:
        raise ReviewError(
            "a revised instance drops or draws at least one region"
        ) from None


class _Refused(Exception):
    """A request refused with an HTTP status and a message."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


class _Handler(http.server.BaseHTTPRequestHandler):
    """Serves one review session; see the module for what it allows."""

    protocol_version = "HTTP/1.1"
    server_version = "pymedphys-redaction-review"
    sys_version = ""

    def log_message(self, format, *args) -> None:  # pylint: disable = redefined-builtin
        # Request lines hold only fixed paths and run positions, but nothing
        # is logged, so that nothing reaches a terminal that is recorded.
        pass

    def do_GET(self) -> None:  # pylint: disable = invalid-name
        if not self._host_allowed():
            return
        path = self.path.split("?", 1)[0]
        if path in _STATIC_FILES:
            name, content_type = _STATIC_FILES[path]
            self._send(200, (_STATIC / name).read_bytes(), content_type)
            return
        if not self._token_allowed():
            return
        session = self._review.session
        if path == "/api/session":
            self._json(200, session.session_document())
            return
        found = _FRAME_PATH.fullmatch(path)
        if found:
            try:
                raw, headers = session.frame(int(found[1]), int(found[2]))
            except ReviewError as error:
                self._json(404, {"error": str(error)})
                return
            self._send(200, raw, "application/octet-stream", headers)
            return
        self._json(404, {"error": "no such resource"})

    def do_PUT(self) -> None:  # pylint: disable = invalid-name
        if not self._host_allowed() or not self._token_allowed():
            return
        found = _DRAFT_PATH.fullmatch(self.path)
        if not found:
            self._refuse(404, "no such resource")
            return
        try:
            document = self._json_body()
            saved = self._review.session.save_draft(int(found[1]), document)
        except _Refused as refused:
            self._refuse(refused.status, refused.message)
            return
        except (ReviewError, QcPackError) as error:
            self._refuse(400, str(error))
            return
        self._json(200, saved)

    def _json_body(self) -> object:
        """Read a request's body as JSON, refusing one not declared as JSON,
        without its length, empty, or too large, before reading it."""
        if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            raise _Refused(415, "a draft is sent as JSON")
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            raise _Refused(411, "a draft needs its length") from None
        if not 0 < length <= _MOST_BODY_BYTES:
            raise _Refused(413, "a draft is empty or too large")
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except ValueError:
            raise _Refused(400, "a draft is sent as JSON") from None

    @property
    def _review(self) -> "ReviewServer":
        return typing.cast("ReviewServer", self.server)

    def _refuse(self, status: int, message: str) -> None:
        self._json(status, {"error": message})

    def do_POST(self) -> None:  # pylint: disable = invalid-name
        self._refuse(405, "not allowed")

    do_DELETE = do_PATCH = do_OPTIONS = do_POST

    def _host_allowed(self) -> bool:
        port = self.server.server_address[1]
        if self.headers.get("Host") in (f"127.0.0.1:{port}", f"localhost:{port}"):
            return True
        self._refuse(421, "this server answers only its own address")
        return False

    def _token_allowed(self) -> bool:
        given = self.headers.get(TOKEN_HEADER, "")
        if hmac.compare_digest(given.encode(), self._review.token.encode()):
            return True
        self._refuse(403, "the review token is missing or wrong")
        return False

    def _json(self, status: int, document: object) -> None:
        self._send(status, json.dumps(document).encode("utf-8"), "application/json")

    def _send(
        self,
        status: int,
        body: bytes,
        content_type: str,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        if status >= 400:
            # A refused request's body may not have been read, so the
            # connection is not reused.
            self.close_connection = True
            self.send_header("Connection", "close")
        for name, value in {**_SECURITY_HEADERS, **(headers or {})}.items():
            self.send_header(name, value)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class ReviewServer(http.server.ThreadingHTTPServer):
    """The app's server, on 127.0.0.1, for one session and one token."""

    daemon_threads = True

    def __init__(self, session: ReviewSession, port: int = 0) -> None:
        super().__init__(("127.0.0.1", port), _Handler)
        self.session = session
        self.token = secrets.token_urlsafe(32)

    @property
    def address(self) -> str:
        """The page's address, with the token after the ``#``."""
        return f"http://127.0.0.1:{self.server_address[1]}/#{self.token}"


def build_parser(*, stderr: TextIO | None = None) -> argparse.ArgumentParser:
    """Return the parser of the command's arguments."""
    parser = _Parser(
        prog="python -m pymedphys._dicom.deidentify.redaction_review_app",
        stderr=stderr,
        description=(
            "Review the regions that Clean Pixel Data proposed in a QC pack, "
            "in the browser on this computer. For use before the first "
            "supported release."
        ),
    )
    parser.add_argument(
        "pack", metavar="PACK", help="the directory that holds the run's QC pack"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="the port on 127.0.0.1 to listen on; by default a free one",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="print the address without opening it in the browser",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Start the server, open the page, and serve until stopped."""
    stdout = sys.stdout if stdout is None else stdout
    stderr = sys.stderr if stderr is None else stderr
    arguments = build_parser(stderr=stderr).parse_args(argv)
    try:
        session = ReviewSession(arguments.pack)
    except QcPackError as error:
        _print(f"error: {error}; the review was not started", stderr)
        return EXIT_NOT_STARTED
    try:
        server = ReviewServer(session, arguments.port)
    except OSError:
        _print(
            "error: the port could not be opened; the review was not started", stderr
        )
        return EXIT_NOT_STARTED
    with server:
        _print(
            f"QC pack {session.reference}: {len(session.instances)} cleaned "
            "instance(s) to review",
            stdout,
        )
        _print(f"open {server.address}", stdout)
        _print("work is saved as you go; press Ctrl+C to stop", stdout)
        if not arguments.no_browser:
            webbrowser.open(server.address)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
    return EXIT_STOPPED


if __name__ == "__main__":
    sys.exit(main())
