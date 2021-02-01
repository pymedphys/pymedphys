from pymedphys._imports import streamlit as st

from pymedphys._experimental.chartchecks.helpers import get_all_dicom_treatment_info


def main():
    file = "C:/Users/rembishj/Documents/raystation_plan/RP1.2.752.243.1.1.20210123122119948.1140.13064.dcm"

    plan = get_all_dicom_treatment_info(file)

    st.write(plan)


if __name__ == "__main__":
    main()
