import pathlib
import pydicom
import streamlit as st
import numpy as np
import plotly.graph_objects as go


st.set_page_config(layout="wide")

st.title("Interactive CT Slice Viewer")

DEFAULT_WINDOW_LEVEL = 0
DEFAULT_WINDOW_WIDTH = 500


def preprocess_ct_slice_datasets(ct_slice_datasets):
    """Preprocesses and caches common properties for CT slice datasets."""
    preprocessed_data = []
    for ds in ct_slice_datasets:
        preprocessed_data.append(
            {
                "SeriesInstanceUID": ds.SeriesInstanceUID,
                "ImagePositionPatient": ds.ImagePositionPatient,
                "ImageOrientationPatient": ds.ImageOrientationPatient,
                "PixelSpacing": ds.PixelSpacing,
                "Rows": ds.Rows,
                "Columns": ds.Columns,
                "PixelArray": ds.pixel_array,
                "RescaleSlope": ds.RescaleSlope,
                "RescaleIntercept": ds.RescaleIntercept,
            }
        )
    return preprocessed_data


# Updated checks to use preprocessed data
def _check_only_one_ct_series(preprocessed_data):
    series_uid = preprocessed_data[0]["SeriesInstanceUID"]
    if any(data["SeriesInstanceUID"] != series_uid for data in preprocessed_data[1:]):
        raise ValueError("At least one CT slice dataset is not from the same series")


def _check_all_slices_aligned(preprocessed_data):
    ref_position = preprocessed_data[0]["ImagePositionPatient"][:2]
    ref_orientation = preprocessed_data[0]["ImageOrientationPatient"]
    ref_spacing = preprocessed_data[0]["PixelSpacing"]

    for data in preprocessed_data[1:]:
        if data["ImagePositionPatient"][:2] != ref_position:
            raise ValueError("At least one CT slice dataset has a different position")
        if data["ImageOrientationPatient"] != ref_orientation:
            raise ValueError(
                "At least one CT slice dataset has a different orientation"
            )
        if data["PixelSpacing"] != ref_spacing:
            raise ValueError(
                "At least one CT slice dataset has a different pixel spacing"
            )


def compute_patient_coordinates(height, width, ipp, iop, pixel_spacing):
    """
    Compute patient coordinates efficiently using matrix multiplication.

    Args:
        height (int): Number of rows in the image.
        width (int): Number of columns in the image.
        ipp (list or ndarray): Image Position Patient (3D coordinates of the first pixel).
        iop (list or ndarray): Image Orientation Patient (cosines of row and column axes).
        pixel_spacing (list or ndarray): Spacing between pixels (row spacing, column spacing).

    Returns:
        tuple: X, Y coordinate arrays of shape (height, width).
    """
    ipp = np.array(ipp)
    iop = np.array(iop).reshape(2, 3)  # Reshape to 2x3 matrix (row_cosine, col_cosine)
    pixel_spacing = np.array(pixel_spacing)

    # Scale row and column cosines by pixel spacing
    iop_scaled = iop.T @ np.diag(pixel_spacing)  # Shape: (3, 2)

    # Create meshgrid of pixel indices
    jj, ii = np.meshgrid(np.arange(width), np.arange(height), indexing="xy")

    # Stack the pixel indices and compute physical coordinates
    indices = np.stack([jj.ravel(), ii.ravel()], axis=0)  # Shape: (2, height * width)
    coordinates = ipp[:, None] + iop_scaled @ indices  # Shape: (3, height * width)

    # Reshape coordinates to (height, width)
    X, Y = coordinates[0].reshape(height, width), coordinates[1].reshape(height, width)

    return X, Y


