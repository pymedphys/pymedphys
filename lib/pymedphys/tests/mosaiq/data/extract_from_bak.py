"""Fleshes out CSV files found within this directory from a .bak file.

By design, only tables and columns that have been defined within
`types_map.toml` are extracted so as to not expose any more of the
underlying database schema than what is already within the repository.
"""

import pathlib

HERE = pathlib.Path(__file__).parent

TYPES_MAP = HERE / "types_map.toml"
