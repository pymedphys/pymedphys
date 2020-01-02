import pymedphys._dev.docs


def dev_cli(subparsers):
    dev_parser = subparsers.add_parser("dev")
    dev_subparsers = dev_parser.add_subparsers(dest="dev")
    docs(dev_subparsers)

    return dev_parser


def docs(dev_subparsers):
    parser = dev_subparsers.add_parser("docs")

    parser.add_argument("--publish", action="store_true")
    parser.set_defaults(
        func=pymedphys._dev.docs.build_docs  # pylint: disable = protected-access
    )
