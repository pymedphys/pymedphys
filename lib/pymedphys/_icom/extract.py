import functools
import re

from . import mappings

DATE_PATTERN = re.compile(rb"\d\d\d\d-\d\d-\d\d\d\d:\d\d:\d\d")


def get_data_points(data):
    date_index = [m.span() for m in DATE_PATTERN.finditer(data)]
    start_points = [span[0] - 8 for span in date_index]

    end_points = start_points[1::] + [None]

    data_points = [data[start:end] for start, end in zip(start_points, end_points)]
    return data_points


@functools.lru_cache()
def get_coll_regex(label, number):
    header = rb"0\xb8\x00DS\x00R.\x00\x00\x00" + label + b"\n"
    item = rb"0\x1c\x01DS\x00R.\x00\x00\x00(-?\d+\.\d+)"

    regex = re.compile(header + b"\n".join([item] * number))
    return regex


def extract_coll(data, label, number):
    regex = get_coll_regex(label, number)

    match = regex.search(data)
    span = match.span()

    data = data[0 : span[0]] + data[span[1] + 1 : :]
    items = [float(item) for item in match.groups()]

    return data, items


@functools.lru_cache()
def get_extraction_regex(key):
    regex = re.compile(
        rb"""[0\x00pP]""" + key + rb""".\x00\x00\x00([,\-'"a-zA-Z0-9 \.-]+)"""
    )
    return regex


def extract(data, label):
    key, this_type, where = mappings.ICOM[label]

    if where == "all":
        return extract_all(data, key, this_type)

    if where == "first":
        return extract_first(data, key, this_type)

    raise ValueError("Unexpected value for where")


def extract_all(data, key, this_type):
    result = []
    while True:
        data, a_result = extract_first(data, key, this_type)
        if a_result is not None:
            result.append(a_result)
        else:
            break

    return data, result


def extract_first(data, key, this_type):
    regex = get_extraction_regex(key)
    match = regex.search(data)

    try:
        span = match.span()
    except AttributeError:
        return data, None

    data = data[0 : span[0]] + data[span[1] + 1 : :]

    result = match.group(1)
    if result == b"-32767":
        data, result = extract_first(data, key, this_type)
    elif this_type is str:
        result = result.decode()
    else:
        result = this_type(result)

    return data, result
