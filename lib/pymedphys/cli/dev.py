import pathlib
import sys

from pymedphys._dev import docs, propagate, tests, tg263_edition_check
from pymedphys._dev.deid_tables import edition_check
from pymedphys._dev.deid_tables import generate as deid_tables


def dev_cli(subparsers):
    dev_parser = subparsers.add_parser("dev")
    dev_subparsers = dev_parser.add_subparsers(dest="dev")
    add_docs_parser(dev_subparsers)
    add_test_parser(dev_subparsers)
    add_lint_parser(dev_subparsers)
    add_propagate_parser(dev_subparsers)
    add_deid_tables_parser(dev_subparsers)
    add_deid_matrix_parser(dev_subparsers)
    add_tg263_check_parser(dev_subparsers)
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
            "of DICOM PS3.15, PS3.6, and PS3.16, after checking each source page's "
            "SHA-256 digest."
        ),
    )
    parser.add_argument(
        "--source-dir",
        help=(
            "Read the source pages from this directory, laid out as NEMA's "
            "output/ tree, instead of downloading them."
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
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check",
        action="store_true",
        help="Exit with status 1 if the tables in --output-dir are missing or differ.",
    )
    mode.add_argument(
        "--check-current",
        action="store_true",
        help=(
            "Generate the tables from NEMA's current edition, or from the pages "
            "in --source-dir, without checking the pinned digests or writing "
            "the tables, and compare each table's rows with those in "
            "--output-dir. Lists the tables that would change and the pages "
            "that could not be fetched or parsed, without quoting them. Exits "
            "with status 0 if no table would change, 1 if a table would change, "
            "and 3 if a page could not be fetched or a table generated."
        ),
    )
    parser.add_argument(
        "--json",
        metavar="FILE",
        help="With --check-current, also write the result to FILE as JSON.",
    )
    parser.set_defaults(func=run_deid_tables)


def run_deid_tables(args):
    if args.check_current:
        edition_check.edition_check_cli(args)
    elif args.json:
        raise SystemExit("--json is only written with --check-current")
    else:
        deid_tables.deid_tables_cli(args)


def add_deid_matrix_parser(dev_subparsers):
    parser = dev_subparsers.add_parser(
        "deid-matrix",
        help=(
            "Generate the de-identification requirements-to-tests matrix from "
            "the requirements register, as Markdown, optionally with the "
            "outcomes in pytest JUnit XML reports."
        ),
    )
    parser.add_argument(
        "--register",
        help="The requirements register. Defaults to the one shipped with PyMedPhys.",
    )
    parser.add_argument(
        "--tests",
        metavar="ROOT",
        help=(
            "The directory whose tests directory holds the tests that cite "
            "the register's requirements with the deid_requirement marker, "
            "and that their node ids are relative to. Defaults to the "
            "pymedphys package."
        ),
    )
    parser.add_argument(
        "--junit",
        metavar="FILE",
        action="append",
        default=[],
        help=(
            "A pytest JUnit XML report (pytest --junitxml) whose outcomes the "
            "matrix gives. Repeat for each environment's report: a traced test "
            "fails if any of its cases failed in any report, and is partly run "
            "if a report lacks it or a case that another report ran."
        ),
    )
    parser.add_argument(
        "--output",
        metavar="FILE",
        help="Write the matrix to FILE instead of standard output.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "After writing the matrix, list on standard error each traced test "
            "that failed, was skipped, or did not run in the reports, and exit "
            "with status 1 if there is any."
        ),
    )
    parser.set_defaults(func=run_deid_matrix)


def run_deid_matrix(args):
    # Imported here so that other commands do not load the de-identification
    # package.
    from pymedphys._dicom.deidentify import requirements, traceability

    if args.check and not args.junit:
        raise SystemExit("--check needs at least one --junit report")
    try:
        register = requirements.load_requirements(
            pathlib.Path(args.register) if args.register else None,
            requirements.cited_tests(pathlib.Path(args.tests)) if args.tests else None,
        )
        matrix = traceability.build_matrix(
            register, [pathlib.Path(path) for path in args.junit], args.register
        )
    except (requirements.RequirementsError, traceability.TraceabilityError) as error:
        raise SystemExit(str(error)) from None
    markdown = traceability.render_markdown(matrix)
    if args.output:
        pathlib.Path(args.output).write_text(markdown, encoding="utf-8", newline="\n")
    else:
        sys.stdout.write(markdown)
    problems = matrix.problems() if args.check else ()
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        raise SystemExit(1)


def add_tg263_check_parser(dev_subparsers):
    parser = dev_subparsers.add_parser(
        "tg263-check",
        help=(
            "Check whether AAPM's TG-263 resource page links to a download "
            "not yet reviewed, no longer links to the pinned edition, or the "
            "pinned file has changed or gone. Exits with status 0 if nothing "
            "has changed, 1 if something has, and 3 if the page or the pinned "
            "file could not be fetched, or the page links to no download."
        ),
    )
    parser.add_argument(
        "--json",
        metavar="FILE",
        help="Also write the result to FILE as JSON.",
    )
    parser.set_defaults(func=tg263_edition_check.tg263_check_cli)


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
