import pathlib
import subprocess
import webbrowser

LIBRARY_ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS_DIR = LIBRARY_ROOT.joinpath("docs")
DOCS_BUILD_DIR = DOCS_DIR.joinpath("_build")
DOCS_HTML_BUILD_DIR = DOCS_BUILD_DIR.joinpath("html")


def build_docs(args):
    subprocess.check_call(
        "pandoc CHANGELOG.md --from markdown --to rst -s -o release-notes.rst",
        cwd=DOCS_DIR,
        shell=True,
    )

    if args.output:
        output_directory = args.output
    else:
        output_directory = str(DOCS_HTML_BUILD_DIR)

    if args.live:
        webbrowser.open("http://127.0.0.1:8000")

        subprocess.check_call(
            " ".join(["sphinx-autobuild", str(DOCS_DIR), output_directory]), shell=True
        )

    else:
        subprocess.check_call(
            " ".join(["sphinx-build", "-W", str(DOCS_DIR), output_directory]),
            shell=True,
        )
