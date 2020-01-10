import copy
import datetime
import functools
import lzma
import os
import pathlib
import re

import numpy as np
import pandas as pd

offset = 20000
date_pattern = re.compile(b"\d\d\d\d-\d\d-\d\d\d\d:\d\d:\d\d.")
item_pattern = re.compile(b"\x00\x00\x00([a-zA-Z0-9 \.-]+)")


def get_most_recent_data_point():
    with pymedphys._utilities.filesystem.open_no_lock(live_path, "rb") as f:
        f.seek(0, os.SEEK_END)
        file_size = f.tell()
        f.seek(file_size - offset)
        data = f.read()

    data_points = get_data_points(data)
    return data_points[-1]


def get_data_points(data):
    date_index = [m.span() for m in date_pattern.finditer(data)]
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
    header = b"0\xb8\x00DS\x00R[\x03\x04\x05\x06]\x00\x00\x00" + label + b"\n"
    item = b"0\x1c\x01DS\x00R[\x03\x04\x05\x06]\x00\x00\x00(-?\d+\.\d+)"

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
    regex = re.compile(
        b"[0\x00pP]"
        + key
        + b"\x00[PSR][\x01\x02\x03\x04\x05\x06]\x00\x00\x00([a-zA-Z0-9 \.-]+)"
    )
    return regex


def extract_by_lookup(data, key):
    regex = get_lookup_regex(key)
    match = regex.search(data)

    span = match.span()
    removed_data = data[0 : span[0]] + data[span[1] + 1 : :]

    return removed_data, match.group(1)


def extract_all_lookup(data, result):
    for key, label in lookup.items():
        try:
            data, result[label] = extract_by_lookup(data, key)
        except AttributeError:
            result[label] = None

    return data


def run_all_assertions(data, result):
    for key, label in assert_equal.items():
        try:
            while True:
                data, new_result = extract_by_lookup(data, key)
                if result[label] != new_result:
                    raise ValueError(
                        f"Expected these to be the same:\n{label}\n{result[label]}\n{new_result}"
                    )
        except AttributeError:
            pass

    return data


def strict_extract(data):
    result = dict()

    data = extract_all_lookup(data, result)

    data, result["mlc"] = extract_coll(data, b"MLCX", 160)
    data, result["jaw_x"] = extract_coll(data, b"ASYMX", 2)
    data, result["jaw_y"] = extract_coll(data, b"ASYMY", 2)

    data = run_all_assertions(data, result)

    for key, a_type in types.items():
        if result[key] == b"-32767":
            result[key] = None
            continue

        if a_type is str:
            result[key] = result[key].decode()
        else:
            result[key] = a_type(result[key])

    return data, result


def get_patient_id(data_point):
    try:
        _, patient_id = extract_by_lookup(data_point, inverse_lookup["Patient ID"])
        patient_id = patient_id.decode()
    except AttributeError:
        patient_id = None

    return patient_id


types = {
    "Patient ID": str,
    "Machine ID": str,
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
}


lookup = {
    b" \x00LO": "Patient ID",
    b"\xb2\x00SH": "Machine ID",
    b"\xc6\x00CS": "Radiation Type",
    b"\x14\x01SH": "Energy",
    b"\x18\x01CS": "Wedge",
    b"\x07\x10DS": "Segment",
    b"\t\x10DS": "Total MU",
    b"2\x00DS": "Delivery MU",
    b"3\x00DS": "Backup Delivery MU",
    b"8\x00SH": "Beam Timer",
    b"\x0b\x00DS": "Segment MU",
    b"\x1e\x01DS": "Gantry",
    b" \x01DS": "Collimator",
    b'"\x01DS': "Table Column",
    b"\%\x01DS": "Table Isocentric",
    b"\(\x01DS": "Table Vertical",
    b"\)\x01DS": "Table Longitudinal",
    b"\*\x01DS": "Table Lateral",
}

inverse_lookup = {key: item for item, key in lookup.items()}

assert_equal = {
    #     b'\x07\x10DS': 'Segment',
    b"\x06\x10LO": "Machine ID"
}


def initial_results_parse(data_point):
    pattern = re.compile(b"(........\x00\x00\x00[a-zA-Z0-9 \.-]+)")

    results = pattern.findall(data_point)
    results = np.array(results)

    return results
