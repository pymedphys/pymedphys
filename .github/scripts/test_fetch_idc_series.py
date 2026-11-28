"""Reject object-name collisions before downloading an IDC DICOM series."""

import importlib.util
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


def _s3_page(*, keys, truncated, token=None):
    namespace = "http://s3.amazonaws.com/doc/2006-03-01/"
    listed = "".join(f"<Contents><Key>{key}</Key></Contents>" for key in keys)
    continuation = (
        f"<NextContinuationToken>{token}</NextContinuationToken>"
        if token is not None
        else ""
    )
    return (
        f'<ListBucketResult xmlns="{namespace}">'
        f"{listed}<IsTruncated>{str(truncated).lower()}</IsTruncated>"
        f"{continuation}</ListBucketResult>"
    ).encode()


def test_repeated_s3_continuation_token_is_rejected(monkeypatch):
    page = _s3_page(keys=[f"{UUID}/one.dcm"], truncated=True, token="stuck")
    monkeypatch.setattr(IDCMODULE, "_get", lambda *_args, **_kwargs: page)
    with pytest.raises(ValueError, match="repeated a continuation token"):
        IDCMODULE.keys(UUID)


def test_truncated_s3_listing_without_token_is_rejected(monkeypatch):
    page = _s3_page(keys=[f"{UUID}/one.dcm"], truncated=True)
    monkeypatch.setattr(IDCMODULE, "_get", lambda *_args, **_kwargs: page)
    with pytest.raises(ValueError, match="no continuation token"):
        IDCMODULE.keys(UUID)


def test_s3_pagination_still_returns_all_objects(monkeypatch):
    pages = iter(
        [
            _s3_page(keys=[f"{UUID}/one.dcm"], truncated=True, token="next"),
            _s3_page(keys=[f"{UUID}/two.dcm"], truncated=False),
        ]
    )
    monkeypatch.setattr(IDCMODULE, "_get", lambda *_args, **_kwargs: next(pages))
    assert IDCMODULE.keys(UUID) == [f"{UUID}/one.dcm", f"{UUID}/two.dcm"]
