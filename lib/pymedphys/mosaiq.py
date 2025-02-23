"""Module to handle the connection to a Mosaiq SQL database and execute SQL queries."""

# pylint: disable = unused-import
# ruff: noqa: F401

from ._mosaiq.api import Connection, Cursor, connect, execute
