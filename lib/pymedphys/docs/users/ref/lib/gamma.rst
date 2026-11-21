#####
Gamma
#####

*******
Summary
*******

:func:`pymedphys.gamma` compares two dose grids with the gamma index. It
returns a :class:`pymedphys.GammaResult`, which holds the gamma values
together with the numbers of analysed and passing points and every setting
that was used, so that a percentage is never separated from its counts or
from the criteria behind it.

.. code-block:: python

    result = pymedphys.gamma(
        axes_reference, dose_reference, axes_evaluation, dose_evaluation, 3, 2
    )

    result.gamma  # gamma on the reference grid; NaN where a point was not analysed
    result.passed, result.analysed  # the counts behind the percentage
    result.percent_passed  # the percentage of analysed points with gamma <= 1
    result.settings  # every setting the calculation used

A list for either criterion gives a tuple with one result for each
combination. Each is exactly what a call with that pair alone returns.

.. code-block:: python

    results = pymedphys.gamma(
        axes_reference,
        dose_reference,
        axes_evaluation,
        dose_evaluation,
        [3, 2],
        [3, 2, 1],
    )

    for result in results:
        dose = result.settings.dose_criterion_percent
        distance = result.settings.distance_criterion_mm
        print(
            f"{dose:g}%/{distance:g} mm: {result.percent_passed:.1f}% "
            f"({result.passed} of {result.analysed})"
        )

The how-to guides :doc:`from DICOM files </users/howto/gamma/from-dicom>`,
:doc:`from 1D data </users/howto/gamma/1D-from-csv>` and
:doc:`speeding up a calculation </users/howto/gamma/speed-up>` are worked
examples.


***
API
***

.. autofunction:: pymedphys.gamma

Results
=======

.. autoclass:: pymedphys.GammaResult()
    :members: percent_passed

.. autoclass:: pymedphys.GammaSettings()

.. autoclass:: pymedphys.GammaProvenance()

Counting the points of a gamma array
====================================

A result carries its own counts. These functions count the points of any
other gamma array, such as the part of ``result.gamma`` within a region of
interest, by the same rules. Raising the lower dose cutoff, for example,
does not need a new calculation:

.. code-block:: python

    keep = dose_reference >= 0.5 * result.settings.normalisation_dose
    counts = pymedphys.gamma_pass_counts(np.where(keep, result.gamma, np.nan))

.. autofunction:: pymedphys.gamma_pass_counts

.. autofunction:: pymedphys.gamma_percent_passed

.. autoclass:: pymedphys.GammaPassCounts
    :members: percent_passed


**********************
Accuracy of the search
**********************

Gamma at a reference point is a minimum over the whole evaluation dose.
:func:`pymedphys.gamma` looks for it on shells of increasing radius around
the point, ``search_step_fraction`` of the distance criterion apart, with the
evaluation dose interpolated linearly at points the same distance apart on
each shell.

- The search can only overestimate gamma, because every point it samples is
  a candidate for the minimum. Too coarse a step therefore reports passing
  points as failing, never the reverse.
- Where the evaluation dose changes by :math:`G` dose criteria across one
  distance criterion, gamma can be overestimated by up to about
  ``search_step_fraction`` :math:`\times \sqrt{1 + G^2}`. The default step of
  0.1 keeps this small while :math:`G` is of order one. A tight dose
  criterion with a large distance criterion, such as 0.2%/4 mm, or a steep
  dose gradient makes :math:`G` large, and needs a smaller step.
- To check a result, lower ``search_step_fraction`` until the percentage
  passed stops changing.
- ``skip_once_passed=True`` stops the search for a point once its gamma is
  below 1. Which points pass is unchanged, but the gamma values of passing
  points are then upper bounds, not minima.


**************
What is stable
**************

Stable from version 0.42.0:

- the definition of gamma, and that a point passes when its gamma is at most
  1;
- NaN in ``result.gamma`` meaning that a point was not analysed;
- a call with lists of criteria returning what separate calls return;
- the documented attributes of the result classes and the options of
  :func:`pymedphys.gamma`.

Not promised:

- bit-identical gamma values between versions or platforms. Gamma is found
  by a search, and a better search can lower values.

Any change to the numbers that a default call returns is announced by a
warning in the changelog, and a new calculation method starts as an explicit
choice.

A result is a snapshot. Its arrays are read-only copies that share no memory
with the inputs, and they stay read-only when a result is copied or
unpickled; ``result.gamma.copy()`` gives an array that can be edited. Results
compare by identity. A pickled result is for use with the version of
PyMedPhys that made it.


**********************************
Moving from versions before 0.42.0
**********************************

Before version 0.42.0, ``pymedphys.gamma`` returned a NumPy array, or a
dictionary of arrays keyed by ``(dose, distance)`` when either criterion was
a list, and several options had other names.

.. list-table::
    :header-rows: 1
    :widths: 30 30 40

    * - Before
      - From 0.42.0
      - Notes
    * - ``dose_percent_threshold``
      - ``dose_criterion_percent``
      - Still the fifth positional argument.
    * - ``distance_mm_threshold``
      - ``distance_criterion_mm``
      - Still the sixth positional argument.
    * - ``lower_percent_dose_cutoff``
      - ``lower_dose_cutoff_percent``
      -
    * - ``local_gamma=False`` or ``True``
      - ``normalisation="global"`` or ``"local"``
      -
    * - ``global_normalisation``
      - ``normalisation_dose``
      -
    * - ``interp_fraction=10``
      - ``search_step_fraction=0.1``
      - The number inverts: one divided by the old value.
    * - ``interp_algo``
      - ``interpolator``
      -
    * - ``max_gamma``
      - ``gamma_cap``
      -
    * - ``ram_available``
      - ``memory_budget_bytes``
      -
    * - ``quiet``
      - removed
      - It had no effect. Configure :mod:`logging` to see progress messages.

Options after the two criteria must now be passed by keyword. A call that
uses an old name raises a ``TypeError`` that lists every replacement it
needs.

.. code-block:: python

    grids = (axes_reference, dose_reference, axes_evaluation, dose_evaluation)

    # Before
    gamma = pymedphys.gamma(
        *grids, 3, 2, lower_percent_dose_cutoff=10, local_gamma=True, max_gamma=2
    )
    valid = gamma[~np.isnan(gamma)]
    percent_passed = 100 * np.count_nonzero(valid <= 1) / valid.size

    # From 0.42.0
    result = pymedphys.gamma(
        *grids, 3, 2, lower_dose_cutoff_percent=10, normalisation="local", gamma_cap=2
    )
    gamma = result.gamma
    percent_passed = result.percent_passed
    print(f"{result.passed} of {result.analysed} analysed points passed")

    # Before, with lists of criteria
    gammas = pymedphys.gamma(*grids, [3, 2], [2, 1])
    gamma = gammas[(3, 1)]

    # From 0.42.0: a tuple, dose criteria varying slowest
    results = pymedphys.gamma(*grids, [3, 2], [2, 1])
    by_criteria = {
        (
            result.settings.dose_criterion_percent,
            result.settings.distance_criterion_mm,
        ): result
        for result in results
    }
    gamma = by_criteria[(3, 1)].gamma

A result is not an array. Code that passes it to a NumPy function, compares
it with an array, or indexes it raises a ``TypeError`` that says to use
``result.gamma``.

A list of criteria now gives, for each pair, exactly what a separate call
with that pair gives. Before version 0.42.0 the pairs of a list were searched
together, at steps finer than a pair with a larger distance criterion gets on
its own, so those pairs could report lower gamma values and higher pass rates
from a list than from a separate call.
