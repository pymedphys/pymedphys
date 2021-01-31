from pymedphys._imports import altair as alt
from pymedphys._imports import dicomparser, dvhcalc
from pymedphys._imports import pandas as pd
from pymedphys._imports import pydicom
from pymedphys._imports import streamlit as st


def main():
    files = st.file_uploader("select file to upload", accept_multiple_files=True)
    file = "P:/Share/Chris/Test_Patient/RS.1.3.46.670589.13.15476.20191204085114.491830"
    st.write(files)
    # st.write(bytes_data)

    ds_input: pydicom.FileDataset = pydicom.dcmread(files[1], force=True)

    dd_input: pydicom.FileDataset = pydicom.dcmread(files[0], force=True)

    rs = dicomparser.DicomParser(ds_input)

    st.write(rs.GetStructureInfo())
    struc = rs.GetStructures()
    st.write(struc)

    dvh_structures = {"name": [], "bincenters": [], "counts": [], "volume": []}
    # traces = []

    for i in range(1, len(struc) + 1):
        calcdvh = dvhcalc.get_dvh(ds_input, dd_input, i).from_data(binsize=10)
        dvh_structures["name"].append(calcdvh.name)
        dvh_structures["bincenters"].append(calcdvh.bincenters)
        dvh_structures["counts"].append(calcdvh.counts)
        dvh_structures["volume"].append(calcdvh.volume)
    #     ax.plot(structures[i]['bincenters'], structures[i]['counts']/structures[i]['volume'], label = calcdvh.name)
    #     ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left', borderaxespad=0.)
    # ax.set(ylim=(0,1))
    # st.pyplot(fig)
    data = pd.DataFrame.from_dict(dvh_structures)
    data["rel_volume"] = data["counts"] / data["volume"]

    source = data

    selection = alt.selection_multi(fields=["name"], bind="legend")

    plot = (
        alt.Chart(source)
        .mark_area()
        .encode(
            alt.X("bincenters:Q", axis=alt.Axis(domain=False, format="%Y", tickSize=0)),
            alt.Y("rel_volume:Q", stack="center", axis=None),
            alt.Color("name:N", scale=alt.Scale(scheme="category20b")),
            opacity=alt.condition(selection, alt.value(1), alt.value(0.2)),
        )
        .add_selection(selection)
    )

    st.write(plot)


if __name__ == "__main__":
    main()
