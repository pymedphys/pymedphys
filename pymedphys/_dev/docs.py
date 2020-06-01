import hashlib
import pathlib
import shutil
import subprocess

import pymedphys._data.upload
import pymedphys._data.zenodo

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
DOCS_DIR = ROOT.joinpath("docs")
DOCS_BUILD_DIR = DOCS_DIR.joinpath("_build")
DOCS_HTML_BUILD_DIR = DOCS_BUILD_DIR.joinpath("html")


def build_docs(args):
    subprocess.check_call(
        " ".join(
            [
                "poetry",
                "run",
                "sphinx-build",
                "-W",
                str(DOCS_DIR),
                str(DOCS_HTML_BUILD_DIR),
            ]
        ),
        shell=True,
    )

    if args.publish:
        publish_docs_to_zenodo()


def publish_docs_to_zenodo():
    docs_filename = "html.zip"

    zip_path = DOCS_BUILD_DIR.joinpath(docs_filename)
    shutil.make_archive(zip_path.with_suffix(""), "zip", DOCS_HTML_BUILD_DIR)

    record_name = "docs"
    md5s = pymedphys._data.zenodo.get_zenodo_file_md5s(  # pylint: disable = protected-access
        record_name
    )
    zenodo_md5 = md5s[docs_filename]

    local_md5 = hashlib.md5()
    with open(zip_path, "rb") as f:
        local_md5.update(f.read())

    if local_md5.hexdigest() == zenodo_md5:
        print("Zenodo's version matches the built version on disk. Skipping upload.")
        return

    record_id = pymedphys._data.upload.upload_zenodo_file(  # pylint: disable = protected-access
        zip_path, "PyMedPhys Docs", record_name=record_name
    )

    pymedphys._data.zenodo.update_zenodo_record_id(  # pylint: disable = protected-access
        record_name, record_id
    )

    print("Published")
