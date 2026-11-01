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

"""The redaction review app's server (D-059), on synthetic images only."""

import contextlib
import dataclasses
import http.client
import io
import json
import re
import threading

from pymedphys._imports import numpy as np
from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import (
    qc_attestation,
    qc_previews,
    redaction_review,
    redaction_review_app,
    redaction_verdicts,
)
from pymedphys._dicom.deidentify.qc_attestation import Coverage, Outcome
from pymedphys._dicom.deidentify.qc_pack import QcPackError
from pymedphys._dicom.deidentify.redaction_review_app import (
    TOKEN_HEADER,
    ReviewServer,
    ReviewSession,
)
from pymedphys._dicom.deidentify.redaction_verdicts import Draft, Verdicts

from ._redaction_review_pack import FALSE_POSITIVE, write_pack

pytestmark = [pytest.mark.pydicom, pytest.mark.usefixtures("pydicom_behaviour")]

COMPLETE = Coverage(retained_strings=True, series=True, high_risk_instances=True)
FP = [
    FALSE_POSITIVE.top,
    FALSE_POSITIVE.left,
    FALSE_POSITIVE.bottom,
    FALSE_POSITIVE.right,
]


@pytest.fixture(name="pack", scope="module")
def fixture_pack(tmp_path_factory):
    return write_pack(tmp_path_factory.mktemp("review"))


@pytest.fixture(name="fresh")
def fixture_fresh(tmp_path):
    """A pack of its own, for a test that changes it."""
    return write_pack(tmp_path)


@contextlib.contextmanager
def _serving(directory):
    server = ReviewServer(ReviewSession(directory))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)


def _request(server, method, path, body=None, *, token=True, host=None, headers=None):
    port = server.server_address[1]
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    sent = {"Host": host or f"127.0.0.1:{port}", **(headers or {})}
    if token:
        sent[TOKEN_HEADER] = server.token if token is True else token
    if body is not None and not isinstance(body, bytes):
        body = json.dumps(body).encode()
        sent.setdefault("Content-Type", "application/json")
    connection.putrequest(method, path, skip_host=True)
    for name, value in sent.items():
        if name != "X-Length":
            connection.putheader(name, value)
    if body is not None:
        connection.putheader(
            "Content-Length", sent.pop("X-Length", None) or str(len(body))
        )
    connection.endheaders(body)
    response = connection.getresponse()
    content = response.read()
    connection.close()
    return response, content


def _draft(redaction=None, drawn=(), dropped=(), seen=()):
    return {
        "redaction": redaction,
        "drawn": list(drawn),
        "dropped": list(dropped),
        "seen": list(seen),
    }


# The session.


def test_the_session_lists_each_cleaned_instance_with_its_proposals(pack):
    directory, positions = pack
    document = ReviewSession(directory).session_document()

    assert document["reference"] == qc_attestation.pack_reference(directory)[0]
    by_position = {entry["position"]: entry for entry in document["instances"]}
    single, multi = (
        by_position[positions["one.dcm"]],
        by_position[positions["three.dcm"]],
    )
    assert (single["frames"], single["rows"], single["columns"]) == (1, 128, 128)
    assert FP in single["proposals"][0]["boxes"]
    assert [entry["frame"] for entry in multi["proposals"]] == [0, 2]
    # Every frame is required, whatever the IOD, until it meets the
    # maintainer's acceptance criteria (D-059).
    assert multi["required"] == [0, 1, 2]
    assert single["rules"] == [] and single["draft"] is None


def test_a_frame_is_the_packs_review_frame_as_raw_samples(pack):
    directory, positions = pack
    session = ReviewSession(directory)
    position = positions["three.dcm"]

    raw, headers = session.frame(position, 1)

    assert headers == {
        "X-Rows": "128",
        "X-Columns": "128",
        "X-Samples": "1",
        "X-Bits": "16",
    }
    name, _ = session.instances[position].review_frames[1]
    expected = qc_previews.decoded_png((directory / name).read_bytes())
    assert np.array_equal(np.frombuffer(raw, "<u2").reshape(128, 128), expected)


def test_a_frame_changed_after_the_pack_was_written_is_refused(fresh):
    directory, positions = fresh
    session = ReviewSession(directory)
    name, _ = session.instances[positions["one.dcm"]].review_frames[0]
    path = directory / name
    path.chmod(0o600)
    path.write_bytes(qc_previews.png(np.zeros((128, 128), np.uint16)))

    with pytest.raises(redaction_review_app.ReviewError, match="changed"):
        session.frame(positions["one.dcm"], 0)