@st.cache_data(show_spinner=True, persist=True)
def load_ct_as_memmap(dirpath, memmap_file="ct_volume.dat"):
    """
    Load CT slices as a memory-mapped array and cache the operation.
    """
    dirpath = pathlib.Path(dirpath)

    ct_slice_datasets = []
    for fpath in dirpath.glob("*.dcm"):
        ds = pydicom.dcmread(fpath)
        if ds.Modality == "CT":
            ct_slice_datasets.append(ds)

    if not ct_slice_datasets:
        raise ValueError("No CT slices found in the provided directory.")

    preprocessed_data = preprocess_ct_slice_datasets(ct_slice_datasets)

    _check_only_one_ct_series(preprocessed_data)
    _check_all_slices_aligned(preprocessed_data)

    preprocessed_data.sort(key=lambda data: data["ImagePositionPatient"][2])

    num_slices = len(preprocessed_data)
    height = preprocessed_data[0]["Rows"]
    width = preprocessed_data[0]["Columns"]

    memmap_path = dirpath / memmap_file

    if not memmap_path.exists():
        memmap = np.memmap(
            memmap_path, dtype=np.int16, mode="w+", shape=(num_slices, height, width)
        )
        for i, data in enumerate(preprocessed_data):
            memmap[i, :, :] = (
                data["PixelArray"] * data["RescaleSlope"] + data["RescaleIntercept"]
            )
        memmap.flush()
    else:
        memmap = np.memmap(
            memmap_path, dtype=np.int16, mode="r", shape=(num_slices, height, width)
        )

    first_data = preprocessed_data[0]
    pixel_min = memmap.min()
    pixel_max = memmap.max()

    wl_default = int(first_data.get("WindowCenter", DEFAULT_WINDOW_LEVEL))
    ww_default = int(first_data.get("WindowWidth", DEFAULT_WINDOW_WIDTH))

    X, Y = compute_patient_coordinates(
        height,
        width,
        first_data["ImagePositionPatient"],
        first_data["ImageOrientationPatient"],
        first_data["PixelSpacing"],
    )

    ct_headers = [
        {
            "ipp": data["ImagePositionPatient"],
            "iop": data["ImageOrientationPatient"],
            "spacing": data["PixelSpacing"],
        }
        for data in preprocessed_data
    ]

    return memmap, ct_headers, X, Y, pixel_min, pixel_max, wl_default, ww_default


@st.cache_data(show_spinner=True, persist=True)
def load_rt_structures(fpath):
    """
    Load RT structures and cache based on the file path.
    """
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


def preprocess_contours(structures):
    """
    Precompute which contours belong to each Z-coordinate.

    Args:
        structures (dict): RT structure data.

    Returns:
        dict: Mapping of Z-coordinate to contours for each structure.
    """
    contour_map = {}
    for structure_name, structure_data in structures.items():
        for contour in structure_data["Contours"]:
            contour_z = contour[:, 2]
            unique_z = np.unique(contour_z)
            for z in unique_z:
                if z not in contour_map:
                    contour_map[z] = []
                contour_map[z].append((structure_name, contour))
    return contour_map


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


def initialize_base_figure(
    ct_image, ct_headers, X, Y, initial_slice_idx, wl_default, ww_default, structures
):
    """
    Initialize and cache the base figure for the CT viewer.

    Args:
        ct_image (np.ndarray): The CT image data.
        ct_headers (list): Headers containing metadata for each slice.
        X (np.ndarray): X coordinates of the image grid.
        Y (np.ndarray): Y coordinates of the image grid.
        initial_slice_idx (int): Index of the initial slice.
        wl_default (int): Default window level.
        ww_default (int): Default window width.
        structures (dict): RT structure data.

    Returns:
        go.Figure: The initialized Plotly figure.
    """
    height, width = ct_image.shape[1:]
    slice_image = ct_image[initial_slice_idx, :, :]
    windowed_img = window_image(slice_image, ww_default, wl_default)
    img_min = wl_default - (ww_default / 2)
    img_max = wl_default + (ww_default / 2)

    slice_z = ct_headers[initial_slice_idx]["ipp"][2]

    # Compute heatmap parameters
    x0 = X[0, 0]
    dx = X[0, 1] - X[0, 0]
    y0 = Y[0, 0]
    dy = Y[1, 0] - Y[0, 0]

    fig = go.Figure()
    heatmap = go.Heatmap(
        z=windowed_img,
        colorscale="gray",
        hovertemplate="HU: %{z}<extra></extra>",
        showscale=False,
        x0=x0,
        dx=dx,
        y0=y0,
        dy=dy,
        zmin=img_min,
        zmax=img_max,
    )
    fig.add_trace(heatmap)

    # Removed initial contour addition to allow dynamic toggling via checkboxes

    fig.update_layout(
        title=f"Z = {slice_z:.2f} mm (Slice {initial_slice_idx})",
        margin=dict(l=10, r=10, b=10, t=40),
        height=800,
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )

    # Set fixed aspect ratio for axes
    fig.update_xaxes(
        range=[x0, x0 + dx * width],
        scaleanchor="y",
        scaleratio=1,
        showgrid=False,
        zeroline=True,
        showline=True,
        linecolor="black",
        linewidth=1,
    )
    fig.update_yaxes(
        range=[y0 + dy * height, y0],
        autorange=False,
        showgrid=False,
        zeroline=True,
        showline=True,
        linecolor="black",
        linewidth=1,
    )

    return fig


