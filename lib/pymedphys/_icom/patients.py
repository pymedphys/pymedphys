import logging
import lzma
import pathlib
import traceback

import pymedphys
from pymedphys._utilities.filesystem import encode_file_name

from . import extract, observer

# TODO: Convert logging to use lazy formatting
# see https://docs.python.org/3/howto/logging.html#optimization


def _progress_log(level, restricted_logs: bool, local_message, restricted_message, *args):
    """Preserve protected-local diagnostics unless restricted logging is selected."""
    if restricted_logs:
        logging.log(level, restricted_message)
    else:
        logging.log(level, local_message, *args)


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


def save_patient_data(
    start_timestamp, patient_data, output_dir: pathlib.Path, *, restricted_logs: bool = False
):
    _, patient_id = extract.extract(patient_data[0], "Patient ID")

    _progress_log(
        logging.DEBUG,
        restricted_logs,
        "When preparing patient record to be saved, the patient id was %(patient_id)s",
        "Preparing iCOM delivery record for archiving",
        {"patient_id": patient_id},
    )

    for data in patient_data:
        _, patient_name = extract.extract(data, "Patient Name")
        if patient_name is not None:
            break

    _progress_log(
        logging.DEBUG,
        restricted_logs,
        "When preparing patient record to be saved, the patient name was "
        "%(patient_name)s",
        "Preparing iCOM delivery record for archiving",
        {"patient_name": patient_name},
    )

    # Windows does not allow the double quotes that patient names can contain.
    patient_dir = output_dir.joinpath(encode_file_name(f"{patient_id}_{patient_name}"))
    patient_dir.mkdir(parents=True, exist_ok=True)

    _progress_log(
        logging.DEBUG,
        restricted_logs,
        "The patient archive directory to be used is %(patient_dir)s.",
        "iCOM archive directory created",
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
        _progress_log(
            logging.INFO,
            restricted_logs,
            f"Delivery with a total MU of {round(delivery.mu[-1], 1)} for "
            f"{patient_name} ({patient_id}) is being saved within {filename}.",
            "Saving iCOM delivery record",
        )
    except NoMUDelivered as _:
        _progress_log(
            logging.INFO,
            restricted_logs,
            "No MU delivered, not saving delivery data for "
            f"{patient_name} ({patient_id}).",
            "No MU delivered; iCOM delivery not archived",
        )

        return

    except UnableToReadIcom as _:
        new_location = filename.parent.parent.joinpath(
            "unknown_error_in_record", filename.parent.name, filename.name
        )
        new_dir = new_location.parent
        new_dir.mkdir(parents=True, exist_ok=True)

        filename = new_location

        _progress_log(
            logging.WARNING,
            restricted_logs,
            f"Unknown error within the record for {patient_name} ({patient_id}). "
            f"Will instead save the record within {str(filename)}.",
            "Unrecognised iCOM record; using fallback archive",
        )

    with lzma.open(filename, "w") as f:
        f.write(data)


class PatientIcomData:
    def __init__(self, output_dir, *, restricted_logs: bool = False):
        self._restricted_logs = restricted_logs
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

        shrunk_data, patient_id = extract.extract(data, "Patient ID")
        if self._restricted_logs:
            logging.info("iCOM acquisition data received")
        else:
            timestamp = data[8:26].decode()
            shrunk_data, patient_name = extract.extract(shrunk_data, "Patient Name")
            _, machine_id = extract.extract(shrunk_data, "Machine ID")
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

                _progress_log(
                    logging.DEBUG,
                    self._restricted_logs,
                    "Starting data collection for patient id %(patient_id)s. "
                    "Recording started at %(usage_start)s.",
                    "Started iCOM delivery collection",
                    {"usage_start": self._usage_start[ip], "patient_id": patient_id},
                )

            self._current_patient_data[ip].append(data)

            _progress_log(
                logging.DEBUG,
                self._restricted_logs,
                "iCOM stream appended to the data being collected for "
                "patient id %(patient_id)s.",
                "Appended iCOM data to active delivery",
                {"patient_id": patient_id},
            )

        elif usage_start is not None:
            _progress_log(
                logging.DEBUG,
                self._restricted_logs,
                "Delivery that started at %(usage_start)s appears to have completed.",
                "iCOM delivery collection appears complete",
                {"usage_start": usage_start},
            )

            try:
                save_patient_data(
                    usage_start,
                    self._current_patient_data[ip],
                    self._output_dir,
                    restricted_logs=self._restricted_logs,
                )
            except OSError:
                # A delivery that cannot be archived must not stop the
                # recording of the deliveries that follow it.
                if self._restricted_logs:
                    # OSError exception text can contain patient-bearing paths.
                    logging.error("Could not archive iCOM delivery")
                else:
                    logging.exception(
                        "Could not archive the delivery that started at %s.",
                        usage_start,
                    )
            finally:
                self._current_patient_data[ip] = None
                self._usage_start[ip] = None

        else:
            logging.debug("No delivery is currently being recorded.")


def archive_by_patient(directories_to_watch, output_dir, *, restricted_logs: bool = False):
    patient_icom_data = PatientIcomData(output_dir, restricted_logs=restricted_logs)

    def archive_by_patient_callback(ip, data):
        patient_icom_data.update_data(ip, data)

    observer.observe_with_callback(
        directories_to_watch, archive_by_patient_callback, restricted_logs=restricted_logs
    )