def test_a_frame_that_the_pack_does_not_list_is_refused(pack):
    directory, positions = pack

    with pytest.raises(redaction_review_app.ReviewError, match="no such frame"):
        ReviewSession(directory).frame(positions["one.dcm"], 1)


def test_an_attested_pack_cannot_be_reviewed(fresh):
    directory, _ = fresh
    qc_attestation.attest(
        directory, reviewer="Invented", outcome=Outcome.ATTESTED, coverage=COMPLETE
    )

    with pytest.raises(QcPackError, match="already been attested"):
        ReviewSession(directory)


def test_saved_drafts_for_another_pack_are_refused(fresh):
    directory, _ = fresh
    reference, _ = qc_attestation.pack_reference(directory)
    redaction_verdicts.save_redaction_verdicts(
        directory, Verdicts(reference, "0" * 64, (Draft(0),))
    )

    with pytest.raises(QcPackError, match="for another QC pack"):
        ReviewSession(directory)


def test_saved_drafts_resume(fresh):
    directory, positions = fresh
    position = positions["one.dcm"]
    session = ReviewSession(directory)
    session.save_draft(position, _draft(dropped=[{"frame": 0, "boxes": [FP]}]))

    resumed = ReviewSession(directory).session_document()

    (entry,) = [e for e in resumed["instances"] if e["position"] == position]
    assert entry["draft"] == _draft(dropped=[{"frame": 0, "boxes": [FP]}])


@pytest.mark.parametrize(
    "draft, message",
    [
        (_draft(drawn=[{"frame": 0, "boxes": [[0, 0, 2, 129]]}]), "past its frame"),
        (
            _draft(drawn=[{"frame": 1, "boxes": [[0, 0, 2, 2]]}]),
            "frame that the instance lacks",
        ),
        (
            _draft(dropped=[{"frame": 0, "boxes": [[0, 0, 2, 2]]}]),
            "does not list for its frame",
        ),
        (_draft(seen=[1]), "frame is shown that the instance lacks"),
        (_draft("accepted"), "before every frame"),
        (_draft("revised", seen=[0]), "drops or draws at least one region"),
        (_draft(seen=[0, 0]), "sorted, distinct"),
        ({"redaction": None}, "needs its verdict"),
        (_draft("kept", seen=[0]), "sorted, distinct"),
    ],
)
def test_a_draft_the_pack_would_refuse_is_refused(fresh, draft, message):
    directory, positions = fresh
    session = ReviewSession(directory)

    with pytest.raises(redaction_review_app.ReviewError, match=message):
        session.save_draft(positions["one.dcm"], draft)
    assert not (directory / redaction_verdicts.VERDICTS_FILE).exists()


def test_a_rule_region_cannot_be_dropped(fresh):
    directory, positions = fresh
    session = ReviewSession(directory)
    position = positions["one.dcm"]
    cleaned = session.instances[position]
    session.instances[position] = dataclasses.replace(
        cleaned, rules=frozenset({FALSE_POSITIVE})
    )

    with pytest.raises(redaction_review_app.ReviewError, match="a region rule gave"):
        session.save_draft(position, _draft(dropped=[{"frame": 0, "boxes": [FP]}]))


def test_saved_drafts_give_the_attestation_its_verdicts(fresh):
    directory, positions = fresh
    session = ReviewSession(directory)
    session.save_draft(
        positions["one.dcm"],
        _draft("revised", dropped=[{"frame": 0, "boxes": [FP]}], seen=[0]),
    )
    session.save_draft(positions["three.dcm"], _draft("rejected"))
    reference, digest = qc_attestation.pack_reference(directory)

    verdicts = redaction_verdicts.read_redaction_verdicts(
        directory / redaction_verdicts.VERDICTS_FILE,
        reference=reference,
        pack_digest=digest,
    ).verdicts()
    attestation = qc_attestation.attest(
        directory,
        reviewer="Invented",
        outcome=Outcome.ATTESTED,
        coverage=COMPLETE,
        redactions=verdicts,
    )

    assert [v.redaction.value for v in attestation.redactions] == [
        "revised",
        "rejected",
    ]


# The server.


