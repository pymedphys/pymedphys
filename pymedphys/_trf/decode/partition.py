from .header import determine_header_length


def split_into_header_table(trf_contents):
    header_length = determine_header_length(trf_contents)

    trf_header_contents = trf_contents[0:header_length]
    trf_table_contents = trf_contents[header_length::]

    return trf_header_contents, trf_table_contents
