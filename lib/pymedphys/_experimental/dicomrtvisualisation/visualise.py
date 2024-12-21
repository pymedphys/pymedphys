import pathlib
import pydicom
import streamlit as st
import numpy as np
import plotly.graph_objects as go

# 1. Set Streamlit page configuration to 'wide' layout
st.set_page_config(layout="wide")

st.title("Interactive CT Slice Viewer (Optimized and Aligned)")


def _check_only_one_ct_series(ct_slice_datasets):
    if any(
        ds.SeriesInstanceUID != ct_slice_datasets[0].SeriesInstanceUID
        for ds in ct_slice_datasets[1:]
    ):
        raise ValueError("At least one CT slice dataset is not from the same series")


def _check_all_slices_aligned(ct_slice_datasets):
    if any(
        ds.ImagePositionPatient[:2] != ct_slice_datasets[0].ImagePositionPatient[:2]
        for ds in ct_slice_datasets[1:]
    ):
        raise ValueError("At least one CT slice dataset has a different position")

    if any(
        ds.ImageOrientationPatient != ct_slice_datasets[0].ImageOrientationPatient
        for ds in ct_slice_datasets[1:]
    ):
        raise ValueError("At least one CT slice dataset has a different orientation")

    if any(
        ds.PixelSpacing != ct_slice_datasets[0].PixelSpacing
        for ds in ct_slice_datasets[1:]
    ):
        raise ValueError("At least one CT slice dataset has a different pixel spacing")


def compute_patient_coordinates(height, width, ipp, iop, pixel_spacing):
    ipp = np.array(ipp)
    iop = np.array(iop)
    pixel_spacing = np.array(pixel_spacing)

    row_cosine = np.array(iop[0:3])
    col_cosine = np.array(iop[3:6])

    # Create meshgrid of pixel indices
    jj, ii = np.meshgrid(np.arange(width), np.arange(height))

    # Calculate the physical coordinates
    X = (
        ipp[0]
        + row_cosine[0] * jj * pixel_spacing[0]
        + col_cosine[0] * ii * pixel_spacing[1]
    )
    Y = (
        ipp[1]
        + row_cosine[1] * jj * pixel_spacing[0]
        + col_cosine[1] * ii * pixel_spacing[1]
    )

    return X, Y


@st.cache_data(show_spinner=False)
def load_ct_as_memmap(dirpath, memmap_file="ct_volume.dat"):
    dirpath = pathlib.Path(dirpath)

    ct_slice_datasets = []
    for fpath in dirpath.glob("*.dcm"):
        fullpath = dirpath / fpath
        ds = pydicom.dcmread(fullpath)
        if ds.Modality == "CT":
            ct_slice_datasets.append(ds)

    if not ct_slice_datasets:
        raise ValueError("No CT slices found in the provided directory.")

    _check_only_one_ct_series(ct_slice_datasets)
    _check_all_slices_aligned(ct_slice_datasets)

    ct_slice_datasets.sort(key=lambda ds: ds.ImagePositionPatient[2])

    num_slices = len(ct_slice_datasets)
    height = ct_slice_datasets[0].Rows
    width = ct_slice_datasets[0].Columns

    # Define the memmap file path relative to the directory
    memmap_path = dirpath / memmap_file

    # If the memmap file doesn't exist, create it
    if not memmap_path.exists():
        # Initialize the volume array
        volume = np.zeros((num_slices, height, width), dtype=np.int16)
        for i, ds in enumerate(ct_slice_datasets):
            volume[i, :, :] = ds.pixel_array * ds.RescaleSlope + ds.RescaleIntercept
        # Save to memmap file
        volume.tofile(memmap_path)
        del volume  # Ensure it's written to disk

    # Create a memory map of the file
    memmap = np.memmap(
        memmap_path, dtype=np.int16, mode="r", shape=(num_slices, height, width)
    )

    # Retrieve metadata from the first slice
    first_ds = ct_slice_datasets[0]
    pixel_min = memmap.min()
    pixel_max = memmap.max()

    if hasattr(first_ds, "WindowCenter"):
        wl_default = int(first_ds.WindowCenter)
    else:
        wl_default = int((pixel_min + pixel_max) / 2)

    if hasattr(first_ds, "WindowWidth"):
        ww_default = int(first_ds.WindowWidth)
    else:
        ww_default = int(pixel_max - pixel_min)

    X, Y = compute_patient_coordinates(
        height,
        width,
        first_ds.ImagePositionPatient,
        first_ds.ImageOrientationPatient,
        first_ds.PixelSpacing,
    )

    ct_headers = [
        {
            "ipp": ds.ImagePositionPatient,
            "iop": ds.ImageOrientationPatient,
            "spacing": ds.PixelSpacing,
        }
        for ds in ct_slice_datasets
    ]

    return memmap, ct_headers, X, Y, pixel_min, pixel_max, wl_default, ww_default


