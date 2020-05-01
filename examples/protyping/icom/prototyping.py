import datetime
import functools
import os
import re

import numpy as np

# pylint: disable = protected-access
import pymedphys._utilities.filesystem

offset = 20000
DATE_PATTERN = re.compile(rb"\d\d\d\d-\d\d-\d\d\d\d:\d\d:\d\d.")
ITEM_PATTERN = re.compile(rb"\x00\x00\x00([a-zA-Z0-9 \.-]+)")


def get_most_recent_data_point(live_path):
    with pymedphys._utilities.filesystem.open_no_lock(live_path, "rb") as f:
        f.seek(0, os.SEEK_END)
        file_size = f.tell()
        f.seek(file_size - offset)
        data = f.read()

    data_points = get_data_points(data)
    return data_points[-1]


def get_data_points(data):
    date_index = [m.span() for m in DATE_PATTERN.finditer(data)]
    start_points = [span[0] - 8 for span in date_index]

    end_points = start_points[1::] + [None]

    data_points = [data[start:end] for start, end in zip(start_points, end_points)]
    return data_points


def extract_positions_by_header(key, num_items, results_by_line):
    header_index = results_by_line.index([key])
    return [
        float(item[0])
        for item in results_by_line[header_index + 1 : header_index + 1 + num_items]
    ]


def get_jaw_and_mlc(results_by_line):
    options = [(b"ASYMX", 2), (b"ASYMY", 2), (b"MLCX", 160)]
    collimation = {}
    for key, num_items in options:
        collimation[key] = extract_positions_by_header(key, num_items, results_by_line)

    return collimation


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
    items = np.array([float(item) for item in match.groups()])

    return data, items


@functools.lru_cache()
def get_lookup_regex(key):
    regex = re.compile(rb"[0\x00pP]" + key + rb".\x00\x00\x00([a-zA-Z0-9 \.-]+)")
    return regex


def extract_by_lookup(data, key, this_type):
    regex = get_lookup_regex(key)
    match = regex.search(data)

    try:
        span = match.span()
    except AttributeError:
        return data, None

    removed_data = data[0 : span[0]] + data[span[1] + 1 : :]

    result = match.group(1)
    if result == b"-32767":
        removed_data, result = extract_by_lookup(removed_data, key, this_type)
    elif this_type is str:
        result = result.decode()
    else:
        result = this_type(result)

    return removed_data, result


def extract_all_lookup(data, result):
    for key, label in lookup.items():
        data, result[label] = extract_by_lookup(data, key, types[label])

    return data


def extract_all_multiples(data, result):
    for key, label in multiples.items():
        result[label] = []

        while True:
            data, a_result = extract_by_lookup(data, key, types[label])
            if a_result is not None:
                result[label].append(a_result)
            else:
                break

    return data


# def run_all_assertions(data, result):
#     for key, label in assert_equal.items():
#         try:
#             while True:
#                 data, new_result = extract_by_lookup(data, key, types[label])
#                 if result[label] != new_result:
#                     raise ValueError(
#                         f"Expected these to be the same:\n{label}\n{result[label]}\n{new_result}"
#                     )
#         except AttributeError:
#             pass

#     return data


def strict_extract(data):
    result = dict()

    timestamp_and_counter = DATE_PATTERN.search(data).group(0)
    timestamp = timestamp_and_counter[:-1]
    counter = int(timestamp_and_counter[-1])

    result["Timestamp"] = datetime.datetime.strptime(
        timestamp.decode(), "%Y-%m-%d%H:%M:%S"
    ).isoformat()
    result["Counter"] = counter

    data = extract_all_lookup(data, result)
    data = extract_all_multiples(data, result)

    data, result["MLCX"] = extract_coll(data, b"MLCX", 160)
    data, result["ASYMX"] = extract_coll(data, b"ASYMX", 2)
    data, result["ASYMY"] = extract_coll(data, b"ASYMY", 2)

    # data = run_all_assertions(data, result)
    return data, result


def get_patient_id(data_point):
    _, patient_id = extract_by_lookup(data_point, inverse_lookup["Patient ID"], str)
    return patient_id


types = {
    "Patient ID": str,
    "Patient Name": str,
    "Rx Site": str,
    "Field ID": str,
    "Machine ID": int,
    "Radiation Type": str,
    "Energy": str,
    "Wedge": str,
    "Segment": int,
    "Total MU": float,
    "Delivery MU": float,
    "Backup Delivery MU": float,
    "Beam Timer": float,
    "Segment MU": float,
    "Gantry": float,
    "Collimator": float,
    "Table Column": int,
    "Table Isocentric": int,
    "Table Vertical": float,
    "Table Longitudinal": float,
    "Table Lateral": float,
    "Interlocks": str,
    "Previous Interlocks": str,
    "Beam Description": str,
}


lookup = {
    b" \x00LO\x00P": "Patient ID",
    b"\x10\x00PN\x00P": "Patient Name",
    b"\x01\x10LO\x00P": "Rx Site",
    b"\x03\x10LO\x00P": "Field ID",
    b"\xb2\x00SH\x00P": "Machine ID",
    b"\xc6\x00CS\x00R": "Radiation Type",
    b"\x14\x01SH\x00R": "Energy",
    b"\x18\x01CS\x00R": "Wedge",
    b"\x07\x10DS\x00R": "Segment",
    b"\t\x10DS\x00R": "Total MU",
    b"2\x00DS\x00R": "Delivery MU",
    b"3\x00DS\x00R": "Backup Delivery MU",
    b"8\x00SH\x00R": "Beam Timer",
    b"\x0b\x00DS\x00R": "Segment MU",
    b"\x1e\x01DS\x00R": "Gantry",
    b" \x01DS\x00R": "Collimator",
    b'"\x01DS\x00R': "Table Column",
    rb"\%\x01DS\x00R": "Table Isocentric",
    rb"\(\x01DS\x00R": "Table Vertical",
    rb"\)\x01DS\x00R": "Table Longitudinal",
    rb"\*\x01DS\x00R": "Table Lateral",
    b"\x0c\x00SH\x00R": "Beam Description",
}

multiples = {
    b"\x16\x10LO\x00R": "Interlocks",
    b"\x18\x10LO\x00R": "Previous Interlocks",
}

inverse_lookup = {key: item for item, key in lookup.items()}

# assert_equal = {
#     #     b'\x07\x10DS': 'Segment',
# #     b"\x06\x10LO": "Machine ID"
# }


def initial_results_parse(data_point):
    pattern = re.compile(b"(........\x00\x00\x00[a-zA-Z0-9 \.-]+)")

    results = pattern.findall(data_point)
    results = np.array(results)

    return results
