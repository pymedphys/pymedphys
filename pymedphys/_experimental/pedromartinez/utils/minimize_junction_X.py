from pymedphys._imports import numpy as np

from scipy import signal
from scipy.signal import find_peaks

import matplotlib.pyplot as plt

from . import running_mean as rm


def minimize_junction_X(amplitude, peaks, peak_type, dx):
    print("Analyzing X jaws...")

    amp_prev = 0
    amp_filt_prev = 0

    fig = plt.figure(figsize=(10, 6))  # create the plot

    kk = 0  # counter for figure generation
    for j in range(0, amplitude.shape[1] - 1):
        for k in range(j + 1, amplitude.shape[1]):  # looping through remaining images
            amp_base_res = signal.convolve(
                amplitude[:, j], amplitude[:, j], mode="full"
            )
            amp_base_res = signal.resample(
                amp_base_res / np.amax(amp_base_res),
                int(np.ceil(len(amp_base_res) / 2)),
            )

            amp_overlay_res = signal.convolve(
                amplitude[:, k], amplitude[:, k], mode="full"
            )
            amp_overlay_res = signal.resample(
                amp_overlay_res / np.amax(amp_overlay_res),
                int(np.ceil(len(amp_overlay_res) / 2)),
            )
            peak1, _ = find_peaks(amp_base_res, prominence=0.5)
            peak2, _ = find_peaks(amp_overlay_res, prominence=0.5)

            if (
                abs(peak2 - peak1) < 2500
            ):  # if the two peaks are close together proceeed to analysis
                kk = kk + 1  # incrementing the figure generator
                cumsum_prev = 1e7
                if peak2 < peak1:  # this guarantee that we always slide the overlay
                    amp_base_res = amplitude[:, k]
                    amp_overlay_res = amplitude[:, j]
                else:
                    amp_base_res = amplitude[:, j]
                    amp_overlay_res = amplitude[:, k]

                if peak_type[j] == 0:
                    inc = -1
                else:
                    inc = 1
                for i in range(0, inc * 80, inc * 1):
                    # x = np.linspace(0, 0 + (len(amp_base_res) * dx), len(amplitude),
                    #                 endpoint=False)  # definition of the distance axis
                    amp_overlay_res_roll = np.roll(amp_overlay_res, i)

                    # amplitude is the vector to analyze +-500 samples from the center
                    amp_tot = (
                        amp_base_res[peaks[j] - 1000 : peaks[j] + 1000]
                        + amp_overlay_res_roll[peaks[j] - 1000 : peaks[j] + 1000]
                    )  # divided by 2 to normalize
                    # xsel = x[peaks[j] - 1000:peaks[j] + 1000]

                    amp_filt = rm.running_mean(amp_tot, 281)
                    cumsum = np.sum(np.abs(amp_tot - amp_filt))

                    if (  # pylint: disable = no-else-break
                        cumsum > cumsum_prev
                    ):  # then we went too far
                        break
                    else:
                        amp_prev = amp_tot
                        amp_filt_prev = amp_filt
                        cumsum_prev = cumsum

                ax = fig.add_subplot(amplitude.shape[1] - 1, 1, kk)
                ax.plot(amp_prev)
                ax.plot(amp_filt_prev)
                if kk == 1:
                    ax.set_title("Minimization result", fontsize=16)
                if (
                    kk == amplitude.shape[1] - 1
                ):  # if we reach the final plot the add the x axis label
                    ax.set_xlabel("distance [mm]")

                ax.set_ylabel("amplitude")
                # ax.annotate('delta=' + str(abs(i - inc * 1) * dx) + ' mm', xy=(2, 1), xycoords='axes fraction',
                #             xytext=(.35, .10))
                if peaks[kk - 1] != 0:
                    ax.annotate(
                        "delta=" + str(abs(i - inc * 1) * dx) + " mm",
                        xy=(2, 1),
                        xycoords="axes fraction",
                        xytext=(0.35, 0.10),
                    )
                else:
                    ax.annotate(
                        "delta= 0 mm (NO PEAK FOUND)",
                        xy=(2, 1),
                        xycoords="axes fraction",
                        xytext=(0.35, 0.10),
                    )

    return fig
