"""Regression coverage for safe-by-default DICOM listener binding."""

import argparse

from pymedphys.cli.dicom import set_up_dicom_cli


def _parse_listen_args(*options):
    parser = argparse.ArgumentParser()
    set_up_dicom_cli(parser.add_subparsers(dest="command"))
    return parser.parse_args(["dicom", "listen", "0", *options])


def test_dicom_listener_binds_to_loopback_by_default():
    args = _parse_listen_args()
    assert args.host == "127.0.0.1"


def test_dicom_listener_allows_explicit_network_bind():
    args = _parse_listen_args("--host", "0.0.0.0")
    assert args.host == "0.0.0.0"
