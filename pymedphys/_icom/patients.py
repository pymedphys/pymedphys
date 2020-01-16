import functools
import pathlib
import re

from . import mappings, observer


@functools.lru_cache()
def get_extraction_regex(key):
    regex = re.compile(rb"[0\x00pP]" + key + rb".\x00\x00\x00([a-zA-Z0-9 \.-]+)")
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


def get_patient_id(data):
    _, patient_id = extract(data, "Patient ID")
    return patient_id


class PatientIcomData:
    def __init__(self, output_dir):
        self._data = {}
        self._output_dir = pathlib.Path(output_dir)

    def update_data(self, ip, data):
        try:
            self._data[ip].append(data)
        except KeyError:
            self._data[ip] = [data]

        timestamp = data[8:26].decode()
        patient_id = get_patient_id(data)
        print(f"IP: {ip} | Timestamp: {timestamp} | Patient ID: {patient_id}")


def archive_by_patient(directories_to_watch, output_dir):
    patient_icom_data = PatientIcomData(output_dir)

    def archive_by_patient_callback(ip, data):
        patient_icom_data.update_data(ip, data)

    observer.observe_with_callback(directories_to_watch, archive_by_patient_callback)


def archive_by_patient_cli(args):
    directories_to_watch = args.directories
    output_dir = args.output_dir

    archive_by_patient(directories_to_watch, output_dir)
