from pymedphys._dev import docs, tests


def dev_cli(subparsers):
    dev_parser = subparsers.add_parser("dev")
    dev_subparsers = dev_parser.add_subparsers(dest="dev")
    add_docs_parser(dev_subparsers)
    add_test_parser(dev_subparsers)

    return dev_parser


def add_docs_parser(dev_subparsers):
    parser = dev_subparsers.add_parser("docs")

    parser.add_argument("--publish", action="store_true")
    parser.set_defaults(func=docs.build_docs)


def add_test_parser(test_subparsers):
    parser = test_subparsers.add_parser("tests")
    parser.set_defaults(func=tests.run_tests)
