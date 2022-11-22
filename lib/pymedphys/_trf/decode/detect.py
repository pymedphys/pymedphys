from .header import decode_header
from .partition import split_into_header_table
from .table import decode_rows
from .trf2pandas import header_as_dataframe


def detect_cli(args):
    detect_file_encoding(args.filepath)


def detect_file_encoding(filepath):
    with open(filepath, "rb") as file:
        trf_contents = file.read()

    trf_header_contents, trf_table_contents = split_into_header_table(trf_contents)

    header_dataframe = header_as_dataframe(trf_header_contents)
    print(header_dataframe)

    header = decode_header(trf_header_contents)

    version = header.version
    item_parts_length = header.item_parts_length
    item_parts = header.item_parts

    possible_groupings = search_for_possible_decoding_options(
        trf_table_contents, version, item_parts_length, item_parts
    )

    return possible_groupings


def search_for_possible_decoding_options(
    trf_table_contents, version, item_parts_length, item_parts
):
    line_grouping_range = item_parts_length
    linac_state_codes_column_range = range(0, 50)

    possible_groupings = []

    for line_grouping in line_grouping_range:
        for linac_state_codes_column in linac_state_codes_column_range:
            try:
                decode_rows(
                    trf_table_contents,
                    version=version,
                    item_parts_length=item_parts_length,
                    item_parts=item_parts,
                )
                possible_groupings.append([line_grouping, linac_state_codes_column])
                print(
                    f"Line Grouping: {line_grouping}, Linac State Codes Column: {linac_state_codes_column}"
                )
            except ValueError:
                pass

    return possible_groupings
