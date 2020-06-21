import functools
import getpass
import json
import pathlib

from pymedphys._imports import keyring, requests

ZENODO_HOSTNAME = "zenodo.org"
BASE_URL = f"https://{ZENODO_HOSTNAME}/api/records/"
HERE = pathlib.Path(__file__).resolve().parent


@functools.lru_cache()
def get_zenodo_file_urls(record_name):
    files = get_all_zenodo_file_data(record_name)
    urls = {record["key"]: record["links"]["self"] for record in files}

    return urls


@functools.lru_cache()
def get_all_zenodo_file_data(record_name):
    record_id = get_zenodo_record_id(record_name)
    files = get_all_zenodo_file_data_by_id(record_id)

    return files


@functools.lru_cache()
def get_all_zenodo_file_data_by_id(record_id):
    response = requests.get(f"{BASE_URL}{record_id}")
    data = json.loads(response.text)
    files = data["files"]

    return files


@functools.lru_cache()
def get_zenodo_file_md5s(record_name):
    files = get_all_zenodo_file_data(record_name)
    checksums = {
        record["key"]: record["checksum"].replace("md5:", "") for record in files
    }

    return checksums


@functools.lru_cache()
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


def get_zenodo_access_token(hostname=ZENODO_HOSTNAME):
    access_token = keyring.get_password("Zenodo", hostname)

    if access_token is None or access_token == "":
        print(
            "To upload files to Zenodo you need to provide a Zenodo "
            "access token. Please go to "
            f"https://{hostname}/account/settings/applications/tokens/new "
            "login to Zenodo and create a new access token.\n"
            "When creating the access token use the scopes `deposit:actions`, `deposit:write`, "
            "and `user:email`. Once you have your token copy it into the prompt below "
            "to continue with the upload."
        )
        access_token = getpass.getpass()
        set_zenodo_access_token(access_token, hostname)

    return access_token


def set_zenodo_access_token_cli(args):
    set_zenodo_access_token(args.token)


def set_zenodo_access_token(access_token, hostname=ZENODO_HOSTNAME):
    keyring.set_password("Zenodo", hostname, access_token)