def test_the_page_is_served_with_its_security_headers(pack):
    directory, _ = pack
    with _serving(directory) as server:
        for path, kind in (
            ("/", "text/html"),
            ("/app.js", "text/javascript"),
            ("/app.css", "text/css"),
        ):
            response, content = _request(server, "GET", path, token=False)
            assert response.status == 200 and content
            assert response.getheader("Content-Type").startswith(kind)
            assert response.getheader("Cache-Control") == "no-store"
            policy = response.getheader("Content-Security-Policy")
            assert "default-src 'none'" in policy and "connect-src 'self'" in policy
            assert response.getheader("X-Frame-Options") == "DENY"


def test_the_page_loads_nothing_from_elsewhere():
    for name in ("index.html", "app.js", "app.css"):
        text = (redaction_review_app._STATIC / name).read_text("utf-8")  # pylint: disable = protected-access
        assert "http://" not in text.replace("http://127.0.0.1", "")
        assert "https://" not in text and "//cdn" not in text
        # Nothing that users see cites a decision of the design by number.
        assert not re.search(r"D-[0-9]{3}", text)


def test_the_server_listens_on_this_computer_only(pack):
    directory, _ = pack
    with _serving(directory) as server:
        assert server.server_address[0] == "127.0.0.1"
        assert server.address.startswith("http://127.0.0.1:")
        assert server.address.endswith("/#" + server.token)


@pytest.mark.parametrize("token", [False, "wrong"])
def test_data_needs_the_token(pack, token):
    directory, positions = pack
    with _serving(directory) as server:
        for path in ("/api/session", f"/api/frames/{positions['one.dcm']}/0"):
            response, content = _request(server, "GET", path, token=token)
            assert response.status == 403
            assert b"token" in content


@pytest.mark.parametrize("host", ["evil.example", "evil.example:{port}", "127.0.0.1:1"])
def test_a_request_for_another_host_is_refused(pack, host):
    directory, _ = pack
    with _serving(directory) as server:
        port = server.server_address[1]
        response, _ = _request(
            server, "GET", "/api/session", host=host.format(port=port)
        )
        assert response.status == 421
        response, _ = _request(
            server, "GET", "/", token=False, host=host.format(port=port)
        )
        assert response.status == 421


def test_localhost_at_the_port_is_answered(pack):
    directory, _ = pack
    with _serving(directory) as server:
        port = server.server_address[1]
        response, _ = _request(server, "GET", "/api/session", host=f"localhost:{port}")
        assert response.status == 200


def test_the_session_and_a_frame_are_served(pack):
    directory, positions = pack
    with _serving(directory) as server:
        response, content = _request(server, "GET", "/api/session")
        assert response.status == 200
        assert json.loads(content)["reference"].startswith("A-")
        response, content = _request(
            server, "GET", f"/api/frames/{positions['one.dcm']}/0"
        )
        assert response.status == 200
        assert response.getheader("Content-Type") == "application/octet-stream"
        assert len(content) == 128 * 128 * 2
        response, _ = _request(server, "GET", f"/api/frames/{positions['one.dcm']}/7")
        assert response.status == 404


def test_a_draft_is_saved_through_the_server(fresh):
    directory, positions = fresh
    position = positions["three.dcm"]
    draft = _draft(drawn=[{"frame": 1, "boxes": [[108, 2, 120, 34]]}], seen=[0, 1])
    with _serving(directory) as server:
        response, content = _request(server, "PUT", f"/api/drafts/{position}", draft)
        assert response.status == 200, content
        assert json.loads(content) == draft
        # Accepting before the last frame was shown is refused.
        response, content = _request(
            server, "PUT", f"/api/drafts/{position}", {**draft, "redaction": "revised"}
        )
        assert response.status == 400
        assert b"before every frame" in content
    saved = json.loads(
        (directory / redaction_verdicts.VERDICTS_FILE).read_text("ascii")
    )
    assert saved["drafts"][0]["redaction"] is None


@pytest.mark.parametrize(
    "body, headers, status",
    [
        (b"not json", {"Content-Type": "application/json"}, 400),
        (b"{}", {"Content-Type": "text/plain"}, 415),
        (b"", {"Content-Type": "application/json"}, 413),
        # Refused by its length alone, before any of it is read.
        (b"{}", {"Content-Type": "application/json", "X-Length": "4194305"}, 413),
    ],
    ids=["not-json", "not-declared-json", "empty", "too-large"],
)
def test_a_malformed_draft_request_is_refused(fresh, body, headers, status):
    directory, positions = fresh
    with _serving(directory) as server:
        response, _ = _request(
            server, "PUT", f"/api/drafts/{positions['one.dcm']}", body, headers=headers
        )
        assert response.status == status
    assert not (directory / redaction_verdicts.VERDICTS_FILE).exists()