@st.cache_data(show_spinner=False)
def load_rt_structures(fpath):
    ds = pydicom.dcmread(fpath)
    if ds.Modality != "RTSTRUCT":
        raise ValueError("File is not an RTSTRUCT DICOM file")

    structures = {}
    roi_nums_to_names = {
        roi.ROINumber: roi.ROIName for roi in ds.StructureSetROISequence
    }
    for roi_contour in ds.ROIContourSequence:
        if not hasattr(roi_contour, "ContourSequence"):
            continue
        roi_name = roi_nums_to_names.get(roi_contour.ReferencedROINumber, "Unknown")

        contours = []
        for contour_seq in roi_contour.ContourSequence:
            contour_data = contour_seq.ContourData
            points = np.array(contour_data).reshape(-1, 3)
            contours.append(points)

        if contours:
            structures[roi_name] = {
                "Contours": contours,
                "Colour": f"rgb{tuple(np.uint8(c) for c in roi_contour.ROIDisplayColor)}",
                "Number": roi_contour.ReferencedROINumber,
            }
    return structures


def window_image(img, ww, wl):
    img_min = wl - (ww / 2)
    img_max = wl + (ww / 2)
    return np.clip(img, img_min, img_max)


def create_structure_legend(structures):
    """
    Creates an HTML legend for the structures with their corresponding colors.
    """
    legend_html = "<h4>Structures Legend</h4><ul>"
    for structure_name, structure_data in structures.items():
        color = structure_data["Colour"]
        # Convert 'rgb(r, g, b)' to individual r, g, b values
        rgb_values = color.replace("rgb(", "").replace(")", "").split(",")
        r, g, b = [int(v) for v in rgb_values]
        legend_html += f'<li><span style="display:inline-block;width:12px;height:12px;background-color:rgb({r},{g},{b});margin-right:6px;"></span>{structure_name}</li>'
    legend_html += "</ul>"
    return legend_html


# Define the directory containing DICOM files
TEST_DIRPATH = pathlib.Path(
    r"C:\Users\matth\Workspace\SlicerRtData\aria-phantom-contours-branching"
)
rtstruct_path = TEST_DIRPATH / "RS.PYTIM05_.dcm"

# Load data (memmapped volume)
ct_image, ct_headers, X, Y, pixel_min, pixel_max, wl_default, ww_default = (
    load_ct_as_memmap(TEST_DIRPATH)
)
structures = load_rt_structures(rtstruct_path)

num_slices, height, width = ct_image.shape

# Extract all unique Z coordinates
z_coords = np.array([header["ipp"][2] for header in ct_headers])

# Compute Heatmap parameters based on the first slice
x0 = X[0, 0]
dx = X[0, 1] - X[0, 0]
y0 = Y[0, 0]
dy = Y[1, 0] - Y[0, 0]

