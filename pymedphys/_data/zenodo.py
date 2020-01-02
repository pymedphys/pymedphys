import json
import pathlib

from pymedphys._imports import requests

BASE_URL = "https://zenodo.org/api/records/"
HERE = pathlib.Path(__file__).resolve().parent


def get_zenodo_file_urls(record_name):
    files = get_all_zenodo_file_data(record_name)
    urls = {record["key"]: record["links"]["self"] for record in files}

    return urls


def get_all_zenodo_file_data(record_name):
    record_id = get_zenodo_record_id(record_name)
    files = get_all_zenodo_file_data_by_id(record_id)

    return files


def get_all_zenodo_file_data_by_id(record_id):
    response = requests.get(f"{BASE_URL}{record_id}")
    data = json.loads(response.text)
    files = data["files"]

    return files


def get_zenodo_file_md5s(record_name):
    files = get_all_zenodo_file_data(record_name)
    checksums = {
        record["key"]: record["checksum"].replace("md5:", "") for record in files
    }

    return checksums


def get_zenodo_record_id(record_name):
    with open(HERE.joinpath("zenodo.json"), "r") as zenodo_file:
        zenodo = json.load(zenodo_file)

    try:
        record_id = zenodo[record_name]
    except KeyError:
        raise ValueError(
            "This Zenodo record isn't recorded within this version of PyMedPhys."
        )

    return record_id


def update_zenodo_record_id(record_name, record_id):
    with open(HERE.joinpath("zenodo.json"), "r") as zenodo_file:
        zenodo = json.load(zenodo_file)

    zenodo[record_name] = record_id

    with open(HERE.joinpath("zenodo.json"), "w") as zenodo_file:
        json.dump(zenodo, zenodo_file, indent=2)
