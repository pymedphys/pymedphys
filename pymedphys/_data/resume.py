# Adapted from https://www.oreilly.com/library/view/python-cookbook/0596001673/ch11s06.html


import functools
import pathlib
import urllib.request

from pymedphys._imports import tqdm


@functools.lru_cache()
def create_download_progress_bar():
    class DownloadProgressBar(tqdm.tqdm):
        def update_to(self, current_block=1, block_size=1):
            self.update(current_block * block_size - self.n)

    return DownloadProgressBar


class No206URLOpener(urllib.request.FancyURLopener):
    """ Subclass to override error 206 (partial file being sent); okay for us """

    def __init__(self, *args, **kwargs):
        urllib.request.FancyURLopener.__init__(self, *args, **kwargs)
        self.had_a_206 = False

    def http_error_206(
        self,
        url,  # pylint: disable = unused-argument
        fp,  # pylint: disable = unused-argument
        errcode,  # pylint: disable = unused-argument
        errmsg,  # pylint: disable = unused-argument
        headers,  # pylint: disable = unused-argument
        data=None,  # pylint: disable = unused-argument
    ):
        self.had_a_206 = True


def download_with_resume(url, filepath):
    exist_size = 0
    no_206_url_opener = No206URLOpener()
    filepath = pathlib.Path(filepath)

    if filepath.exists():
        open_mode = "ab"
        exist_size = filepath.stat().st_size
        no_206_url_opener.addheader("Range", f"bytes={exist_size}-")
    else:
        open_mode = "wb"

    with no_206_url_opener.open(url) as web_page:
        web_size = int(web_page.headers["Content-Length"])
        if web_size == exist_size:
            return

        if exist_size != 0 and not no_206_url_opener.had_a_206:
            raise ValueError("Resume not supported by server")

        if exist_size < web_size:

            with open(filepath, open_mode) as output_file:
                block_size = 8192
                current_block = exist_size // block_size

                DownloadProgressBar = create_download_progress_bar()
                with DownloadProgressBar(
                    unit="B", unit_scale=True, miniters=1, desc=str(filepath)
                ) as progress:
                    progress.total = web_size
                    while 1:
                        progress.update_to(
                            current_block=current_block, block_size=block_size
                        )
                        data = web_page.read(block_size)
                        if not data:
                            break
                        output_file.write(data)

                        current_block += 1

    exist_size = filepath.stat().st_size
    if exist_size < web_size:
        print(
            "Download was interupted. "
            f"Current file size: {exist_size}, download file size: {web_size}\n"
            "Resuming download..."
        )
        download_with_resume(url, filepath)

    if exist_size > web_size:
        with open(filepath, "rb+") as output_file:
            output_file.seek(web_size)
            output_file.truncate()