# Initialize the figure in session state if not already present
if "base_figure" not in st.session_state:
    # Default to the middle slice
    initial_slice_idx = num_slices // 2
    initial_wl = wl_default
    initial_ww = ww_default

    slice_image = ct_image[initial_slice_idx, :, :]
    windowed_img = window_image(slice_image, initial_ww, initial_wl)
    img_min = initial_wl - (initial_ww / 2)
    img_max = initial_wl + (initial_ww / 2)

    # Retrieve the corresponding Z coordinate
    slice_z = ct_headers[initial_slice_idx]["ipp"][2]

    # Initialize the Heatmap with the first slice
    fig = go.Figure()
    heatmap = go.Heatmap(
        z=windowed_img,
        colorscale="gray",
        hovertemplate="HU: %{z}<extra></extra>",
        showscale=False,  # Hide the main color scale
        x0=x0,
        dx=dx,
        y0=y0,
        dy=dy,
        zmin=img_min,
        zmax=img_max,
    )
    fig.add_trace(heatmap)

    # Add initial contours
    for structure_name, structure_data in structures.items():
        contours = structure_data["Contours"]
        colour = structure_data["Colour"]
        for contour in contours:
            contour_z = contour[:, 2]
            if np.allclose(contour_z, slice_z, atol=0.1):
                x = contour[:, 0]
                y = contour[:, 1]
                fig.add_trace(
                    go.Scatter(
                        x=x,
                        y=y,
                        mode="lines",
                        line=dict(color=colour, width=2),
                        name=structure_name,
                        showlegend=False,  # Disable legend in the main plot
                        hoverinfo="skip",
                    )
                )

    fig.update_layout(
        title=f"Z = {slice_z:.2f} mm (Slice {initial_slice_idx})",
        margin=dict(l=10, r=10, b=10, t=40),  # Reduced margins
        height=800,
        plot_bgcolor="rgba(0,0,0,0)",  # Transparent plot background
        paper_bgcolor="rgba(0,0,0,0)",  # Transparent paper background
    )

    # Set axes based on patient coordinates (fixed scales)
    fig.update_xaxes(
        range=[x0, x0 + dx * width],
        scaleanchor="y",
        scaleratio=1,
        showgrid=False,
        zeroline=True,
        showline=True,
        linecolor="black",
        linewidth=1,
        showticklabels=True,  # Enable tick labels if desired
        ticks="inside",  # Place ticks inside for tightness
    )
    fig.update_yaxes(
        range=[y0 + dy * height, y0],
        autorange=False,
        showgrid=False,
        zeroline=True,
        showline=True,
        linecolor="black",
        linewidth=1,
        showticklabels=True,  # Enable tick labels if desired
        ticks="inside",  # Place ticks inside for tightness
    )

    # Optionally, add axis titles as annotations to keep margins tight
    fig.add_annotation(
        x=x0 + dx * width / 2,
        y=y0 - dy * 0.5,  # Adjust y position as needed
        text="Patient X (mm)",
        showarrow=False,
        font=dict(size=12),
    )

    fig.add_annotation(
        x=x0 - dx * 0.5,  # Adjust x position as needed
        y=y0 + dy * height / 2,
        text="Patient Y (mm)",
        showarrow=False,
        font=dict(size=12),
        textangle=-90,
    )

    st.session_state.base_figure = fig
else:
    fig = st.session_state.base_figure

# User controls in the sidebar
with st.sidebar:
    st.header("Controls")
    # Slider to select Z coordinate
    min_z = z_coords.min()
    max_z = z_coords.max()
    step_z = np.abs(z_coords[1] - z_coords[0]) if num_slices > 1 else 1

    selected_z = st.slider(
        label="Select Z Coordinate (Slice Index: )",
        min_value=float(min_z),
        max_value=float(max_z),
        value=float(z_coords[num_slices // 2]),
        step=float(step_z),
    )

    # Find the closest slice index to the selected Z coordinate
    slice_idx = np.argmin(np.abs(z_coords - selected_z))
    closest_z = z_coords[slice_idx]

    wl = st.slider(
        "Window Level (WL)",
        min_value=int(pixel_min),
        max_value=int(pixel_max),
        value=int(wl_default),
        step=1,
    )

    ww = st.slider(
        "Window Width (WW)",
        min_value=1,
        max_value=int(pixel_max - pixel_min),
        value=int(ww_default),
        step=1,
    )

    st.markdown("---")  # Separator
    # Display the structure legend
    legend_html = create_structure_legend(structures)
    st.markdown(legend_html, unsafe_allow_html=True)

    st.markdown("---")  # Separator
    # Display current slice information
    st.markdown(f"**Current Slice:** {slice_idx} (Z = {closest_z:.2f} mm)")

# Update the Heatmap and Contours based on user input
slice_image = ct_image[slice_idx, :, :]
windowed_img = window_image(slice_image, ww, wl)
img_min = wl - (ww / 2)
img_max = wl + (ww / 2)

# Update Heatmap data
fig.data[0].z = windowed_img
fig.data[0].zmin = img_min
fig.data[0].zmax = img_max

# Update the plot title to include Z coordinate and slice index
fig.update_layout(title=f"Z = {closest_z:.2f} mm (Slice {slice_idx})")

# Remove old contour traces
fig.data = tuple(
    trace
    for trace in fig.data
    if not (isinstance(trace, go.Scatter) and trace.name in structures.keys())
)

# Add new contour traces for the selected slice
current_z = ct_headers[slice_idx]["ipp"][2]
for structure_name, structure_data in structures.items():
    contours = structure_data["Contours"]
    colour = structure_data["Colour"]
    for contour in contours:
        contour_z = contour[:, 2]
        if np.allclose(contour_z, current_z, atol=0.1):
            x = contour[:, 0]
            y = contour[:, 1]
            fig.add_trace(
                go.Scatter(
                    x=x,
                    y=y,
                    mode="lines",
                    line=dict(color=colour, width=2),
                    name=structure_name,
                    showlegend=False,  # Disable legend in the main plot
                    hoverinfo="skip",
                )
            )

# Display the main figure
st.plotly_chart(fig, use_container_width=True, height=800)
