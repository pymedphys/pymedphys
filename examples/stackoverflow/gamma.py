# Posted at https://stackoverflow.com/a/32978931/3912576

if __name__ == "__main__":

    import os

    os.system("pip install numpy scipy pydicom")

    import pydicom
    import pymedphys

    reference_filepath = pymedphys.data_path("original_dose_beam_4.dcm")
    evaluation_filepath = pymedphys.data_path("logfile_dose_beam_4.dcm")

    reference = pydicom.read_file(str(reference_filepath), force=True)
    evaluation = pydicom.read_file(str(evaluation_filepath), force=True)

    axes_reference, dose_reference = pymedphys.dicom.zyx_and_dose_from_dataset(
        reference
    )
    axes_evaluation, dose_evaluation = pymedphys.dicom.zyx_and_dose_from_dataset(
        evaluation
    )

    gamma_options = {
        "dose_percent_threshold": 1,  # This is a bit overkill here at 1%/1mm
        "distance_mm_threshold": 1,
        "lower_percent_dose_cutoff": 20,
        "interp_fraction": 10,  # Should be 10 or more, see the paper referenced above
        "max_gamma": 2,
        "random_subset": None,  # Can be used to get quick pass rates
        "local_gamma": True,  # Change to false for global gamma
        "ram_available": 2**29,  # 1/2 GB
    }

    gamma = pymedphys.gamma(
        axes_reference,
        dose_reference,
        axes_evaluation,
        dose_evaluation,
        **gamma_options
    )
