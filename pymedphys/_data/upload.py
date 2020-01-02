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


import getpass
import hashlib
import json
import pathlib
import urllib

import keyring
import requests


def get_zenodo_access_token(hostname):
    access_token = keyring.get_password("Zenodo", hostname)

    if access_token is None or access_token == "":
        print(
            "To upload files to Zenodo you need to provide a Zenodo "
            "access token. Please go to "
            f"<https://{hostname}/account/settings/applications/tokens/new/>, "
            "login to Zenodo and create a new access token.\n"
            "When creating the access token use the scopes `deposit:actions`, `deposit:write`, "
            "and `user:email`. Once you have your token copy it into the prompt below "
            "to continue with the upload."
        )
        access_token = getpass.getpass()
        keyring.set_password("Zenodo", hostname, access_token)

    return access_token


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


def upload_zenodo_file(filepath, title, author=None, use_sandbox=False):
    filepath = pathlib.Path(filepath)

    if use_sandbox:
        zenodo_url = "https://sandbox.zenodo.org/"
    else:
        zenodo_url = "https://zenodo.org/"

    depositions_url = f"{zenodo_url}api/deposit/depositions"

    headers = {"Content-Type": "application/json"}
    r = zenodo_api_with_helpful_fallback(
        depositions_url, "post", json={}, headers=headers
    )

    deposition_id = r.json()["id"]
    deposition_url = f"{depositions_url}/{deposition_id}"
    files_url = f"{deposition_url}/files"

    md5 = hashlib.md5()
    with open(filepath, "rb") as upload_file:
        md5.update(upload_file.read())

        upload_file.seek(0)
        r = zenodo_api_with_helpful_fallback(
            files_url, "post", data={"name": filepath.name}, files={"file": upload_file}
        )

    if md5.hexdigest() != r.json()["checksum"]:
        raise ValueError(
            "The uploaded Zenodo's checksum does not match the local checksum.\n"
            f"  Zenodo's Checksum: {r.json()['checksum']}\n"
            f"  Local Checksum: {md5.hexdigest()}"
        )

    zenodo_api_with_helpful_fallback(
        deposition_url, "put", data=create_metadata(title, author), headers=headers
    )

    publish_url = f"{deposition_url}/actions/publish"
    r = zenodo_api_with_helpful_fallback(publish_url, "post")

    if r.status_code != 202:
        raise ValueError(
            f"Unexpected status code when publishing the file. Expected 202, got {r.status_code}."
        )
