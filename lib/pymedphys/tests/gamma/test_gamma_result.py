# Copyright (C) 2026 Matthew Jennings

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""The gamma result: a snapshot of the values, counts and settings."""

import copy
import dataclasses
import json
import pickle

from pymedphys._imports import numpy as np
from pymedphys._imports import pytest

import pymedphys
from pymedphys import GammaProvenance, GammaResult, GammaSettings
from pymedphys._gamma.result import build_result, current_provenance


def _settings(**changes):
    values = {
        "dose_criterion_percent": 3.0,
        "distance_criterion_mm": 2.0,
        "normalisation": "global",
        "normalisation_dose": 2.0,
        "normalisation_dose_supplied": False,
        "lower_dose_cutoff_percent": 20.0,
        "lower_dose_cutoff": 0.4,
        "exclude_nan_reference": False,
        "gamma_cap": None,
        "skip_once_passed": False,
        "random_subset": None,
        "random_source": None,
        "random_seed": None,
        "method": "shell",
        "search_step_fraction": 0.1,
        "interpolator": "pymedphys",
    }
    return GammaSettings(**{**values, **changes})


def _result(gamma=None, eligible=None, **settings):
    # Two rows of three points. One point was not analysed; of the other
    # five, gamma is at most 1 at three.
    if gamma is None:
        gamma = np.array([[0.2, 1.0, 1.5], [np.nan, 0.7, 2.5]])
    axes = (np.array([10.0, 20.0]), np.array([1.0, 2.0, 3.0]))
    if eligible is None:
        eligible = int(np.count_nonzero(~np.isnan(gamma)))
    return build_result(
        gamma=gamma, axes=axes, eligible=eligible, settings=_settings(**settings)
    )


def test_result_reports_values_coordinates_and_counts():
    result = _result()

    np.testing.assert_array_equal(result.gamma, [[0.2, 1.0, 1.5], [np.nan, 0.7, 2.5]])
    assert len(result.axes) == 2
    np.testing.assert_array_equal(result.axes[0], [10.0, 20.0])
    np.testing.assert_array_equal(result.axes[1], [1.0, 2.0, 3.0])
    assert (result.passed, result.analysed, result.eligible) == (3, 5, 5)
    assert result.percent_passed == pytest.approx(60)
    assert result.settings.dose_criterion_percent == 3.0
    assert result.provenance.versions["pymedphys"] == pymedphys.__version__


def test_eligible_points_can_outnumber_analysed_points():
    # A random subset analyses some of the eligible points.
    result = _result(eligible=6, random_subset=5, random_source="seed", random_seed=7)

    assert (result.analysed, result.eligible) == (5, 6)


def test_no_analysed_points_has_counts_but_no_percentage():
    result = _result(gamma=np.full((2, 3), np.nan))

    assert (result.passed, result.analysed, result.eligible) == (0, 0, 0)
    with pytest.raises(ValueError, match="No reference point was analysed"):
        _ = result.percent_passed
    assert "no points analysed" in repr(result)


def test_repr_names_the_counts_and_what_was_tested():
    text = repr(_result(normalisation="local", lower_dose_cutoff_percent=10.0))

    assert "60.0% passed (3 of 5 analysed)" in text
    assert "3%/2 mm" in text
    assert "local" in text
    assert "10% cutoff" in text
    assert "array" not in text


def test_arrays_are_read_only_and_owned():
    result = _result()

    for array in (result.gamma, *result.axes):
        assert not array.flags.writeable
        assert array.flags.owndata
        assert array.flags.c_contiguous
    with pytest.raises(ValueError, match="read-only"):
        result.gamma[0, 0] = 0
    # The flag cannot be put back through a hidden writeable base.
    assert result.gamma.base is None


def test_an_editable_copy_leaves_the_result_alone():
    result = _result()

    editable = result.gamma.copy()
    editable[np.isnan(editable)] = 0

    assert editable.flags.writeable
    assert np.isnan(result.gamma[1, 0])
    assert result.passed == 3


def test_result_does_not_share_memory_with_what_it_was_built_from():
    gamma = np.arange(12.0).reshape(2, 6)[:, ::2]  # a view that is not contiguous
    axes = (np.array([10.0, 20.0]), np.array([1.0, 2.0, 3.0]))

    result = build_result(gamma=gamma, axes=axes, eligible=6, settings=_settings())
    gamma[0, 0] = 99
    axes[0][0] = -1

    assert result.gamma[0, 0] == 0
    assert result.axes[0][0] == 10
    assert gamma.flags.writeable and axes[0].flags.writeable
    assert not np.shares_memory(result.gamma, gamma)
    assert not np.shares_memory(result.axes[0], axes[0])


@pytest.mark.parametrize(
    "clone",
    [
        lambda result: pickle.loads(pickle.dumps(result)),
        copy.copy,
        copy.deepcopy,
    ],
    ids=["pickle", "copy", "deepcopy"],
)
def test_copies_and_pickles_stay_read_only_snapshots(clone):
    result = _result()

    cloned = clone(result)

    np.testing.assert_array_equal(cloned.gamma, result.gamma)
    np.testing.assert_array_equal(cloned.axes[1], result.axes[1])
    assert not cloned.gamma.flags.writeable
    assert not cloned.axes[0].flags.writeable
    assert (cloned.passed, cloned.analysed, cloned.eligible) == (3, 5, 5)
    assert cloned.settings == result.settings
    assert cloned.provenance == result.provenance


def test_attributes_cannot_be_rebound():
    result = _result()

    with pytest.raises(dataclasses.FrozenInstanceError):
        result.passed = 5  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.settings.gamma_cap = 2.0  # type: ignore[misc]


def test_results_compare_by_identity():
    first, second = _result(), _result()

    assert first == first  # pylint: disable = comparison-with-itself
    assert first != second
    assert first in [second, first]
    assert len({first, second}) == 2


@pytest.mark.parametrize(
    "use",
    [
        np.isnan,
        np.nanmax,
        np.sum,
        np.shape,
        lambda result: np.ones((2, 3)) == result,
        lambda result: np.ones((2, 3)) <= result,
        pymedphys.gamma_pass_counts,
        pymedphys.gamma_percent_passed,
        lambda result: pymedphys.gamma_pass_counts((result, result)),
    ],
    ids=[
        "isnan",
        "nanmax",
        "sum",
        "shape",
        "array == result",
        "array <= result",
        "gamma_pass_counts",
        "gamma_percent_passed",
        "gamma_pass_counts of a tuple",
    ],
)
def test_treating_a_result_as_an_array_gives_directions(use):
    with pytest.raises(TypeError, match=r"result\.gamma"):
        use(_result())


def test_result_is_not_subscriptable():
    # Old code indexes an array, such as gamma[3, 3]. That must not be taken
    # for a lookup by criteria.
    with pytest.raises(TypeError, match="not subscriptable"):
        _ = _result()[0, 0]  # type: ignore[index]


def test_results_can_be_collected():
    results = (_result(), _result())

    assert np.array(results, dtype=object).shape == (2,)
    holder = np.empty(2, dtype=object)
    holder[:] = results
    assert holder[1] is results[1]


def test_gamma_that_does_not_match_the_axes_is_rejected():
    with pytest.raises(ValueError, match="shape"):
        build_result(
            gamma=np.zeros((3, 2)),
            axes=(np.array([10.0, 20.0]), np.array([1.0, 2.0, 3.0])),
            eligible=6,
            settings=_settings(),
        )


@pytest.mark.parametrize("eligible", [4, 7])
def test_inconsistent_counts_are_rejected(eligible):
    # Five points have a value, and the grid holds six.
    with pytest.raises(ValueError, match="eligible"):
        _result(eligible=eligible)


def test_settings_are_plain_values():
    settings = _settings(gamma_cap=2.0, random_subset=100, random_source="global")

    record = dataclasses.asdict(settings)

    assert json.loads(json.dumps(record)) == record
    assert record["gamma_cap"] == 2.0
    assert record["random_seed"] is None
    assert settings == _settings(
        gamma_cap=2.0, random_subset=100, random_source="global"
    )
    assert settings != _settings()
    assert len({settings, _settings()}) == 2


def test_settings_must_be_given_by_name():
    # pylint: disable = too-many-function-args, missing-kwoa
    with pytest.raises(TypeError):
        GammaSettings(3.0, 2.0)  # type: ignore[call-arg,misc]


def test_provenance_lists_installed_versions():
    provenance = current_provenance()

    assert provenance.versions["pymedphys"] == pymedphys.__version__
    assert provenance.versions["numpy"] == np.__version__
    assert set(provenance.versions) <= {"pymedphys", "numpy", "scipy", "numba"}
    assert list(provenance.versions)[0] == "pymedphys"


def test_installed_versions_are_read_once_for_the_process():
    # Reading package metadata costs more than a small gamma calculation.
    assert current_provenance() is current_provenance()

    axis = np.arange(3.0)
    first = pymedphys.gamma(axis, np.ones(3), axis, np.ones(3), 3, 1)
    second = pymedphys.gamma(axis, np.ones(3), axis, np.ones(3), 2, 1)

    assert first.provenance is second.provenance is current_provenance()


def test_provenance_versions_cannot_be_changed():
    source = {"pymedphys": "1.2.3"}
    provenance = GammaProvenance(versions=source)

    with pytest.raises(TypeError):
        provenance.versions["pymedphys"] = "9"  # type: ignore[index]
    source["pymedphys"] = "9"

    assert provenance.versions["pymedphys"] == "1.2.3"
    assert provenance == GammaProvenance(versions={"pymedphys": "1.2.3"})
    assert hash(provenance) == hash(GammaProvenance(versions={"pymedphys": "1.2.3"}))
    assert pickle.loads(pickle.dumps(provenance)) == provenance


def test_provenance_in_another_order_is_the_same_record():
    versions = {"pymedphys": "1.2.3", "numpy": "2.0.2", "scipy": "1.14.1"}
    provenance = GammaProvenance(versions=versions)
    reordered = GammaProvenance(versions=dict(reversed(versions.items())))

    assert reordered == provenance
    assert hash(reordered) == hash(provenance)
    assert len({provenance, reordered}) == 1
    assert {provenance: "found"}[reordered] == "found"
    assert list(reordered.versions) == ["scipy", "numpy", "pymedphys"]


def test_result_is_built_only_by_the_library():
    # The class takes keywords only, so that attributes can be added later.
    # pylint: disable = too-many-function-args, missing-kwoa
    result = _result()
    with pytest.raises(TypeError):
        GammaResult(result.gamma, result.axes)  # type: ignore[call-arg,misc]
