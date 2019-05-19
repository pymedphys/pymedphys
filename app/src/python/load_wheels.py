# pylint: disable=import-error


import hashlib
import importlib
import io
import json
from pathlib import Path
import zipfile

from distlib import markers, util, version

from js import Promise, window, XMLHttpRequest, pyodide as js_pyodide
import pyodide


def _nullop(*args):
    return


def get_url(url):
    def run_promise(resolve, reject):
        def callback(data):
            resolve(data)

        _get_url_async(url, callback)

    return Promise.new(run_promise)


def _get_url_async(url, cb):
    req = XMLHttpRequest.new()
    req.open('GET', url, True)
    req.responseType = 'arraybuffer'

    def callback(e):
        if req.readyState == 4:
            cb(io.BytesIO(req.response))

    req.onreadystatechange = callback
    req.send(None)


WHEEL_BASE = Path('/lib/python3.7/site-packages/').parent


def extract_wheel(fd):
    with zipfile.ZipFile(fd) as zf:
        zf.extractall(WHEEL_BASE)

    importlib.invalidate_caches()


def validate_wheel(data, sha256):
    m = hashlib.sha256()
    m.update(data.getvalue())
    if m.hexdigest() != sha256:
        raise ValueError("Contents don't match hash")


def get_package_no_validation(url):
    def do_install(resolve, reject):
        def run_promise(wheel):
            try:
                extract_wheel(wheel)
            except Exception as e:
                reject(str(e))
            else:
                resolve()

        get_url(url).then(run_promise)
        importlib.invalidate_caches()

    return Promise.new(do_install)


def get_package(url, sha256):
    def do_install(resolve, reject):
        def callback(wheel):
            try:
                validate_wheel(wheel, sha256)
                extract_wheel(wheel)
            except Exception as e:
                reject(str(e))
            else:
                resolve()

        _get_url_async('https://cors-anywhere.herokuapp.com/' + url, callback)
        importlib.invalidate_caches()

    return Promise.new(do_install)


def load_and_copy_wheels():
    def run_promise(resolve, reject):
        def extract_all_wheels(filenames_json):
            filenames = json.load(filenames_json)

            for filename in filenames:
                print('Loading {} from python-wheels'.format(
                    filename.split('-')[0]))

            urls = [
                '/python-wheels/{}'.format(filename)
                for filename in filenames
            ]

            promises = []
            for url in urls:
                promises.append(get_package_no_validation(url))

            Promise.all(promises).then(resolve)

        get_url('/python-wheels/filenames.json').then(extract_all_wheels)

    return Promise.new(run_promise)


def get_packages(pypi_data):
    promises = []
    for key, package_data in pypi_data.items():
        print('Loading {} from pypi'.format(key))
        promises.append(get_package(*package_data))

    return Promise.all(promises)


pypi_data = {
    'pydicom': (
        'https://files.pythonhosted.org/packages/97/ae/93aeb6ba65cf976a23e735e9d32b0d1ffa2797c418f7161300be2ec1f1dd/pydicom-1.2.0-py2.py3-none-any.whl',
        '2132a9b15a927a1c35a757c0bdef30c373c89cc999cf901633dcd0e8bdd22e84'
    ),
    'packaging': (
        'https://files.pythonhosted.org/packages/91/32/58bc30e646e55eab8b21abf89e353f59c0cc02c417e42929f4a9546e1b1d/packaging-19.0-py2.py3-none-any.whl',
        '9e1cbf8c12b1f1ce0bb5344b8d7ecf66a6f8a6e91bcb0c84593ed6d3ab5c4ab3'
    ),
    'Rx': (
        'https://files.pythonhosted.org/packages/33/0f/5ef4ac78e2a538cc1b054eb86285fe0bf7a5dbaeaac2c584757c300515e2/Rx-1.6.1-py2.py3-none-any.whl',
        '7357592bc7e881a95e0c2013b73326f704953301ab551fbc8133a6fadab84105'
    )
}

get_packages(pypi_data).then(
    lambda _: load_and_copy_wheels()
).then(
    lambda _: window['wheelsReady'].next(True)
)
