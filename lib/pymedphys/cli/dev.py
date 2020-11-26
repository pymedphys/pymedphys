from pymedphys._dev import docs, propagate, tests


def dev_cli(subparsers):
    dev_parser = subparsers.add_parser("dev")
    dev_subparsers = dev_parser.add_subparsers(dest="dev")
    add_docs_parser(dev_subparsers)
    add_test_parser(dev_subparsers)
    add_propagate_parser(dev_subparsers)

    return dev_parser


def add_docs_parser(dev_subparsers):
    parser = dev_subparsers.add_parser("docs")

    parser.add_argument("--output", help="Custom output directory for the built docs.")
    parser.add_argument(
        "--clean", help="Delete all of the built files.", action="store_true"
    )

    parser.set_defaults(func=docs.build_docs)


def add_test_parser(test_subparsers):
    parser = test_subparsers.add_parser("tests")
    parser.set_defaults(func=tests.run_tests)


def add_propagate_parser(test_subparsers):
    parser = test_subparsers.add_parser("propagate")

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

    parser.set_defaults(func=propagate.propagate_all)
