import logging
import lzma
import pathlib
import traceback

import pymedphys

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

        traceback.print_exc()
        raise UnableToReadIcom()

    if len(delivery.mu) == 0:
        logging.debug("Was able to read the iCOM dataset, but no MU was delivered.")

        raise NoMUDelivered()

    return delivery


def save_patient_data(start_timestamp, patient_data, output_dir: pathlib.Path):
    _, patient_id = extract.extract(patient_data[0], "Patient ID")

    logging.debug(
        "When preparing patient record to be saved, the patient id was "
        "%(patient_id)s",
        {"patient_id": patient_id},
    )

    for data in patient_data:
        _, patient_name = extract.extract(data, "Patient Name")
        if patient_name is not None:
            break

    logging.debug(
        "When preparing patient record to be saved, the patient name was "
        "%(patient_name)s",
        {"patient_name": patient_name},
    )

    patient_dir = output_dir.joinpath(f"{patient_id}_{patient_name}")
    patient_dir.mkdir(parents=True, exist_ok=True)

    logging.debug(
        "The patient archive directory to be used is %(patient_dir)s.",
        {"patient_dir": patient_dir},
    )

    reformatted_timestamp = (
        start_timestamp.replace(":", "").replace("T", "_").replace("-", "")
    )
    filename = patient_dir.joinpath(f"{reformatted_timestamp}.xz")

    data = b""
    for item in patient_data:
        data += item

    try:
        delivery = validate_data(data)
        logging.info(  # pylint: disable = logging-fstring-interpolation
            f"Delivery with a total MU of {round(delivery.mu[-1],1)} for "
            f"{patient_name} ({patient_id}) is being saved within "
            f"{filename}."
        )
    except NoMUDelivered as _:
        logging.info(  # pylint: disable = logging-fstring-interpolation
            "No MU delivered, not saving delivery data for "
            f"{patient_name} ({patient_id})."
        )

        return

    except UnableToReadIcom as _:
        new_location = filename.parent.parent.joinpath(
            "unknown_error_in_record", filename.parent.name, filename.name
        )
        new_dir = new_location.parent
        new_dir.mkdir(parents=True, exist_ok=True)

        filename = new_location

        logging.warning(  # pylint: disable = logging-fstring-interpolation
            "Unknown error within the record for "
            f"{patient_name} ({patient_id}). "
            f"Will instead save the record within {str(filename)}."
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
        logging.info(  # pylint: disable = logging-fstring-interpolation
            f"IP: {ip} | Timestamp: {timestamp} | "
            f"Patient ID: {patient_id} | "
            f"Patient Name: {patient_name} | Machine ID: {machine_id}"
        )

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

                logging.debug(
                    "Starting data collection for patient id %(patient_id)s. "
                    "Recording started at %(usage_start)s.",
                    {"usage_start": self._usage_start[ip], "patient_id": patient_id},
                )

            self._current_patient_data[ip].append(data)

            logging.debug(
                "iCOM stream appended to the data being collected for "
                "patient id %(patient_id)s.",
                {"patient_id": patient_id},
            )

        elif usage_start is not None:
            logging.debug(
                "Delivery that started at %(usage_start)s appears to "
                "have completed.",
                {"usage_start": usage_start},
            )

            save_patient_data(
                usage_start, self._current_patient_data[ip], self._output_dir
            )
            self._current_patient_data[ip] = None
            self._usage_start[ip] = None

        else:
            logging.debug("No delivery is currently being recorded.")


def archive_by_patient(directories_to_watch, output_dir):
    patient_icom_data = PatientIcomData(output_dir)

    def archive_by_patient_callback(ip, data):
        patient_icom_data.update_data(ip, data)

    observer.observe_with_callback(directories_to_watch, archive_by_patient_callback)
