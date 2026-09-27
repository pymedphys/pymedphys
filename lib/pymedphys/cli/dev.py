from pymedphys._dev import docs, propagate, tests
from pymedphys._dev.deid_tables import generate as deid_tables


def dev_cli(subparsers):
    dev_parser = subparsers.add_parser("dev")
    dev_subparsers = dev_parser.add_subparsers(dest="dev")
    add_docs_parser(dev_subparsers)
    add_test_parser(dev_subparsers)
    add_lint_parser(dev_subparsers)
    add_propagate_parser(dev_subparsers)
    add_deid_tables_parser(dev_subparsers)
    add_doctests_parser(dev_subparsers)
    add_clean_imports_parser(dev_subparsers)
    add_mosaiq_mssql_parser(dev_subparsers)

    return dev_parser


def add_docs_parser(dev_subparsers):
    parser = dev_subparsers.add_parser("docs")

    parser.add_argument("--output", help="Custom output directory for the built docs.")
    parser.add_argument(
        "--clean", help="Delete all of the built files.", action="store_true"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--prep",
        help="Undergo preparation steps for building with sphinx directly.",
        action="store_true",
    )
    mode.add_argument(
        "--linkcheck",
        help=(
            "Check external links instead of building HTML. Notebooks are not "
            "executed, so no data is downloaded. The report is written to "
            "_build/linkcheck, and the exit status is non-zero when a link "
            "fails."
        ),
        action="store_true",
    )

    parser.set_defaults(func=docs.build_docs)


def add_test_parser(dev_subparsers):
    parser = dev_subparsers.add_parser("tests")
    parser.set_defaults(func=tests.run_tests)


def add_lint_parser(dev_subparsers):
    parser = dev_subparsers.add_parser("lint")
    parser.set_defaults(func=tests.run_pylint)


def add_doctests_parser(dev_subparsers):
    parser = dev_subparsers.add_parser("doctests")
    parser.set_defaults(func=tests.run_doctests)


def add_propagate_parser(dev_subparsers):
    parser = dev_subparsers.add_parser("propagate")

    parser.add_argument(
        "--update",
        help="Run uv lock --upgrade first.",
        action="store_true",
    )

    parser.set_defaults(func=propagate.propagate_all)


def add_deid_tables_parser(dev_subparsers):
    parser = dev_subparsers.add_parser(
        "deid-tables",
        help=(
            "Generate the de-identification rule tables from the pinned edition "
            "of DICOM PS3.15, after checking each source page's SHA-256 digest."
        ),
    )
    parser.add_argument(
        "--source-dir",
        help=(
            "Read the source pages from this directory, laid out as NEMA's "
            "output/chtml/ tree, instead of downloading them."
        ),
    )
    parser.add_argument(
        "--output-dir",
        default=str(deid_tables.DEFAULT_OUTPUT_DIR),
        help=(
            "Where the tables are written or checked. Defaults to the "
            "package's _dicom/deidentify/_standard directory."
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit with status 1 if the tables in --output-dir are missing or differ.",
    )
    parser.set_defaults(func=deid_tables.deid_tables_cli)


def add_clean_imports_parser(dev_subparsers):
    parser = dev_subparsers.add_parser("imports")
    parser.set_defaults(func=tests.run_clean_imports)


def add_mosaiq_mssql_parser(dev_subparsers):
    parser = dev_subparsers.add_parser("mssql")
    parser.set_defaults(func=tests.start_mssql_docker)
    parser.add_argument(
        "--stop",
        action="store_true",
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
    )
