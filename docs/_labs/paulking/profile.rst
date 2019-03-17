Profile Class
=============


``pymedphys._labs.paulking.profile.Profile(x=[], data=[], metadata={})``


.. py:class:: pymedphys._labs.paulking.profile.Profile

	.. automodule:: pymedphys._labs.paulking.profile

	**Example Use**

		| Create a profile and load it from a Profiler file
		| ``profile = Profile().from_snc_profiler('C:\file.prs')``

		| Shift position right or left, scale it up or down
		| ``profile += 2``
		| ``profile = 2 * profiler``

		| Query values or extract sub-profiles
		| ``value_at_2cm = profile.get_data(2)``
		| ``dists_were_val_is_50 = profile.get_x(50)``
		| ``just_the_penumbra = profile.penumbra()``

		| Analyse and modify
		| ``left, right = profile.edges()``
		| ``symmetric = profile.symmetrise()``

		| Compare and report
		| ``film = Profile().from_narrow_png('C:\office_copier.png')``
		| ``profile.create_calibration(film).plot(marker='o')``

		.. image:: ./calib_curve.png


	**Methods**

	**Import ...**

		.. automethod:: from_lists
		.. automethod:: from_tuples
		.. automethod:: from_snc_profiler
		.. automethod:: from_narrow_png
		.. automethod:: from_pulse

	**Query ...**

		.. automethod:: get_increment
		.. automethod:: get_x
		.. automethod:: get_data

	**Extract ...**

		.. automethod:: segment
		.. automethod:: umbra
		.. automethod:: penumbra
		.. automethod:: shoulders
		.. automethod:: tails

	**Analyse ...**

		.. automethod:: edges
		.. automethod:: flatness
		.. automethod:: symmetry

	**Modify ...**

		.. automethod:: resample_x
		.. automethod:: resample_data
		.. automethod:: recentre
		.. automethod:: reversed
		.. automethod:: normalise_distance
		.. automethod:: normalise_dose
		.. automethod:: symmetrise

	**Compare ...**

		.. automethod:: overlay
		.. automethod:: create_calibration


	**Output ...**

		.. automethod:: plot
















