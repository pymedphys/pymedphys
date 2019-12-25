# Adapted from https://www.oreilly.com/library/view/python-cookbook/0596001673/ch11s06.html


import os
import pathlib
import urllib.request

import tqdm


class DownloadProgressBar(tqdm.tqdm):
    def update_to(self, b=1, bsize=1, tsize=None):
        if tsize is not None:
            self.total = tsize
        self.update(b * bsize - self.n)


class myURLOpener(urllib.request.FancyURLopener):
    """ Subclass to override error 206 (partial file being sent); okay for us """

    def http_error_206(self, url, fp, errcode, errmsg, headers, data=None):
        pass  # Ignore the expected "non-error" code


def download_with_resume(url, filepath):
    exist_size = 0
    myUrlclass = myURLOpener()
    filepath = pathlib.Path(filepath)

    if filepath.exists():
        open_mode = "ab"
        exist_size = filepath.stat().st_size
        myUrlclass.addheader(f"Range", "bytes={exist_size}-")
    else:
        open_mode = "wb"

    with open(filepath, open_mode) as outputFile:
        with myUrlclass.open(url) as webPage:
            web_size = int(webPage.headers["Content-Length"])

            if web_size != exist_size:
                bsize = 8192
                current_loop = exist_size // bsize

                with DownloadProgressBar(
                    unit="B", unit_scale=True, miniters=1, desc=filepath.name
                ) as t:
                    while 1:
                        t.update_to(b=current_loop, bsize=bsize, tsize=web_size)
                        data = webPage.read(bsize)
                        if not data:
                            break
                        outputFile.write(data)

                        current_loop += 1
