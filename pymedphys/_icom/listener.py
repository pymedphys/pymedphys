import pathlib
import re
import socket

BUFFER_SIZE = 65536
ICOM_PORT = 1706


def listen(ip, data_dir):
    date_pattern = re.compile(rb"^\d\d\d\d-\d\d-\d\d\d\d:\d\d:\d\d$")

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
        while True:
            data = s.recv(BUFFER_SIZE)

            if not date_pattern.match(data[8:26]):
                raise ValueError("Unexpected iCOM stream format")

            counter = str(int(data[26])).zfill(3)
            filepath = ip_directory.joinpath(f"{counter}.txt")

            with open(filepath, "bw+") as f:
                f.write(data)

    finally:
        s.close()
        print(s)


def listen_cli(args):
    listen(args.ip, args.directory)
