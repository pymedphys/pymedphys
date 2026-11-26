# Posted at https://stackoverflow.com/a/32978931/3912576

if __name__ == "__main__":
    import os

    os.system("pip install numpy scipy pydicom")

    import pydicom

    import pymedphys

    reference_filepath = pymedphys.data_path("original_dose_beam_4.dcm")
    evaluation_filepath = pymedphys.data_path("logfile_dose_beam_4.dcm")

    reference = pydicom.dcmread(str(reference_filepath), force=True)
    evaluation = pydicom.dcmread(str(evaluation_filepath), force=True)

    axes_reference, dose_reference = pymedphys.dicom.zyx_and_dose_from_dataset(
        reference
    )
    axes_evaluation, dose_evaluation = pymedphys.dicom.zyx_and_dose_from_dataset(
        evaluation
    )

    gamma_options = {
        "dose_criterion_percent": 1,  # This is a bit overkill here at 1%/1mm
        "distance_criterion_mm": 1,
        "lower_dose_cutoff_percent": 20,
        # Should be 0.1 or less, see the paper referenced above
        "search_step_fraction": 0.1,
        "gamma_cap": 2,
        "random_subset": None,  # Can be used to get quick pass rates
        "normalisation": "local",  # Change to "global" for global gamma
        "memory_budget_bytes": 2**29,  # 1/2 GB
    }

    result = pymedphys.gamma(
        axes_reference,
        dose_reference,
        axes_evaluation,
        dose_evaluation,
        **gamma_options,
    )

    # The gamma value at each point of the reference grid; NaN where the
    # reference dose is below the lower dose cutoff.
    gamma = result.gamma

    print(
        f"{result.percent_passed:.1f}% passed "
        f"({result.passed} of {result.analysed} analysed points)"
    )
