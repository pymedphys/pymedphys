"""Temporary: report what TCIA serves for MIDI-B, without DICOM values."""

import collections
import json
import re
import sys
import urllib.error
import urllib.request

PAGE = "https://www.cancerimagingarchive.net/collection/midi-b-test-midi-b-validation/"
APIS = (
    "https://services.cancerimagingarchive.net/nbia-api/services/v1",
    "https://services.cancerimagingarchive.net/nbia-api/services/v2",
)
HEADERS = {"User-Agent": "pymedphys-midi-b-discovery"}


def get(url, method="GET"):
    request = urllib.request.Request(url, headers=HEADERS, method=method)
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.status, dict(response.headers), (
                response.read() if method == "GET" else b""
            )
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers), b""
    except Exception as error:  # noqa: BLE001
        return type(error).__name__, {}, b""


status, _, body = get(PAGE)
print("page", status, len(body))
links = sorted(set(re.findall(rb'href="([^"]+)"', body)))
for link in links:
    text = link.decode("utf-8", "replace")
    if re.search(r"\.(db|zip|tcia|csv|xlsx|pdf|docx|sqlite|gz|7z)(\?|$)", text, re.I) or "uploads" in text or "nbia" in text.lower() or "aspera" in text.lower() or "faspex" in text.lower():
        head_status, head, _ = get(text, "HEAD")
        print("link", text, head_status, head.get("Content-Length"), head.get("Last-Modified"), head.get("ETag"))

for api in APIS:
    status, _, body = get(f"{api}/getCollectionValues")
    print("api", api, "getCollectionValues", status, len(body))
    names = []
    if status == 200:
        try:
            names = [entry.get("Collection") for entry in json.loads(body)]
        except ValueError:
            print("  not json")
    midi = sorted(name for name in names if name and "midi" in name.lower())
    print("  midi collections", midi)
    for name in midi:
        status, _, body = get(f"{api}/getSeries?Collection={name}&format=json")
        if status != 200:
            print("  ", name, "getSeries", status)
            continue
        series = json.loads(body)
        keys = sorted({key for entry in series for key in entry})
        modalities = collections.Counter(entry.get("Modality") for entry in series)
        images = sum(int(entry.get("ImageCount") or 0) for entry in series)
        size = sum(float(entry.get("FileSize") or 0) for entry in series)
        patients = len({entry.get("PatientID") for entry in series})
        print("  ", name, "series", len(series), "patients", patients, "images", images, "bytes", int(size))
        print("     keys", keys)
        print("     modalities", dict(modalities))
sys.exit(0)
