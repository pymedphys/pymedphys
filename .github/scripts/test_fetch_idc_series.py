"""Reject object-name collisions before downloading an IDC DICOM series."""

import importlib.util
import urllib.parse
from pathlib import Path

import pytest


_SPEC = importlib.util.spec_from_file_location(
    "fetch_idc_series_under_test", Path(__file__).with_name("fetch_idc_series.py")
)
assert _SPEC is not None and _SPEC.loader is not None
IDCMODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(IDCMODULE)

UUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


@pytest.mark.parametrize(
    ("object_names", "message"),
    [
        ([f"{UUID}/one/CT.dcm", f"{UUID}/two/CT.dcm"], "Colliding"),
        ([f"{UUID}/CT.dcm", f"{UUID}/ct.DCM"], "Colliding"),
        ([f"{UUID}/CT.dcm", "other-prefix/OTHER.dcm"], "Unexpected"),
        ([f"{UUID}/.hidden"], "Unexpected"),
    ],
)
def test_rejects_unsafe_listing_before_any_download(
    tmp_path, monkeypatch, object_names, message
):
    monkeypatch.setattr(IDCMODULE, "keys", lambda _uuid: object_names)

    def never_download(_url):
        pytest.fail("invalid series listing must not trigger file downloads")

    monkeypatch.setattr(IDCMODULE, "_get", never_download)
    with pytest.raises(SystemExit, match=message):
        IDCMODULE.fetch(UUID, tmp_path)
    assert not list((tmp_path / UUID).iterdir())


def test_distinct_object_names_are_downloaded(tmp_path, monkeypatch):
    objects = [f"{UUID}/first.dcm", f"{UUID}/second.dcm"]
    monkeypatch.setattr(IDCMODULE, "keys", lambda _uuid: objects)
    monkeypatch.setattr(IDCMODULE, "_get", lambda url: url.encode("ascii"))

    assert IDCMODULE.fetch(UUID, tmp_path) == 2
    assert (tmp_path / UUID / "first.dcm").is_file()
    assert (tmp_path / UUID / "second.dcm").is_file()


@pytest.mark.parametrize(
    ("second_name", "collision"), [("ct.DCM", True), ("MR.dcm", False)]
)
def test_paginated_listing_is_preflighted_before_download(
    tmp_path, monkeypatch, second_name, collision
):
    token = "next+/="
    listings = []
    downloads = []

    def fake_get(url):
        parsed = urllib.parse.urlsplit(url)
        if parsed.query:
            query = urllib.parse.parse_qs(parsed.query)
            listings.append(query)
            assert query["prefix"] == [f"{UUID}/"]
            if len(listings) == 1:
                assert "continuation-token" not in query
                return (
                    '<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
                    f"<Contents><Key>{UUID}/one/CT.dcm</Key></Contents>"
                    "<IsTruncated>true</IsTruncated>"
                    f"<NextContinuationToken>{token}</NextContinuationToken>"
                    "</ListBucketResult>"
                ).encode()
            assert query["continuation-token"] == [token]
            return (
                '<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
                f"<Contents><Key>{UUID}/two/{second_name}</Key></Contents>"
                "<IsTruncated>false</IsTruncated></ListBucketResult>"
            ).encode()

        assert len(listings) == 2
        downloads.append(urllib.parse.unquote(parsed.path))
        return b"object"

    monkeypatch.setattr(IDCMODULE, "_get", fake_get)

    if collision:
        with pytest.raises(SystemExit, match="Colliding"):
            IDCMODULE.fetch(UUID, tmp_path)
        assert downloads == []
        assert not list((tmp_path / UUID).iterdir())
    else:
        assert IDCMODULE.fetch(UUID, tmp_path) == 2
        assert set(downloads) == {
            f"/{UUID}/one/CT.dcm",
            f"/{UUID}/two/{second_name}",
        }
        assert sorted(path.name for path in (tmp_path / UUID).iterdir()) == sorted(
            ["CT.dcm", second_name]
        )

    assert len(listings) == 2
