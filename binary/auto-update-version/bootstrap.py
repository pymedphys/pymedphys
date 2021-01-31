import functools
import pathlib
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import traceback
import urllib.error
import urllib.request

import tqdm

PYTHON_ENVIRONMENT_POINTER = "https://bootstrap.pymedphys.com/python-urls/win-amd64"
GET_PYMEDPHYS_URL = "https://bootstrap.pymedphys.com/get-pymedphys.py"
HELP_URL = "https://bootstrap.pymedphys.com/help"


class DownloadProgressBar(tqdm.tqdm):
    def update_to(self, b=1, bsize=1, tsize=None):
        if tsize is not None:
            self.total = tsize
        self.update(b * bsize - self.n)


def retry(ExceptionToCheck, tries=4, delay=3, backoff=2):
    """Retry calling the decorated function using an exponential backoff."""

    def deco_retry(f):
        @functools.wraps(f)
        def f_retry(*args, **kwargs):
            mtries, mdelay = tries, delay
            while mtries > 1:
                try:
                    return f(*args, **kwargs)
                except ExceptionToCheck as e:
                    msg = "%s, Retrying in %d seconds..." % (str(e), mdelay)
                    print(msg)
                    time.sleep(mdelay)
                    mtries -= 1
                    mdelay *= backoff
            return f(*args, **kwargs)

        return f_retry  # true decorator

    return deco_retry


@retry((urllib.error.HTTPError, ConnectionResetError))
def download_with_progress(url, filepath, description):
    with DownloadProgressBar(
        unit="B", unit_scale=True, miniters=1, desc=description
    ) as t:
        urllib.request.urlretrieve(url, filepath, reporthook=t.update_to)


def main():
    print("Downloading installation files...")

    with tempfile.TemporaryDirectory() as temp_dir:
        get_pymedphys_filepath = pathlib.Path(temp_dir).joinpath("get-pymedphys.py")
        download_with_progress(
            GET_PYMEDPHYS_URL, get_pymedphys_filepath, "get-pymedphys.py"
        )

        python_environment_url = (
            urllib.request.urlopen(PYTHON_ENVIRONMENT_POINTER).read().decode()
        )
        python_environment_zip = pathlib.Path(temp_dir).joinpath("python.zip")
        download_with_progress(
            python_environment_url, python_environment_zip, "python-embed.zip"
        )

        python_environment_directory = pathlib.Path(temp_dir).joinpath("python")
        shutil.unpack_archive(python_environment_zip, python_environment_directory)
        python_exe = python_environment_directory.joinpath("python.exe")

        command = [str(python_exe), str(get_pymedphys_filepath)] + sys.argv[1:]
        try:
            subprocess.check_call(
                command,
                cwd=python_environment_directory,
            )
        except:
            with open(get_pymedphys_filepath) as f:
                get_pymedphys_contents = textwrap.indent(f.read(), "    ")

            contents_of_python_environment = list(
                python_environment_directory.glob("*")
            )

            help_text = urllib.request.urlopen(HELP_URL).read().decode()

            debug_information_string = textwrap.dedent(
                """\
                {help_text}

                Command called:

                    {command}

                Python environment URL:

                    {python_environment_url}

                get-pymedphys.py contents:

                {get_pymedphys_contents}

                python directory contents:

                    {contents_of_python_environment}

                The traceback of the error:

                {traceback}

                """
            ).format(
                help_text=help_text,
                command=" ".join(command),
                python_environment_url=python_environment_url,
                get_pymedphys_contents=get_pymedphys_contents,
                contents_of_python_environment=contents_of_python_environment,
                traceback=textwrap.indent(traceback.format_exc(), "    "),
            )
            print(debug_information_string)

            input("Press Enter to continue...")

            raise


if __name__ == "__main__":
    main()
