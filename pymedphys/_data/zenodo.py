import json
import urllib.request

BASE_URL = "https://zenodo.org/api/records/"


def get_zenodo_file_urls(record_id):
    response = urllib.request.urlopen(f"{BASE_URL}{record_id}")
    data = json.loads(response.text)
    files = data["files"]
    urls = {record["key"]: record["links"]["self"] for record in files}

    return urls
