import json

from pymedphys._imports import requests

BASE_URL = "https://zenodo.org/api/records/"


def get_zenodo_file_urls(record_id):
    response = requests.get(f"{BASE_URL}{record_id}")
    data = json.loads(response.text)
    files = data["files"]
    urls = {record["key"]: record["links"]["self"] for record in files}

    return urls
