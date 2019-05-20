# pylint: disable=import-error

import os
from glob import glob

from js import window, Promise

from pymedphys_fileformats.trf.trf2dcm import trf2dcm


def run_trf2dcm():
    def run_promise(resolve, reject):
        try:
            dcm_template_filepath = glob(os.path.join('/input', '*.dcm'))[0]
            trf_filepath = glob(os.path.join('/input', '*.trf'))[0]
            gantry_angle = -120  # TODO: Make this customisable within app
            output_dir = '/output'
            trf2dcm(dcm_template_filepath, trf_filepath,
                    gantry_angle, output_dir)
            resolve()
        except Exception as e:
            reject(e)
            raise

    return Promise.new(run_promise)


run_trf2dcm()