def update_figure(
    fig,
    ct_image,
    slice_idx,
    wl,
    ww,
    ct_headers,
    structures,
    contour_map,
    selected_structures,
):
    """
    Update the existing figure with new data based on user inputs.

    Args:
        fig (go.Figure): The existing Plotly figure.
        ct_image (np.ndarray): The CT image data.
        slice_idx (int): Index of the selected slice.
        wl (int): Window level.
        ww (int): Window width.
        ct_headers (list): Headers containing metadata for each slice.
        structures (dict): RT structure data.
        contour_map (dict): Precomputed mapping of contours to Z-coordinates.
        selected_structures (list): List of structure names to display.

    Returns:
        go.Figure: The updated Plotly figure.
    """
    slice_image = ct_image[slice_idx, :, :]
    windowed_img = window_image(slice_image, ww, wl)
    img_min = wl - (ww / 2)
    img_max = wl + (ww / 2)

    # Update heatmap trace
    fig.data[0].z = windowed_img
    fig.data[0].zmin = img_min
    fig.data[0].zmax = img_max

    # Update the title
    slice_z = ct_headers[slice_idx]["ipp"][2]
    fig.update_layout(title=f"Z = {slice_z:.2f} mm (Slice {slice_idx})")

    # Remove existing contour traces
    fig.data = tuple(
        trace
        for trace in fig.data
        if not (isinstance(trace, go.Scatter) and trace.name in structures.keys())
    )

    # Add new contour traces for the selected structures
    if slice_z in contour_map:
        for structure_name, contour in contour_map[slice_z]:
            if structure_name in selected_structures:
                x, y = contour[:, 0], contour[:, 1]
                colour = structures[structure_name]["Colour"]
                fig.add_trace(
                    go.Scatter(
                        x=x,
                        y=y,
                        mode="lines",
                        line=dict(color=colour, width=2),
                        name=structure_name,
                        showlegend=False,  # Legend is handled within checkboxes
                        hoverinfo="skip",
                    )
                )

    return fig


# Sidebar to upload DICOM directory and RTSTRUCT file
dicom_dir = st.sidebar.text_input("Enter DICOM directory path")
rtstruct_file = st.sidebar.text_input("Enter RTSTRUCT file path")

if pathlib.Path(dicom_dir).exists() and pathlib.Path(rtstruct_file).exists():
    ct_image, ct_headers, X, Y, pixel_min, pixel_max, wl_default, ww_default = (
        load_ct_as_memmap(pathlib.Path(dicom_dir))
    )
    structures = load_rt_structures(pathlib.Path(rtstruct_file))
    contour_map = preprocess_contours(structures)
else:
    st.error("Invalid directory or RTSTRUCT file path.")
    st.stop()

num_slices, height, width = ct_image.shape

# Sidebar controls for dynamic updates
with st.sidebar:
    st.header("Controls")

    # Slider to select Z coordinate
    slice_idx = st.slider(
        "Slice Index",
        min_value=0,
        max_value=num_slices - 1,
        value=num_slices // 2,
        step=1,
    )

    # Sliders for window level and width
    wl = st.slider(
        "Window Level (WL)",
        min_value=int(pixel_min),
        max_value=int(pixel_max),
        value=wl_default,
    )
    ww = st.slider(
        "Window Width (WW)",
        min_value=1,
        max_value=int(pixel_max - pixel_min),
        value=ww_default,
    )

    # Add checkboxes for each structure to toggle visibility with color indicators
    st.markdown("---")
    st.subheader("Toggle Structures")
    selected_structures = []
    for structure_name, structure_data in structures.items():
        # Create two columns: one for color box, one for checkbox
        col1, col2 = st.columns([1, 4])
        with col1:
            color = structure_data["Colour"]
            # Create a colored square using HTML and CSS
            st.markdown(
                f"""
                <div style="
                    width: 20px;
                    height: 20px;
                    background-color: {color};
                    border: 1px solid #000;
                    border-radius: 3px;
                "></div>
                """,
                unsafe_allow_html=True,
            )
        with col2:
            # Checkbox with the structure name
            if st.checkbox(structure_name, value=True, key=structure_name):
                selected_structures.append(structure_name)

    # Removed separate legend as colors are now integrated with checkboxes
    st.markdown("---")


# Initialize the figure once
if "base_figure" not in st.session_state:
    initial_slice_idx = ct_image.shape[0] // 2
    st.session_state.base_figure = initialize_base_figure(
        ct_image,
        ct_headers,
        X,
        Y,
        initial_slice_idx,
        wl_default,
        ww_default,
        structures,
    )

# Update the figure based on user inputs, including selected structures
updated_fig = update_figure(
    st.session_state.base_figure,
    ct_image,
    slice_idx,
    wl,
    ww,
    ct_headers,
    structures,
    contour_map,
    selected_structures,  # Pass the selected structures to the update function
)

# Display the updated figure
st.plotly_chart(updated_fig, use_container_width=True, height=800)
