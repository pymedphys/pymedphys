import logging
import lzma
import pathlib

import pymedphys
from pymedphys._utilities.filesystem import encode_file_name

from . import extract, observer

# TODO: Convert logging to use lazy formatting
# see https://docs.python.org/3/howto/logging.html#optimization


class NoMUDelivered(ValueError):
    pass


class UnableToReadIcom(ValueError):
    pass


def validate_data(data_to_be_saved):
    logging.debug("Validating an iCOM dataset.")

    try:
        delivery = pymedphys.Delivery.from_icom(data_to_be_saved)
        logging.debug("iCOM dataset was found to be valid.")
    except Exception as _:
        logging.debug("Was not able to transform the iCOM dataset.")

        # Parser exceptions can contain patient identifiers from the iCOM bytes.
        raise UnableToReadIcom() from None

    if len(delivery.mu) == 0:
        logging.debug("Was able to read the iCOM dataset, but no MU was delivered.")

        raise NoMUDelivered()

    return delivery


def save_patient_data(start_timestamp, patient_data, output_dir: pathlib.Path):
    _, patient_id = extract.extract(patient_data[0], "Patient ID")

    logging.debug("Preparing an iCOM patient archive.")

    for data in patient_data:
        _, patient_name = extract.extract(data, "Patient Name")
        if patient_name is not None:
            break



    # Windows does not allow the double quotes that patient names can contain.
    patient_dir = output_dir.joinpath(encode_file_name(f"{patient_id}_{patient_name}"))
    patient_dir.mkdir(parents=True, exist_ok=True)



    reformatted_timestamp = (
        start_timestamp.replace(":", "").replace("T", "_").replace("-", "")
    )
    filename = patient_dir.joinpath(f"{reformatted_timestamp}.xz")

    data = b""
    for item in patient_data:
        data += item

    try:
        delivery = validate_data(data)
        logging.info(
            "Archiving an iCOM delivery with total MU %s.",
            round(delivery.mu[-1], 1),
        )
    except NoMUDelivered as _:
        logging.info("No MU delivered; not saving the iCOM record.")

        return

    except UnableToReadIcom as _:
        new_location = filename.parent.parent.joinpath(
            "unknown_error_in_record", filename.parent.name, filename.name
        )
        new_dir = new_location.parent
        new_dir.mkdir(parents=True, exist_ok=True)

        filename = new_location

        logging.warning(
            "Unable to parse iCOM delivery; archiving in the unknown-error folder."
        )

    with lzma.open(filename, "w") as f:
        f.write(data)


class PatientIcomData:
    def __init__(self, output_dir):
        self._data = {}
        self._usage_start = {}
        self._current_patient_data = {}
        self._output_dir = pathlib.Path(output_dir)

    def update_data(self, ip, data):
        try:
            if self._data[ip][-1][26] == data[26]:
                logging.warning("Skip this data item, duplicate of previous data item.")
                if self._data[ip][-1] != data:
                    raise ValueError("Duplicate ID, but not duplicate data!")

                return

            # Every iCOM data item has an index, this check here is
            # making sure that the currently received data item is
            # incremented by exactly one compared to the most recently
            # received data item.
            if (self._data[ip][-1][26] + 1) % 256 != data[26]:
                raise ValueError("Data stream appears to be arriving out of order")
            self._data[ip].append(data)
        except KeyError:
            self._data[ip] = [data]

        timestamp = data[8:26].decode()
        shrunk_data, patient_id = extract.extract(data, "Patient ID")
        shrunk_data, patient_name = extract.extract(shrunk_data, "Patient Name")
        shrunk_data, machine_id = extract.extract(shrunk_data, "Machine ID")
        logging.info("Received iCOM data item.")

        try:
            usage_start = self._usage_start[ip]
        except KeyError:
            usage_start = None

        if patient_id is not None:
            if usage_start is None:
                self._current_patient_data[ip] = []

                timestamp = data[8:26].decode()
                iso_timestamp = f"{timestamp[0:10]}T{timestamp[10::]}"
                self._usage_start[ip] = iso_timestamp

                logging.debug("Starting iCOM delivery data collection.")

            self._current_patient_data[ip].append(data)

            logging.debug("Appended an iCOM data item to current delivery.")

        elif usage_start is not None:
            logging.debug(
                "Delivery that started at %(usage_start)s appears to have completed.",
                {"usage_start": usage_start},
            )

            try:
                save_patient_data(
                    usage_start, self._current_patient_data[ip], self._output_dir
                )
            except OSError:
                # A delivery that cannot be archived must not stop the
                # recording of the deliveries that follow it.
                # OSError may contain the archive path, which embeds a patient ID/name.
                logging.error(
                    "Could not archive the delivery that started at %s.",
                    usage_start,
                )
            finally:
                self._current_patient_data[ip] = None
                self._usage_start[ip] = None

        else:
            logging.debug("No delivery is currently being recorded.")


def archive_by_patient(directories_to_watch, output_dir):
    patient_icom_data = PatientIcomData(output_dir)

    def archive_by_patient_callback(ip, data):
        patient_icom_data.update_data(ip, data)

    observer.observe_with_callback(directories_to_watch, archive_by_patient_callback)
