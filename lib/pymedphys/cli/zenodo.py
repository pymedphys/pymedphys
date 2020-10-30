import pymedphys._data.zenodo


def zenodo_cli(subparsers):
    zenodo_parser = subparsers.add_parser("zenodo")
    zenodo_subparsers = zenodo_parser.add_subparsers(dest="zenodo")
    zenodo_set_token(zenodo_subparsers)

    return zenodo_subparsers


def zenodo_set_token(zenodo_subparsers):
    parser = zenodo_subparsers.add_parser("set-token")

    parser.add_argument("token")
    parser.set_defaults(
        func=pymedphys._data.zenodo.set_zenodo_access_token_cli  # pylint: disable = protected-access
    )
