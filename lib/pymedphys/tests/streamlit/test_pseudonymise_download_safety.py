"""Downloads do not interpolate filenames into unsafe HTML."""

from pymedphys._streamlit.apps import pseudonymise


def test_zip_download_uses_native_api_and_sanitizes_filename(monkeypatch):
    calls = []

    def download_button(*args, **kwargs):
        calls.append((args, kwargs))

    def unexpected_html(*args, **kwargs):
        raise AssertionError("unsafe HTML must not be used for downloads")

    monkeypatch.setattr(pseudonymise.st.sidebar, "download_button", download_button)
    monkeypatch.setattr(pseudonymise.st.sidebar, "markdown", unexpected_html)
    payload = b"synthetic ZIP data"
    pseudonymise.link_to_zipbuffer_download(r"C:\patient\example.zip", payload)
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args == ("Download pseudonymised ZIP",)
    assert kwargs["data"] == payload
    assert kwargs["file_name"] == "example.zip"
    assert kwargs["mime"] == "application/zip"
