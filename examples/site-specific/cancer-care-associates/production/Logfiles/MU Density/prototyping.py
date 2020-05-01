import functools
import os
import pathlib
import re
import sys
import traceback

import numpy as np
import pandas as pd

import matplotlib.pyplot as plt

import imageio

import pydicom

import IPython.display
import pymedphys
from pymedphys._mosaiq.helpers import FIELD_TYPES

GRID = pymedphys.mudensity.grid()
COORDS = (GRID["jaw"], GRID["mlc"])


PERCENT_DEVIATION = 2
MM_DIST_THRESHOLD = 0.5


@functools.lru_cache()
def get_delivery_tel_file(filepath):
    delivery_tel = pymedphys.Delivery.from_monaco(filepath)

    return delivery_tel


@functools.lru_cache()
def get_delivery_trf_file(filepath):
    delivery_trf = pymedphys.Delivery.from_logfile(filepath)

    return delivery_trf


@functools.lru_cache()
def get_mu_density_from_file(filepath):
    if filepath.suffix == ".trf":
        delivery = get_delivery_trf_file(filepath)
    elif filepath.name == "tel.1":
        delivery = pymedphys.Delivery.from_monaco(filepath)
    else:
        raise ValueError("Not appropriate file type found")

    mudensity = delivery.mudensity()

    return mudensity


@functools.lru_cache()
def calc_gamma(mudensity_tel, mudensity_trf):
    gamma = pymedphys.gamma(
        COORDS,
        mudensity_tel,
        COORDS,
        mudensity_trf,
        PERCENT_DEVIATION,
        MM_DIST_THRESHOLD,
        local_gamma=True,
        quiet=True,
        max_gamma=2,
    )

    return gamma


def plot_gamma_hist(gamma, percent, dist):
    valid_gamma = gamma[~np.isnan(gamma)]

    plt.hist(valid_gamma, 50, density=True)
    pass_ratio = np.sum(valid_gamma <= 1) / len(valid_gamma)

    plt.title(
        "Local Gamma ({0}%/{1}mm) | Percent Pass: {2:.2f} % | Max Gamma: {3:.2f}".format(
            percent, dist, pass_ratio * 100, np.max(valid_gamma)
        )
    )


def to_tuple(array):
    return tuple(map(tuple, array))


def markdown_print(string):
    IPython.display.display(IPython.display.Markdown(string))


def plot_and_save_results(
    mudensity_tel,
    mudensity_trf,
    gamma,
    png_filepath,
    pdf_filepath,
    header_text="",
    footer_text="",
):
    diff = mudensity_trf - mudensity_tel
    largest_item = np.max(np.abs(diff))

    widths = [1, 1]
    heights = [0.3, 1, 1, 1, 0.1]
    gs_kw = dict(width_ratios=widths, height_ratios=heights)

    fig, axs = plt.subplots(5, 2, figsize=(10, 16), gridspec_kw=gs_kw)
    gs = axs[0, 0].get_gridspec()

    for ax in axs[0, 0:]:
        ax.remove()

    for ax in axs[1, 0:]:
        ax.remove()

    for ax in axs[4, 0:]:
        ax.remove()

    axheader = fig.add_subplot(gs[0, :])
    axhist = fig.add_subplot(gs[1, :])
    axfooter = fig.add_subplot(gs[4, :])

    axheader.axis("off")
    axfooter.axis("off")

    axheader.text(0, 0, header_text, ha="left", wrap=True, fontsize=30)
    axfooter.text(0, 1, footer_text, ha="left", va="top", wrap=True, fontsize=6)

    plt.sca(axs[2, 0])
    pymedphys.mudensity.display(GRID, mudensity_tel)
    axs[2, 0].set_title("Monaco Plan")

    plt.sca(axs[2, 1])
    pymedphys.mudensity.display(GRID, mudensity_trf)
    axs[2, 1].set_title("Logfile Result")

    plt.sca(axs[3, 0])
    pymedphys.mudensity.display(
        GRID, diff, cmap="seismic", vmin=-largest_item, vmax=largest_item
    )
    plt.title("Logfile - Monaco")

    plt.sca(axs[3, 1])
    pymedphys.mudensity.display(GRID, gamma, cmap="coolwarm", vmin=0, vmax=2)
    plt.title(f"Local Gamma | {PERCENT_DEVIATION}%/{MM_DIST_THRESHOLD}mm")

    plt.sca(axhist)
    plot_gamma_hist(gamma, PERCENT_DEVIATION, MM_DIST_THRESHOLD)

    return fig


def get_incomplete_qcls(cursor, location):
    data = pymedphys.mosaiq.execute(
        cursor,
        """
        SELECT
            Ident.IDA,
            Patient.Last_Name,
            Patient.First_Name,
            Chklist.Due_DtTm,
            Chklist.Instructions,
            Chklist.Notes,
            QCLTask.Description
        FROM Chklist, Staff, QCLTask, Ident, Patient
        WHERE
            Chklist.Pat_ID1 = Ident.Pat_ID1 AND
            Patient.Pat_ID1 = Ident.Pat_ID1 AND
            QCLTask.TSK_ID = Chklist.TSK_ID AND
            Staff.Staff_ID = Chklist.Rsp_Staff_ID AND
            Staff.Last_Name = %(location)s AND
            Chklist.Complete = 0
        """,
        {"location": location},
    )

    results = pd.DataFrame(
        data=data,
        columns=[
            "patient_id",
            "last_name",
            "first_name",
            "due",
            "instructions",
            "comment",
            "task",
        ],
    )

    results = results.sort_values(by=["due"], ascending=False)

    return results


def get_patient_fields(cursor, patient_id):
    """Returns all of the patient fields for a given Patient ID.
    """
    patient_id = str(patient_id)

    patient_field_results = pymedphys.mosaiq.execute(
        cursor,
        """
        SELECT
            TxField.FLD_ID,
            TxField.Field_Label,
            TxField.Field_Name,
            TxField.Version,
            TxField.Meterset,
            TxField.Type_Enum,
            Site.Site_Name
        FROM Ident, TxField, Site
        WHERE
            TxField.Pat_ID1 = Ident.Pat_ID1 AND
            TxField.SIT_Set_ID = Site.SIT_Set_ID AND
            Ident.IDA = %(patient_id)s
        """,
        {"patient_id": patient_id},
    )

    table = pd.DataFrame(
        data=patient_field_results,
        columns=[
            "field_id",
            "field_label",
            "field_name",
            "field_version",
            "monitor_units",
            "field_type",
            "site",
        ],
    )

    table.drop_duplicates(inplace=True)

    table["field_type"] = [FIELD_TYPES[item] for item in table["field_type"]]

    return table
