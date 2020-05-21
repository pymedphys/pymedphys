import pathlib
import re
import socket
import time
import traceback

BUFFER_SIZE = 256
ICOM_PORT = 1706


def save_an_icom_batch(date_pattern, ip_directory, data_to_save):
    if not date_pattern.match(data_to_save[8:26]):
        raise ValueError("Unexpected iCOM stream format")

    counter = str(int(data_to_save[26])).zfill(3)
    filepath = ip_directory.joinpath(f"{counter}.txt")

    with open(filepath, "bw+") as f:
        f.write(data_to_save)


def get_start_location_from_date_span(span):
    return span[0] - 8


def listen(ip, data_dir):
    date_pattern = re.compile(rb"\d\d\d\d-\d\d-\d\d\d\d:\d\d:\d\d")

    data_dir = pathlib.Path(data_dir)
    live_dir = data_dir.joinpath("live")
    ip_directory = live_dir.joinpath(ip)
    compressed_dir = data_dir.joinpath("compressed")

    ip_directory.mkdir(exist_ok=True, parents=True)
    compressed_dir.mkdir(exist_ok=True)

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((ip, ICOM_PORT))
    print(s)

    try:
        data = b""

        while True:
            data += s.recv(BUFFER_SIZE)

            matches = date_pattern.finditer(data)
            try:
                span = next(matches).span()
            except StopIteration:
                continue

            previous_start_location = get_start_location_from_date_span(span)
            for match in matches:
                new_start_location = get_start_location_from_date_span(match.span())
                save_an_icom_batch(
                    date_pattern,
                    ip_directory,
                    data[previous_start_location:new_start_location],
                )
                previous_start_location = new_start_location

            data = data[previous_start_location::]

    finally:
        s.close()
        print(s)


def listen_cli(args):
    while True:
        try:
            listen(args.ip, args.directory)
        except KeyboardInterrupt:
            raise
        except:  # pylint: disable = bare-except
            traceback.print_exc()

        print(
            "The iCOM listener dropped out. Will wait 15 minutes, and "
            "then retry connection."
        )

        time.sleep(60 * 15)
