import pathlib
import sys

from cefpython3 import cefpython as cef

HERE = pathlib.Path(__file__).resolve().parent


def main():
    sys.excepthook = cef.ExceptHook

    switches = {
        "disable-web-security": "",
        "file_access_from_file_urls_allowed": "",
        "universal_access_from_file_urls_allowed": "",
    }
    cef.Initialize(switches=switches)

    entry_point = HERE.joinpath("build", "index.html")
    url = f"file://{entry_point}"
    print(url)

    cef.CreateBrowserSync(url=url)
    cef.MessageLoop()
    cef.Shutdown()


if __name__ == "__main__":
    main()
