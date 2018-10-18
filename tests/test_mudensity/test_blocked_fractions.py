import numpy as np

from pymedphys.level1.mudensity import calc_a_single_blocked_fraction


def a_single_mlc_pair(x, left_mlc_pos_start, left_mlc_pos_end, right_mlc_pos_start, right_mlc_pos_end):
    left_start_diffs = x - left_mlc_pos_start
    left_end_diffs = x - left_mlc_pos_end
    left_start_blocked = left_start_diffs <= 0
    left_end_blocked = left_end_diffs <= 0

    right_start_diffs = x - right_mlc_pos_start
    right_end_diffs = x - right_mlc_pos_end
    right_start_blocked = right_start_diffs >= 0
    right_end_blocked = right_end_diffs >= 0

    start_left_blocked_fraction, end_left_blocked_fraction = calc_a_single_blocked_fraction(
        left_start_diffs, left_end_diffs, left_start_blocked, left_end_blocked)

    start_right_blocked_fraction, end_right_blocked_fraction = calc_a_single_blocked_fraction(
        right_start_diffs, right_end_diffs, right_start_blocked, right_end_blocked)

    all_start_blocked_fractions = np.concatenate([
        np.expand_dims(start_left_blocked_fraction, axis=0), 
        np.expand_dims(start_right_blocked_fraction, axis=0)
    ], axis=0)

    all_end_blocked_fractions = np.concatenate([
        np.expand_dims(end_left_blocked_fraction, axis=0),
        np.expand_dims(end_right_blocked_fraction, axis=0)
    ], axis=0)

    start_blocked_fraction = np.max(all_start_blocked_fractions, axis=0)
    end_blocked_fraction = np.max(all_end_blocked_fractions, axis=0)

    blocked_fraction = start_blocked_fraction + end_blocked_fraction
    blocked_fraction[blocked_fraction > 1] = 1

    return blocked_fraction


def mlc_blocked_fraction(left_mlc_pos_start, left_mlc_pos_end, 
                         right_mlc_pos_start, right_mlc_pos_end, reference):
    x_coarse = np.linspace(-10, 10, 21)
    blocked_fraction_coarse = a_single_mlc_pair(
        x_coarse, left_mlc_pos_start, left_mlc_pos_end, right_mlc_pos_start, 
        right_mlc_pos_end)
    assert np.allclose(blocked_fraction_coarse, reference)


def test_thin_sweep():
    left_mlc_pos_start = -4
    left_mlc_pos_end = 1

    right_mlc_pos_start = -3.99
    right_mlc_pos_end = 1.01

    reference = np.array([
        1, 1, 1, 1, 1, 1, 1, 0.998, 0.998,
        0.998, 0.998, 0.998, 1, 1, 1, 1, 1, 1,
        1, 1, 1])

    mlc_blocked_fraction(
        left_mlc_pos_start, left_mlc_pos_end,
        right_mlc_pos_start, right_mlc_pos_end, reference)


def test_overlapping_sweep():
    left_mlc_pos_start = -2.3
    left_mlc_pos_end = 3.1

    right_mlc_pos_start = 0
    right_mlc_pos_end = 7.7

    reference = np.array([
        1, 1, 1, 1, 1, 1, 1, 1, 0.94444444, 0.75925926, 0.57407407, 0.51875902,
        0.46344396, 0.40812891, 0.51948052, 0.64935065, 0.77922078, 0.90909091,
        1, 1, 1])

    mlc_blocked_fraction(
        left_mlc_pos_start, left_mlc_pos_end,
        right_mlc_pos_start, right_mlc_pos_end, reference)
