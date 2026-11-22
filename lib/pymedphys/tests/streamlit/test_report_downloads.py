"""Regression tests for native Streamlit report downloads."""

from types import SimpleNamespace
from unittest.mock import Mock

from pymedphys._streamlit.apps import pseudonymise
from pymedphys._streamlit.apps.metersetmap import main as metersetmap_main


def test_pseudonymisation_zip_download_keeps_filename_as_data(monkeypatch):
    download = Mock()
    monkeypatch.setattr(
        pseudonymise,
        "st",
        SimpleNamespace(sidebar=SimpleNamespace(download_button=download)),
    )
    filename = "synthetic' onclick='example.zip"
    zip_bytes = b"PK\x03\x04synthetic"

    pseudonymise.link_to_zipbuffer_download(filename, zip_bytes)

    download.assert_called_once_with(
        label=f"Click to download {filename}",
        data=zip_bytes,
        file_name=filename,
        mime="application/zip",
    )


def test_metersetmap_pdf_download_keeps_filename_as_data(monkeypatch, tmp_path):
    download = Mock()
    monkeypatch.setattr(
        metersetmap_main,
        "st",
        SimpleNamespace(write=Mock(), download_button=download),
    )
    monkeypatch.setattr(metersetmap_main.subprocess, "check_call", Mock())

    pdf_path = tmp_path / "synthetic' onclick='example.pdf"
    pdf_bytes = b"%PDF-1.4\nsynthetic"
    pdf_path.write_bytes(pdf_bytes)

    metersetmap_main.convert_png_to_pdf("synthetic.png", pdf_path)

    download.assert_called_once_with(
        label=f"Click to download {pdf_path.name}",
        data=pdf_bytes,
        file_name=pdf_path.name,
        mime="application/pdf",
    )
