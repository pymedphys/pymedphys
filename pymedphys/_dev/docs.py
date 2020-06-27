import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
DOCS_DIR = ROOT.joinpath("docs")
DOCS_BUILD_DIR = DOCS_DIR.joinpath("_build")
DOCS_HTML_BUILD_DIR = DOCS_BUILD_DIR.joinpath("html")


def build_docs(_):
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
