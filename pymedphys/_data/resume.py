# Adapted from https://www.oreilly.com/library/view/python-cookbook/0596001673/ch11s06.html


import pathlib
import urllib.request

import tqdm


class DownloadProgressBar(tqdm.tqdm):
    def update_to(self, current_block=1, block_size=1, total_size=None):
        if total_size is not None:
            self.total = total_size
        self.update(current_block * block_size - self.n)


class No206URLopener(urllib.request.FancyURLopener):
    """ Subclass to override error 206 (partial file being sent); okay for us """

    def http_error_206(self, url, fp, errcode, errmsg, headers, data=None):
        pass  # Ignore the expected "non-error" code


def download_with_resume(url, filepath):
    exist_size = 0
    no_206_url_opener = No206URLopener()
    filepath = pathlib.Path(filepath)

    if filepath.exists():
        open_mode = "ab"
        exist_size = filepath.stat().st_size
        no_206_url_opener.addheader(f"Range", "bytes={exist_size}-")
    else:
        open_mode = "wb"

    with open(filepath, open_mode) as output_file:
        with no_206_url_opener.open(url) as wep_page:
            web_size = int(wep_page.headers["Content-Length"])

            if web_size != exist_size:
                block_size = 8192
                current_block = exist_size // block_size

                with DownloadProgressBar(
                    unit="B", unit_scale=True, miniters=1, desc=filepath.name
                ) as t:
                    while 1:
                        t.update_to(
                            current_block=current_block,
                            block_size=block_size,
                            total_size=web_size,
                        )
                        data = wep_page.read(block_size)
                        if not data:
                            break
                        output_file.write(data)

                        current_block += 1
