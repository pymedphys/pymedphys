import functools
import re

from . import mappings


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
