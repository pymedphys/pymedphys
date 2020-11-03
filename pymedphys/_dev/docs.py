import pathlib
import subprocess
import webbrowser

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
DOCS_DIR = ROOT.joinpath("docs")
DOCS_BUILD_DIR = DOCS_DIR.joinpath("_build")
DOCS_HTML_BUILD_DIR = DOCS_BUILD_DIR.joinpath("html")


def build_docs(args):
    webbrowser.open("http://127.0.0.1:8000")

    if args.live:
        subprocess.check_call(
            " ".join(
                [
                    "poetry",
                    "run",
                    "sphinx-autobuild",
                    str(DOCS_DIR),
                    str(DOCS_HTML_BUILD_DIR),
                ]
            ),
            shell=True,
        )

    else:
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
