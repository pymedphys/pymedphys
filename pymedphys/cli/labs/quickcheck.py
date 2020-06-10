"""Export csv data from QuickCheck measurements.
"""

from pymedphys.labs.quickcheck import export_cli


def quickcheck_cli(subparsers):
    quickcheck_parser = subparsers.add_parser(
        "quickcheck",
        help="A toolbox to retreive measurement data from PTW Quickcheck and write it to a csv file.",
    )
    quickcheck_subparsers = quickcheck_parser.add_subparsers(dest="quickcheck")

    export_quickcheck(quickcheck_subparsers)

    return quickcheck_parser


def export_quickcheck(quickcheck_subparsers):
    parser = quickcheck_subparsers.add_parser(
        "to-csv", help="Export Quickcheck data to .csv"
    )

    parser.add_argument(
        "ip", type=str, help="IP address or host name of Quickcheck device"
    )

    parser.add_argument("csv_path", type=str, help="file path for csv file.")

    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Flag to output debug information."
    )

    parser.set_defaults(func=export_cli)
