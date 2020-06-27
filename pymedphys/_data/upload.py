# Copyright (C) 2019 Simon Biggs

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import hashlib
import json
import pathlib
import urllib

from pymedphys._imports import keyring, requests

from .zenodo import get_zenodo_access_token, get_zenodo_record_id

HEADERS = {"Content-Type": "application/json"}


def zenodo_api_with_helpful_fallback(url, method, **kwargs):
    hostname = urllib.parse.urlparse(url).hostname

    access_token = get_zenodo_access_token(hostname)
    kwargs["params"] = {"access_token": access_token}

    r = getattr(requests, method)(url, **kwargs)
    if r.status_code == 401:
        print("The access token you provided is invalid.\n")
        keyring.delete_password("Zenodo", hostname)
        return zenodo_api_with_helpful_fallback(url, **kwargs)
    if r.status_code == 403:
        print(
            "The access token you provided doesn't appear to have the right scopes. "
            "Make sure that the access token you provide has the scopes "
            "`deposit:actions`, `deposit:write`, and `user:email`.\n"
        )
        keyring.delete_password("Zenodo", hostname)
        return zenodo_api_with_helpful_fallback(url, **kwargs)

    return r


def create_metadata(title, author=None):
    if author is None:
        author = "PyMedPhys Contributors"

    metadata = {
        "metadata": {
            "title": title,
            "upload_type": "dataset",
            "creators": [{"name": author}],
            "description": "<p>This is an automated upload from the PyMedPhys library.</p>",
            "license": "Apache-2.0",
            "access_right": "open",
        }
    }

    return json.dumps(metadata)


def publish_deposition(deposition_id, use_sandbox=False):
    deposition_url = get_deposition_url(deposition_id, use_sandbox=use_sandbox)

    publish_url = f"{deposition_url}/actions/publish"
    r = zenodo_api_with_helpful_fallback(publish_url, "post")

    if r.status_code != 202:
        raise ValueError(
            f"Unexpected status code when publishing the file. Expected 202, got {r.status_code}."
        )


def get_zenodo_url(use_sandbox):
    if use_sandbox:
        zenodo_url = "https://sandbox.zenodo.org/"
    else:
        zenodo_url = "https://zenodo.org/"

    return zenodo_url


def get_deposition_url(deposition_id, use_sandbox=False):
    root_depositions_url = get_root_depositions_url(use_sandbox)
    deposition_url = f"{root_depositions_url}/{deposition_id}"

    return deposition_url


def get_root_depositions_url(use_sandbox):
    zenodo_url = get_zenodo_url(use_sandbox)
    root_depositions_url = f"{zenodo_url}api/deposit/depositions"

    return root_depositions_url


def get_files_url(deposition_id, use_sandbox=False):
    deposition_url = get_deposition_url(deposition_id, use_sandbox=use_sandbox)
    files_url = f"{deposition_url}/files"

    return files_url


def delete_filenames_within_record(filenames, deposition_id, use_sandbox=False):
    files_url = get_files_url(deposition_id, use_sandbox=use_sandbox)

    r = zenodo_api_with_helpful_fallback(files_url, "get")
    record_filenames = [record["filename"] for record in r.json()]

    for filename in filenames:
        if filename in record_filenames:
            file_self_urls = [
                record["links"]["self"]
                for record in r.json()
                if record["filename"] == filename
            ]

            if len(file_self_urls) > 1:
                raise ValueError("Unexpected number of file_ids found")

            file_self_url = file_self_urls[0]

            zenodo_api_with_helpful_fallback(file_self_url, "delete")


def upload_filepaths(filepaths, deposition_id, use_sandbox=False):
    files_url = get_files_url(deposition_id, use_sandbox=use_sandbox)

    for filepath in filepaths:
        md5 = hashlib.md5()

        with open(filepath, "rb") as upload_file:
            md5.update(upload_file.read())

            upload_file.seek(0)
            r = zenodo_api_with_helpful_fallback(
                files_url,
                "post",
                data={"name": filepath.name},
                files={"file": upload_file},
            )

        response = r.json()

        try:
            record_checksum = response["checksum"]
        except KeyError:
            raise ValueError(
                f"The response when uploading was not as expected:\n {response}"
            )

        if md5.hexdigest() != record_checksum:
            raise ValueError(
                "The uploaded Zenodo's checksum does not match the local checksum.\n"
                f"  Zenodo's Checksum: {record_checksum}\n"
                f"  Local Checksum: {md5.hexdigest()}"
            )


def set_metadata(metadata, deposition_id, use_sandbox=False):
    deposition_url = get_deposition_url(deposition_id, use_sandbox=use_sandbox)
    zenodo_api_with_helpful_fallback(
        deposition_url, "put", data=metadata, headers=HEADERS
    )


def upload_files_to_zenodo(
    filepaths, title, author=None, use_sandbox=False, record_name=None
):
    filepaths = [pathlib.Path(filepath) for filepath in filepaths]

    root_depositions_url = get_root_depositions_url(use_sandbox)

    if record_name is not None:
        if use_sandbox:
            raise ValueError("Cannot use sandbox when `record_name` is provided")

        old_deposition_id = get_zenodo_record_id(record_name)
        old_deposition_url = f"{root_depositions_url}/{old_deposition_id}"
        new_version_url = f"{old_deposition_url}/actions/newversion"
        r = zenodo_api_with_helpful_fallback(new_version_url, "post")
        deposition_id = int(r.json()["links"]["latest_draft"].split("/")[-1])
    else:
        r = zenodo_api_with_helpful_fallback(
            root_depositions_url, "post", json={}, headers=HEADERS
        )

        try:
            response = r.json()
        except json.JSONDecodeError:
            raise ValueError(f"Unexpected response: {r.text}")

        try:
            deposition_id = response["id"]
        except KeyError:
            raise ValueError(f"Unexpected response: {response}")

    metadata = create_metadata(title, author)
    set_metadata(metadata, deposition_id, use_sandbox=use_sandbox)

    filenames = [path.name for path in filepaths]
    delete_filenames_within_record(filenames, deposition_id, use_sandbox=use_sandbox)

    upload_filepaths(filepaths, deposition_id, use_sandbox=use_sandbox)
    publish_deposition(deposition_id, use_sandbox=use_sandbox)

    return deposition_id
