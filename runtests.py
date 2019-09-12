#!/usr/bin/env python
"""
runtests.py [OPTIONS] [-- ARGS]

Run tests

Examples::

    $ python runtests.py
"""

import sys

# In case we are run from the source directory, we don't want to import the
# project from there:
sys.path.pop(0)

import argparse


def main(argv):
    parser = argparse.ArgumentParser(usage=__doc__.lstrip())
