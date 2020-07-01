import numpy as np
from scipy import signal
from scipy.signal import find_peaks

import matplotlib.pyplot as plt


# this subroutine aims to find the peaks
def peak_find_fieldrot(ampl_resamp, dx, profilename):
    peaks = []
    peak_type = []
    for j in range(0, ampl_resamp.shape[1] - 1):
        amp_base_res = signal.convolve(
            ampl_resamp[:, j], ampl_resamp[:, j], mode="full"
        )
        amp_base_res = signal.resample(
            amp_base_res / np.amax(amp_base_res), int(np.ceil(len(amp_base_res) / 2))
        )

        for k in range(j + 1, ampl_resamp.shape[1]):
            amp_overlay_res = signal.convolve(
                ampl_resamp[:, k], ampl_resamp[:, k], mode="full"
            )
            amp_overlay_res = signal.resample(
                amp_overlay_res / np.amax(amp_overlay_res),
                int(np.ceil(len(amp_overlay_res) / 2)),
            )

            peak1, _ = find_peaks(amp_base_res, prominence=0.5)
            peak2, _ = find_peaks(amp_overlay_res, prominence=0.5)
            # print('peak find', peak1, peak2, abs(peak2 - peak1),len(amp_base_res))

            if (
                abs(peak2 - peak1) <= 4000
            ):  # if the two peaks are separated the two fields are not adjacent.
                amp_peak = ampl_resamp[:, j] + ampl_resamp[:, k]
                x = np.linspace(
                    0, 0 + (len(amp_peak) * dx / 10), len(amp_peak), endpoint=False
                )  # definition of the distance axis

                peak_pos, _ = find_peaks(
                    signal.savgol_filter(
                        amp_peak[min(peak1[0], peak2[0]) : max(peak1[0], peak2[0])],
                        201,
                        3,
                    ),
                    prominence=0.010,
                )
                pos_prominence = signal.peak_prominences(
                    signal.savgol_filter(
                        amp_peak[min(peak1[0], peak2[0]) : max(peak1[0], peak2[0])],
                        201,
                        3,
                    ),
                    peak_pos,
                )
                # print('#peaks pos det=', len(peak_pos), peak_pos)
                # print('#pos peaks prominence=', pos_prominence[0])
                peak_neg, _ = find_peaks(
                    signal.savgol_filter(
                        -amp_peak[min(peak1[0], peak2[0]) : max(peak1[0], peak2[0])],
                        201,
                        3,
                    ),
                    prominence=0.010,
                )
                neg_prominence = signal.peak_prominences(
                    signal.savgol_filter(
                        -amp_peak[min(peak1[0], peak2[0]) : max(peak1[0], peak2[0])],
                        201,
                        3,
                    ),
                    peak_neg,
                )
                # print('#peaks neg det=',len(peak_neg),peak_neg)
                # print('#neg peaks prominence=', neg_prominence[0])
                # we now need to select the peak with the largest prominence positve or negative
                # we add all the peaks and prominences toghether
                peaks_all = np.concatenate((peak_pos, peak_neg), axis=None)
                prom_all = np.concatenate(
                    (pos_prominence[0], neg_prominence[0]), axis=None
                )
                # print('all peaks',peaks_all,prom_all)
                peak = peaks_all[np.argmax(prom_all)]
                if peak.size != 0:
                    if peak in peak_pos:
                        peak_type.append(1)
                        peaks.append(min(peak1[0], peak2[0]) + peak)
                        # print('pos peak')
                    elif peak in peak_neg:
                        peak_type.append(0)
                        peaks.append(min(peak1[0], peak2[0]) + peak)
                        # print('neg peak')

                    fig = plt.figure(figsize=(10, 6))
                    plt.plot(
                        x, amp_peak, label="Total amplitude profile - " + profilename
                    )
                    plt.plot(
                        x[min(peak1[0], peak2[0]) + peak],
                        amp_peak[min(peak1[0], peak2[0]) + peak],
                        "x",
                        label="Peaks detected",
                    )
                    plt.ylabel("amplitude [a.u.]")
                    plt.xlabel("distance [mm]")
                    plt.legend()
                    fig.suptitle("Junctions - " + profilename, fontsize=16)

                elif peak.size == 0:
                    peaks.append(0)
                    peak_type.append(0)
                    print("no peak has been found")

            # else:
            # print(j, k, 'the data is not contiguous finding another curve in dataset')

    # print('peaks=',peaks)
    return peaks, peak_type, fig
