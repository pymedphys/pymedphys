from pymedphys._dev import docs, propagate, tests


def dev_cli(subparsers):
    dev_parser = subparsers.add_parser("dev")
    dev_subparsers = dev_parser.add_subparsers(dest="dev")
    add_docs_parser(dev_subparsers)
    add_test_parser(dev_subparsers)
    add_lint_parser(dev_subparsers)
    add_propagate_parser(dev_subparsers)
    add_doctests_parser(dev_subparsers)
    add_cypress_parser(dev_subparsers)
    add_clean_imports_parser(dev_subparsers)
    add_mosaiq_mssql_parser(dev_subparsers)

    return dev_parser


def add_docs_parser(dev_subparsers):
    parser = dev_subparsers.add_parser("docs")

    parser.add_argument("--output", help="Custom output directory for the built docs.")
    parser.add_argument(
        "--clean", help="Delete all of the built files.", action="store_true"
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
        "--copies",
        help="Only propagate the file copying tasks. This is much quicker.",
        action="store_true",
    )

    parser.add_argument(
        "--pyproject",
        help="Only propagate the dependencies of pyproject.",
        action="store_true",
    )

    parser.add_argument(
        "--update",
        help="Run poetry update first.",
        action="store_true",
    )

    parser.set_defaults(func=propagate.propagate_all)


def add_cypress_parser(dev_subparsers):
    parser = dev_subparsers.add_parser("cypress")
    parser.set_defaults(func=tests.run_cypress)


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
