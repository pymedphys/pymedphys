# pylint: disable=import-error

from js import window, Promise


def run_user_code():
    def run_promise(resolve, reject):
        try:
            exec(window['pythonCode'].getValue())
            resolve()
        except Exception as e:
            reject(e)
            raise

    return Promise.new(run_promise)


run_user_code()
