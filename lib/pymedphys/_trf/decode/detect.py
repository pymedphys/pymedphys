"""Report which of the known TRF row layouts decode a file.

The decoder reads a file's row layout from the version in its header. When a
file will not decode, for example one from a newer linac software version,
this tries every row layout the decoder knows, and names any item parts that
have no column name.
"""

from .constants import CONFIG
from .header import decode_header
from .partition import split_into_header_table
from .table import decode_rows
from .trf2pandas import header_as_dataframe


def detect_cli(args):
    layouts = detect_file_encoding(args.filepath)

    if not layouts:
        raise SystemExit("None of the known TRF row layouts decode this file.")


def detect_file_encoding(filepath):
    """Print the header and the row layouts that decode the file's table.

    Returns the versions whose row layout decodes the table.
    """
    with open(filepath, "rb") as file:
        trf_contents = file.read()

    trf_header_contents, trf_table_contents = split_into_header_table(trf_contents)

    header_dataframe = header_as_dataframe(trf_header_contents)
    print(header_dataframe)

    header = decode_header(trf_header_contents)

    unknown = unknown_item_parts(header.item_parts)
    if unknown:
        print(f"Item parts with no column name: {', '.join(unknown)}")

    layouts = search_for_possible_decoding_options(
        trf_table_contents, header.item_parts_length, header.item_parts
    )

    print(f"Header version: {header.version}")
    print(f"Row layouts that decode the table: {layouts}")

    return layouts


def unknown_item_parts(item_parts):
    """Return the item part pairs that have no column name, such as "1_2"."""
    pairs = [
        f"{item_parts[i]}_{item_parts[i + 1]}" for i in range(0, len(item_parts), 2)
    ]

    return [pair for pair in pairs if pair not in CONFIG["item_part_names"]]


def search_for_possible_decoding_options(
    trf_table_contents, item_parts_length, item_parts
):
    """Return the versions whose row layout decodes the table.

    A layout decodes the table when every row it reads has one value for each
    column, as reading the file into a table requires.
    """
    layouts = []

    for version in sorted(CONFIG["version_row"], key=int):
        try:
            rows, column_names = decode_rows(
                trf_table_contents,
                version=int(version),
                item_parts_length=item_parts_length,
                item_parts=item_parts,
            )
        except (KeyError, ValueError):
            continue

        if rows and all(len(row) == len(column_names) for row in rows):
            layouts.append(int(version))

    return layouts