@pytest.mark.parametrize("method", ["POST", "DELETE", "PATCH", "OPTIONS"])
def test_other_methods_are_refused(pack, method):
    directory, _ = pack
    with _serving(directory) as server:
        response, _ = _request(server, method, "/api/session")
        assert response.status == 405
        assert response.getheader("Access-Control-Allow-Origin") is None


# The command.


def test_the_command_does_not_start_without_a_pack(tmp_path):
    stdout, stderr = io.StringIO(), io.StringIO()

    status = redaction_review_app.main(
        [str(tmp_path / "secret-name"), "--no-browser"], stdout=stdout, stderr=stderr
    )

    assert status == redaction_review_app.EXIT_NOT_STARTED
    assert "holds no QC pack" in stderr.getvalue()
    assert "secret-name" not in stdout.getvalue() + stderr.getvalue()


def test_the_command_serves_until_stopped(pack, monkeypatch):
    directory, _ = pack
    stdout = io.StringIO()

    def stop(self):  # pylint: disable = unused-argument
        raise KeyboardInterrupt

    monkeypatch.setattr(ReviewServer, "serve_forever", stop)
    status = redaction_review_app.main([str(directory), "--no-browser"], stdout=stdout)

    assert status == redaction_review_app.EXIT_STOPPED
    lines = stdout.getvalue().splitlines()
    assert lines[0].endswith("2 cleaned instance(s) to review")
    assert lines[1].startswith("open http://127.0.0.1:")
    assert str(directory) not in stdout.getvalue()


# Flagged-only review, for an IOD whose text finder met the criteria (D-059).

CT_IMAGE = "1.2.840.10008.5.1.4.1.1.2"


def test_no_iod_needs_only_its_flagged_frames_shown_yet():
    assert not qc_attestation.FLAGGED_ONLY_SOP_CLASSES


def test_an_unlocked_iod_needs_only_its_flagged_frames_shown(fresh, monkeypatch):
    directory, positions = fresh
    monkeypatch.setattr(
        qc_attestation, "FLAGGED_ONLY_SOP_CLASSES", frozenset({CT_IMAGE})
    )
    session = ReviewSession(directory)
    position = positions["three.dcm"]
    assert session.instances[position].required == (0, 2)

    # The frame without a proposal, frame 1, is never shown.
    session.save_draft(position, _draft("accepted", seen=[0, 2]))
    session.save_draft(
        positions["one.dcm"],
        _draft("revised", dropped=[{"frame": 0, "boxes": [FP]}], seen=[0]),
    )
    reference, digest = qc_attestation.pack_reference(directory)
    verdicts = redaction_verdicts.read_redaction_verdicts(
        directory / redaction_verdicts.VERDICTS_FILE,
        reference=reference,
        pack_digest=digest,
    ).verdicts()
    qc_attestation.attest(
        directory,
        reviewer="Invented",
        outcome=Outcome.ATTESTED,
        coverage=COMPLETE,
        redactions=verdicts,
    )

    review = redaction_review.read_redaction_review(directory)
    assert review.not_shown == 1


def test_an_unlocked_iod_still_needs_each_flagged_frame_shown(fresh, monkeypatch):
    directory, positions = fresh
    monkeypatch.setattr(
        qc_attestation, "FLAGGED_ONLY_SOP_CLASSES", frozenset({CT_IMAGE})
    )

    with pytest.raises(redaction_review_app.ReviewError, match="before every frame"):
        ReviewSession(directory).save_draft(
            positions["three.dcm"], _draft("accepted", seen=[0])
        )


def test_another_iod_stays_needing_every_frame_shown(fresh, monkeypatch):
    directory, positions = fresh
    monkeypatch.setattr(
        qc_attestation,
        "FLAGGED_ONLY_SOP_CLASSES",
        frozenset({"1.2.840.10008.5.1.4.1.1.4"}),
    )

    assert ReviewSession(directory).instances[positions["three.dcm"]].required == (
        0,
        1,
        2,
    )
    with pytest.raises(QcPackError, match="was not shown 1 frame"):
        qc_attestation.attest(
            directory,
            reviewer="Invented",
            outcome=Outcome.ATTESTED,
            coverage=COMPLETE,
            redactions=[
                qc_attestation.RedactionVerdict(
                    positions["three.dcm"],
                    qc_attestation.Redaction.ACCEPTED,
                    seen=(0, 2),
                )
            ],
        )
