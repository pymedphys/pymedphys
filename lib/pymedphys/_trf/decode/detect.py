"""Report which of the known TRF row layouts fit a file.

The decoder reads a file's row layout from the version in its header. When a
file will not decode, for example one from a newer linac software version,
this reports which row layouts the decoder knows fit the file's table, and
names any item parts that have no column name.
"""

from .constants import CONFIG
from .header import decode_header
from .partition import split_into_header_table
from .table import row_length
from .trf2pandas import header_as_dataframe


def detect_cli(args):
    layouts = detect_file_encoding(args.filepath)

    if not layouts:
        raise SystemExit("None of the known TRF row layouts fit this file.")


def detect_file_encoding(filepath):
    """Print the header and the row layouts that fit the file's table.

    Returns the versions whose row layout fits the table.
    """
    with open(filepath, "rb") as file:
        trf_contents = file.read()

    trf_header_contents, trf_table_contents = split_into_header_table(trf_contents)

    header_dataframe = header_as_dataframe(trf_header_contents)
    print(header_dataframe)

    header = decode_header(trf_header_contents)

    unknown = unknown_item_parts(header.item_parts)
    if unknown:
        print(
            f"Item parts with no column name: {', '.join(unknown)}. Reading "
            "the file needs a name for each, in the decoder's configuration."
        )

    layouts = search_for_possible_decoding_options(
        trf_table_contents, header.item_parts_length
    )

    print(f"Header version: {header.version}")
    print(f"Row layouts that fit the table: {layouts}")

    return layouts


def unknown_item_parts(item_parts):
    """Return the item part pairs that have no column name, such as "1_2"."""
    pairs = [
        f"{item_parts[i]}_{item_parts[i + 1]}" for i in range(0, len(item_parts), 2)
    ]

    return [pair for pair in pairs if pair not in CONFIG["item_part_names"]]


def search_for_possible_decoding_options(trf_table_contents, item_parts_length):
    """Return the versions whose row layout fits the table.

    Every known layout gives each row one value per column, so a layout fits
    when the table is a whole number of its rows. This does not look up the
    columns' names, so an item part with no name, such as one a newer linac
    software version logs, does not hide the layouts that fit.
    """
    if not item_parts_length or not trf_table_contents:
        return []

    return [
        int(version)
        for version in sorted(CONFIG["version_row"], key=int)
        if len(trf_table_contents) % row_length(version, item_parts_length) == 0
    ]
