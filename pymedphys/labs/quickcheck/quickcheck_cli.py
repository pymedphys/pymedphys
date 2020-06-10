import logging
import sys

from .qcheck import QuickCheck


def export_cli(args):
    """
    expose a cli to allow export of Quickcheck data to csv
    """

    ip = args.ip
    csv_path = args.csv_path
    verbose = args.verbose

    # Create a logger to std out for cli
    log_level = logging.INFO
    logger = logging.getLogger(__name__)
    if verbose:
        log_level = logging.DEBUG
    logger.setLevel(log_level)

    ch = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    ch.setFormatter(formatter)
    ch.setLevel(log_level)
    logger.addHandler(ch)

    qc = QuickCheck(ip)
    qc.connect()
    if qc.connected:
        qc.get_measurements()
        print("Saving data to " + csv_path)
        qc.close()
        qc.measurements.to_csv(csv_path)
