"""Fleshes out CSV files found within the data directory from a .bak file.

By design, only tables and columns that have been defined within
`data/types_map.toml` are extracted so as to not expose any more of the
underlying database schema than what is already within the repository.
"""
