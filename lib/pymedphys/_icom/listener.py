import logging
import pathlib
import re
import socket
import time
import traceback

from . import patients

BUFFER_SIZE = 256
ICOM_PORT = 1706


def save_an_icom_batch(
    date_pattern, ip_directory, data_to_save, *, restricted_logs: bool = False
):
    if not date_pattern.match(data_to_save[8:26]):
        raise ValueError("Unexpected iCOM stream format")

    counter = str(int(data_to_save[26])).zfill(3)
    filepath = ip_directory.joinpath(f"{counter}.txt")

    with open(filepath, "bw+") as f:
        f.write(data_to_save)

    if restricted_logs:
        logging.debug("Saved iCOM stream batch")
    else:
        logging.debug("Saved stream to %(filepath)s", {"filepath": filepath})


def get_start_location_from_date_span(span):
    return span[0] - 8


def initialise_socket(ip, *, restricted_logs: bool = False):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((ip, ICOM_PORT))
    s.settimeout(10)
    if restricted_logs:
        logging.info("iCOM socket connected")
    else:
        logging.info(s)

    return s


def listen(ip, data_dir, *, restricted_logs: bool = False):
    date_pattern = re.compile(rb"\d\d\d\d-\d\d-\d\d\d\d:\d\d:\d\d")

    data_dir = pathlib.Path(data_dir)
    live_dir = data_dir.joinpath("live")
    patients_dir = data_dir.joinpath("patients")

    patient_icom_data = patients.PatientIcomData(
        patients_dir, restricted_logs=restricted_logs
    )

    def archive_by_patient(ip, data):
        patient_icom_data.update_data(ip, data)

    ip_directory = live_dir.joinpath(ip)
    ip_directory.mkdir(exist_ok=True, parents=True)

    s = initialise_socket(ip, restricted_logs=restricted_logs)

    try:
        data = b""

        while True:
            try:
                data += s.recv(BUFFER_SIZE)
            except socket.timeout:
                logging.warning("Socket connection timed out, retrying connection")
                if restricted_logs:
                    logging.info("Closing timed-out iCOM socket")
                else:
                    logging.info(s)
                s.close()
                if not restricted_logs:
                    logging.info(s)
                s = initialise_socket(ip, restricted_logs=restricted_logs)
                continue

            matches = date_pattern.finditer(data)
            try:
                span = next(matches).span()
            except StopIteration:
                continue

            previous_start_location = get_start_location_from_date_span(span)
            for match in matches:
                new_start_location = get_start_location_from_date_span(match.span())
                data_to_save = data[previous_start_location:new_start_location]

                save_an_icom_batch(
                    date_pattern,
                    ip_directory,
                    data_to_save,
                    restricted_logs=restricted_logs,
                )
                archive_by_patient(ip, data_to_save)

                previous_start_location = new_start_location

            data = data[previous_start_location::]

    finally:
        s.close()
        if restricted_logs:
            logging.info("iCOM socket closed")
        else:
            logging.info(s)


def listen_cli(args):
    while True:
        try:
            listen(args.ip, args.directory, restricted_logs=args.restricted_logs)
        except KeyboardInterrupt:
            raise
        except:  # pylint: disable = bare-except  # noqa: E722
            traceback.print_exc()

        logging.warning(
            "The iCOM listener dropped out. Will wait 15 minutes, and "
            "then retry connection."
        )

        time.sleep(60 * 15)
