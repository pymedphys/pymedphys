import sys

from cefpython3 import cefpython as cef


def main():
    sys.excepthook = cef.ExceptHook

    switches = {"disable-web-security": ""}
    cef.Initialize(switches=switches)

    cef.CreateBrowserSync(url="file:///build/index.html")
    cef.MessageLoop()
    cef.Shutdown()


if __name__ == "__main__":
    main()
