# Copyright (C) 2019 Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import argparse
import logging
import sys

from pymedphys import _config
from pymedphys._vendor.patchlogging import apply_logging_patch

from .dev import dev_cli
from .dicom import dicom_cli
from .experimental import experimental_cli
from .gui import gui_cli
from .icom import icom_cli
from .streamlit import streamlit_cli
from .trf import trf_cli
from .zenodo import zenodo_cli


class DefaultHelpParser(argparse.ArgumentParser):
    def error(self, message):
        sys.stderr.write("error: %s\n" % message)
        self.print_help()
        sys.exit(2)


def define_parser():
    parser = DefaultHelpParser(prog="pymedphys")
    subparsers = parser.add_subparsers()

    dicom_cli(subparsers)
    experimental_cli(subparsers)
    trf_cli(subparsers)
    dev_cli(subparsers)
    zenodo_cli(subparsers)
    icom_cli(subparsers)
    gui_cli(subparsers)
    streamlit_cli(subparsers)

    # https://stackoverflow.com/a/20663028/3912576
    parser.add_argument(
        "-v",
        "--verbose",
        help="Be verbose",
        action="store_true",
        dest="logging_verbose",
    )
    parser.add_argument(
        "-d",
        "--debug",
        help="Print debugging statements",
        action="store_true",
        dest="logging_debug",
    )

    return parser


def get_logging_config():
    try:
        config = _config.get_config()
    except FileNotFoundError:
        return {}

    try:
        cli_config = config["cli"]
        logging_config = cli_config["logging"]
    except KeyError:
        return {}

    return logging_config


def run_logging_basic_config(args, logging_config):
    if "level" not in logging_config:
        logging_config["level"] = logging.WARNING

    # Allow command line options to override the config.toml options
    if args.logging_verbose:
        logging_config["level"] = logging.INFO
    else:
        try:
            logging_config["level"] = getattr(logging, logging_config["level"].upper())
        except AttributeError:
            pass

    # Have debug after info so that if both --verbose and --debug are
    # passed to the CLI debug will be used. Should both be passed it is
    # logged as a warning below.
    if args.logging_debug:
        logging_config["level"] = logging.DEBUG

    if "format" not in logging_config:
        logging_config["format"] = "%(asctime)s %(levelname)-8s %(message)s"

        if logging_config["level"] <= logging.DEBUG:
            logging_config["format"] += "\n    %(pathname)s#%(lineno)d"

    if "datefmt" not in logging_config:
        logging_config["datefmt"] = "%Y-%m-%d %H:%M:%S"

    logging.basicConfig(force=True, **logging_config)

    if args.logging_debug and args.logging_verbose:
        logging.warning(
            "Both --verbose and --debug were defined. Verbose mode was "
            "ignored. Debug mode has been used."
        )

    logging.info(
        "Set `logging.basicConfig` with:\n%(logging_config)s",
        {"logging_config": logging_config},
    )


def pymedphys_cli():
    _config.is_cli = True

    # This is to allow the usage of force=True within logging.basicConfig
    apply_logging_patch()

    parser = define_parser()

    args, remaining = parser.parse_known_args()
    logging_config = get_logging_config()
    run_logging_basic_config(args, logging_config)

    if hasattr(args, "func"):
        try:
            args.func(args, remaining)
            return
        except TypeError:
            pass

        parser.parse_args()
        args.func(args)

        return

    subparser_names = [
        attribute
        for attribute in dir(args)
        if not (attribute.startswith("_") or attribute.startswith("logging"))
    ]

    if not subparser_names:
        parser.print_help()
    else:
        assert len(subparser_names) == 1

        subparser_name = subparser_names[0]
        assert getattr(args, subparser_name) is None

        parser.parse_args([subparser_name, "--help"])
