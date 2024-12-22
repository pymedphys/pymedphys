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
    for idx, ds in enumerate(ct_slice_datasets):
        try:
            preprocessed_data.append(
                {
                    "SeriesInstanceUID": ds.SeriesInstanceUID,
                    "ImagePositionPatient": tuple(ds.ImagePositionPatient),
                    "ImageOrientationPatient": tuple(ds.ImageOrientationPatient),
                    "PixelSpacing": tuple(ds.PixelSpacing),
                    "Rows": ds.Rows,
                    "Columns": ds.Columns,
                    "PixelArray": ds.pixel_array,
                    "RescaleSlope": getattr(ds, "RescaleSlope", 1.0),
                    "RescaleIntercept": getattr(ds, "RescaleIntercept", 0.0),
                    "WindowCenter": getattr(ds, "WindowCenter", DEFAULT_WINDOW_LEVEL),
                    "WindowWidth": getattr(ds, "WindowWidth", DEFAULT_WINDOW_WIDTH),
                }
            )
        except AttributeError as e:
            st.warning(
                f"Missing attribute in CT slice {idx + 1}: {e}. This slice will be skipped."
            )
    if not preprocessed_data:
        raise ValueError("No valid CT slices found after preprocessing.")
    return preprocessed_data


def _check_only_one_ct_series(preprocessed_data):
    """Ensure all CT slices belong to the same series."""
    series_uid = preprocessed_data[0]["SeriesInstanceUID"]
    for idx, data in enumerate(preprocessed_data[1:], start=2):
        if data["SeriesInstanceUID"] != series_uid:
            raise ValueError(
                f"CT slice {idx} has a different SeriesInstanceUID. All slices must belong to the same series."
            )


def _check_all_slices_aligned(preprocessed_data):
    """Ensure all CT slices are aligned in position, orientation, and spacing."""
    ref_position = preprocessed_data[0]["ImagePositionPatient"][:2]
    ref_orientation = preprocessed_data[0]["ImageOrientationPatient"]
    ref_spacing = preprocessed_data[0]["PixelSpacing"]

    for idx, data in enumerate(preprocessed_data[1:], start=2):
        if data["ImagePositionPatient"][:2] != ref_position:
            raise ValueError(
                f"CT slice {idx} has a different ImagePositionPatient. All slices must be aligned."
            )
        if data["ImageOrientationPatient"] != ref_orientation:
            raise ValueError(
                f"CT slice {idx} has a different ImageOrientationPatient. All slices must have the same orientation."
            )
        if data["PixelSpacing"] != ref_spacing:
            raise ValueError(
                f"CT slice {idx} has a different PixelSpacing. All slices must have the same pixel spacing."
            )


@st.cache_data(show_spinner=False, persist=True)
def compute_patient_coordinates(
    height: int, width: int, ipp: tuple, iop: tuple, pixel_spacing: tuple
):
    """
    Compute patient coordinates efficiently using matrix multiplication.

    Args:
        height (int): Number of rows in the image.
        width (int): Number of columns in the image.
        ipp (tuple): Image Position Patient (3D coordinates of the first pixel).
        iop (tuple): Image Orientation Patient (cosines of row and column axes).
        pixel_spacing (tuple): Spacing between pixels (row spacing, column spacing).

    Returns:
        tuple: X, Y coordinate arrays of shape (height, width).
    """
    ipp = np.array(ipp)
    iop = np.array(iop).reshape(2, 3)  # Reshape to 2x3 matrix (row_cosine, col_cosine)
    pixel_spacing = np.array(pixel_spacing)

    # Scale row and column cosines by pixel spacing
    try:
        iop_scaled = iop.T @ np.diag(pixel_spacing)  # Shape: (3, 2)
    except ValueError as e:
        raise ValueError(f"Error in scaling IOP with Pixel Spacing: {e}") from e

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

    Args:
        dirpath (Path): Path to the directory containing CT DICOM files.
        memmap_file (str): Filename for the memory-mapped file.

    Returns:
        tuple: (memmap, ct_headers, X, Y, pixel_min, pixel_max, wl_default, ww_default)
    """
    dirpath = pathlib.Path(dirpath)

    ct_slice_datasets = []
    for fpath in sorted(dirpath.glob("*.dcm")):
        try:
            ds = pydicom.dcmread(fpath)
            if ds.Modality == "CT":
                ct_slice_datasets.append(ds)
        except pydicom.errors.InvalidDicomError:
            st.warning(
                f"File {fpath.name} is not a valid DICOM file and will be skipped."
            )
        except Exception as e:
            st.warning(f"Error reading {fpath.name}: {e}. This file will be skipped.")

    if not ct_slice_datasets:
        raise ValueError("No valid CT slices found in the provided directory.")

    preprocessed_data = preprocess_ct_slice_datasets(ct_slice_datasets)

    _check_only_one_ct_series(preprocessed_data)
    _check_all_slices_aligned(preprocessed_data)

    # Sort slices based on ImagePositionPatient Z-coordinate
    preprocessed_data.sort(key=lambda data: data["ImagePositionPatient"][2])

    num_slices = len(preprocessed_data)
    height = preprocessed_data[0]["Rows"]
    width = preprocessed_data[0]["Columns"]

    memmap_path = dirpath / memmap_file

    if not memmap_path.exists():
        try:
            memmap = np.memmap(
                memmap_path,
                dtype=np.int16,
                mode="w+",
                shape=(num_slices, height, width),
            )
            for i, data in enumerate(preprocessed_data):
                memmap[i, :, :] = (
                    data["PixelArray"] * data["RescaleSlope"] + data["RescaleIntercept"]
                )
            memmap.flush()
            st.info(f"CT volume data saved to {memmap_path}.")
        except Exception as e:
            raise RuntimeError(f"Failed to create memory-mapped file: {e}") from e
    else:
        try:
            memmap = np.memmap(
                memmap_path, dtype=np.int16, mode="r", shape=(num_slices, height, width)
            )
            st.info(f"CT volume data loaded from existing memmap file {memmap_path}.")
        except Exception as e:
            raise RuntimeError(f"Failed to load memory-mapped file: {e}") from e

    first_data = preprocessed_data[0]
    pixel_min = memmap.min()
    pixel_max = memmap.max()

    wl_default = int(first_data.get("WindowCenter", DEFAULT_WINDOW_LEVEL))
    ww_default = int(first_data.get("WindowWidth", DEFAULT_WINDOW_WIDTH))

    try:
        X, Y = compute_patient_coordinates(
            height,
            width,
            first_data["ImagePositionPatient"],
            first_data["ImageOrientationPatient"],
            first_data["PixelSpacing"],
        )
    except Exception as e:
        raise RuntimeError(f"Failed to compute patient coordinates: {e}") from e

    ct_headers = []
    for data in preprocessed_data:
        try:
            ct_headers.append(
                {
                    "ipp": data["ImagePositionPatient"],
                    "iop": data["ImageOrientationPatient"],
                    "spacing": data["PixelSpacing"],
                }
            )
        except Exception as e:
            st.warning(f"Error processing CT header data: {e}")

    return memmap, ct_headers, X, Y, pixel_min, pixel_max, wl_default, ww_default


@st.cache_data(show_spinner=True, persist=True)
def load_rt_structures(fpath):
    """
    Load RT structures and cache based on the file path.

    Args:
        fpath (Path): Path to the RTSTRUCT DICOM file.

    Returns:
        dict: Structures with their contours and display information.
    """
    try:
        ds = pydicom.dcmread(fpath)
    except pydicom.errors.InvalidDicomError as ide:
        raise ValueError("The provided file is not a valid DICOM file.") from ide
    except Exception as e:
        raise ValueError(f"Error reading RTSTRUCT file: {e}") from e

    if ds.Modality != "RTSTRUCT":
        raise ValueError("File is not an RTSTRUCT DICOM file.")

    required_sequences = ["StructureSetROISequence", "ROIContourSequence"]
    for seq in required_sequences:
        if not hasattr(ds, seq):
            raise ValueError(f"RTSTRUCT file is missing the required {seq}.")

    structures = {}
    roi_nums_to_names = {}
    try:
        for roi in ds.StructureSetROISequence:
            roi_num = getattr(roi, "ROINumber", None)
            roi_name = getattr(roi, "ROIName", "Unknown")
            if roi_num is not None:
                roi_nums_to_names[roi_num] = roi_name
            else:
                st.warning("Found ROI without ROINumber. Skipping this ROI.")
    except Exception as e:
        raise ValueError(f"Error processing StructureSetROISequence: {e}") from e

    try:
        for roi_contour in ds.ROIContourSequence:
            if not hasattr(roi_contour, "ContourSequence"):
                st.warning("ROIContourSequence item missing ContourSequence. Skipping.")
                continue
            roi_num = getattr(roi_contour, "ReferencedROINumber", None)
            roi_name = roi_nums_to_names.get(roi_num, "Unknown")

            contours = []
            for contour_seq in roi_contour.ContourSequence:
                contour_data = getattr(contour_seq, "ContourData", None)
                if contour_data is None:
                    st.warning("ContourSequence item missing ContourData. Skipping.")
                    continue
                try:
                    points = np.array(contour_data, dtype=float).reshape(-1, 3)
                    contours.append(points)
                except Exception as e:
                    st.warning(
                        f"Error reshaping ContourData: {e}. Skipping this contour."
                    )

            if contours:
                try:
                    colour = (
                        f"rgb{tuple(np.uint8(c) for c in roi_contour.ROIDisplayColor)}"
                    )
                except AttributeError:
                    st.warning(
                        f"ROIDisplayColor missing for ROI {roi_name}. Defaulting to gray."
                    )
                    colour = "rgb(128, 128, 128)"
                structures[roi_name] = {
                    "Contours": contours,
                    "Colour": colour,
                    "Number": roi_num,
                }
    except Exception as e:
        raise ValueError(f"Error processing ROIContourSequence: {e}") from e

    if not structures:
        st.warning("No valid structures found in RTSTRUCT file.")

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


@st.cache_data(show_spinner=True, persist=True)
def load_rt_dose(fpath, _ct_headers):
    """
    Load RTDOSE data and map it to CT slices based on Z-coordinate.

    Args:
        fpath (Path): Path to the RTDOSE DICOM file.
        _ct_headers (list): List of CT slice headers with 'ipp'.

    Returns:
        tuple: (dose_map, dose_units, dose_X, dose_Y)
            dose_map (dict): Mapping of slice index to dose_array.
            dose_units (str): Units of the dose ('GY' or 'CGY').
            dose_X (dict): Mapping of slice index to X coordinates arrays.
            dose_Y (dict): Mapping of slice index to Y coordinates arrays.
    """
    try:
        ds = pydicom.dcmread(fpath)
    except pydicom.errors.InvalidDicomError as ide:
        raise ValueError("The provided RTDOSE file is not a valid DICOM file.") from ide
    except Exception as e:
        raise ValueError(f"Error reading RTDOSE file: {e}") from e

    if ds.Modality != "RTDOSE":
        raise ValueError("File is not an RTDOSE DICOM file.")

    dose_grid_scaling = getattr(ds, "DoseGridScaling", None)
    if dose_grid_scaling is None:
        st.warning("DoseGridScaling missing. Assuming a scaling factor of 1.0.")
        dose_grid_scaling = 1.0

    dose_units = getattr(ds, "DoseUnits", "UNKNOWN")  # Usually 'GY' or 'CGY'

    try:
        dose_data = (
            ds.pixel_array * dose_grid_scaling
        )  # Convert to physical dose values
    except Exception as e:
        raise ValueError(f"Error processing dose pixel data: {e}") from e

    # Extract dose grid information
    grid_frame_offset_vector = getattr(
        ds, "GridFrameOffsetVector", None
    )  # Z-offsets for each dose slice
    if grid_frame_offset_vector is None:
        st.warning(
            "GridFrameOffsetVector missing. Assuming single dose slice at origin."
        )
        grid_frame_offset_vector = [0.0]

    dose_origin = getattr(ds, "ImagePositionPatient", None)
    if dose_origin is None:
        raise ValueError("Dose ImagePositionPatient missing.")

    dose_origin = np.array(dose_origin, dtype=float)

    # Compute dose slice positions based on grid_frame_offset_vector
    try:
        dose_z_positions = dose_origin[2] + np.array(
            grid_frame_offset_vector, dtype=float
        )
    except Exception as e:
        raise ValueError(f"Error computing dose slice positions: {e}") from e

    slice_z_positions = [header["ipp"][2] for header in _ct_headers]

    dose_map = {}  # slice_idx: dose_array
    dose_X = {}  # slice_idx: X coordinates array
    dose_Y = {}  # slice_idx: Y coordinates array

    for idx, dose_z in enumerate(dose_z_positions):
        # Find the closest CT slice based on Z-coordinate
        try:
            closest_slice_idx = np.argmin(np.abs(np.array(slice_z_positions) - dose_z))
        except Exception as e:
            st.warning(
                f"Error finding closest CT slice for dose slice {idx + 1}: {e}. Skipping."
            )
            continue

        # Check if this dose_z closely matches the CT slice's z-coordinate (within tolerance)
        z_tolerance = 1e-3  # in mm
        if np.abs(slice_z_positions[closest_slice_idx] - dose_z) > z_tolerance:
            st.warning(
                f"Dose slice {idx + 1} at dose_z={dose_z} mm does not closely match any CT slice Z-coordinate. Skipping."
            )
            continue

        # Store dose data without resampling
        if closest_slice_idx not in dose_map:
            dose_map[closest_slice_idx] = dose_data[idx]
        else:
            # If multiple dose slices map to the same CT slice, average them
            dose_map[closest_slice_idx] = (
                dose_map[closest_slice_idx] + dose_data[idx]
            ) / 2

        # Calculate spatial coordinates for the dose slice
        dose_iop = getattr(ds, "ImageOrientationPatient", None)
        dose_pixel_spacing = getattr(ds, "PixelSpacing", None)
        if dose_iop is None or dose_pixel_spacing is None:
            st.warning(
                f"Missing ImageOrientationPatient or PixelSpacing for dose slice {idx + 1}. Cannot compute spatial coordinates."
            )
            continue

        try:
            dose_X_slice, dose_Y_slice = compute_patient_coordinates(
                ds.Rows,
                ds.Columns,
                tuple(ds.ImagePositionPatient),
                tuple(ds.ImageOrientationPatient),
                tuple(ds.PixelSpacing),
            )
        except Exception as e:
            st.warning(
                f"Failed to compute spatial coordinates for dose slice {idx + 1}: {e}. Skipping."
            )
            continue

        dose_X[closest_slice_idx] = dose_X_slice
        dose_Y[closest_slice_idx] = dose_Y_slice

    if not dose_map:
        st.warning("No valid dose slices were mapped to CT slices.")

    return dose_map, dose_units, dose_X, dose_Y


def window_image(img, ww, wl):
    """Apply window level and window width to the image."""
    img_min = wl - (ww / 2)
    img_max = wl + (ww / 2)
    return np.clip(img, img_min, img_max)


def create_structure_legend(structures):
    """Creates an HTML legend for the structures with their corresponding colors."""
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
    ct_image, ct_headers, X, Y, initial_slice_idx, wl_default, ww_default
):
    """Initialize and cache the base figure for the CT viewer."""
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
    dose_map,
    show_dose,
    dose_units,
    dose_X,
    dose_Y,
):
    """Update the existing figure with new data based on user inputs."""
    try:
        slice_image = ct_image[slice_idx, :, :]
        windowed_img = window_image(slice_image, ww, wl)
        img_min = wl - (ww / 2)
        img_max = wl + (ww / 2)
    except IndexError:
        st.error(f"Slice index {slice_idx} is out of bounds.")
        return fig
    except Exception as e:
        st.error(f"Error processing slice {slice_idx}: {e}")
        return fig

    # Update heatmap trace (CT image)
    try:
        fig.data[0].z = windowed_img
        fig.data[0].zmin = img_min
        fig.data[0].zmax = img_max
    except IndexError:
        st.error("CT image heatmap trace is missing.")
        return fig
    except Exception as e:
        st.error(f"Error updating heatmap: {e}")
        return fig

    # Update the title
    try:
        slice_z = ct_headers[slice_idx]["ipp"][2]
        fig.update_layout(title=f"Z = {slice_z:.2f} mm (Slice {slice_idx})")
    except IndexError:
        st.error(f"Slice header for index {slice_idx} is missing.")
    except Exception as e:
        st.error(f"Error updating title: {e}")

    # Remove existing contour and dose overlay traces
    try:
        fig.data = tuple(
            trace
            for trace in fig.data
            if not (
                (isinstance(trace, go.Scatter) and trace.name in structures.keys())
                or (isinstance(trace, go.Heatmap) and trace.name == "Dose Overlay")
            )
        )
    except Exception as e:
        st.error(f"Error removing old traces: {e}")

    # Add new contour traces for the selected structures
    try:
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
    except Exception as e:
        st.error(f"Error adding contour traces: {e}")

    # Add RTDOSE overlay if enabled
    if show_dose and slice_idx in dose_map:
        try:
            dose_slice = dose_map[slice_idx]
            dose_X_slice = dose_X.get(slice_idx)
            dose_Y_slice = dose_Y.get(slice_idx)

            if dose_X_slice is not None and dose_Y_slice is not None:
                # Normalize dose for colorscale
                dose_min = dose_slice.min()
                dose_max = dose_slice.max()
                normalized_dose = (
                    (dose_slice - dose_min) / (dose_max - dose_min)
                    if dose_max > dose_min
                    else dose_slice
                )

                # Create a semi-transparent colorwash using Heatmap
                dose_heatmap = go.Heatmap(
                    z=normalized_dose,
                    colorscale="Jet",
                    opacity=0.5,
                    showscale=False,
                    x0=dose_X_slice[0, 0],
                    dx=dose_X_slice[0, 1] - dose_X_slice[0, 0],
                    y0=dose_Y_slice[0, 0],
                    dy=dose_Y_slice[1, 0] - dose_Y_slice[0, 0],
                    hovertemplate=f"Dose: %{{z:.2f}} {dose_units}<extra></extra>",
                    name="Dose Overlay",
                )
                fig.add_trace(dose_heatmap)
            else:
                st.warning(
                    f"No spatial coordinates found for dose slice at index {slice_idx}. "
                    "Cannot overlay dose data."
                )
        except Exception as e:
            st.error(f"Error adding RTDOSE overlay: {e}")

    return fig


# Sidebar to upload DICOM directory, RTSTRUCT file, and RTDOSE file
st.sidebar.header("Input Files")

dicom_dir = st.sidebar.text_input("Enter DICOM directory path")
rtstruct_file = st.sidebar.text_input("Enter RTSTRUCT file path")
rtdose_file = st.sidebar.text_input("Enter RTDOSE file path (optional)")

# Checkbox to toggle RTDOSE colorwash
show_dose = False
if rtdose_file:
    show_dose = st.sidebar.checkbox("Show Dose Colorwash", value=False)

if dicom_dir and rtstruct_file:
    if pathlib.Path(dicom_dir).exists():
        if pathlib.Path(rtstruct_file).exists():
            try:
                (
                    ct_image,
                    ct_headers,
                    X,
                    Y,
                    pixel_min,
                    pixel_max,
                    wl_default,
                    ww_default,
                ) = load_ct_as_memmap(pathlib.Path(dicom_dir))
                structures = load_rt_structures(pathlib.Path(rtstruct_file))
                contour_map = preprocess_contours(structures)
                st.sidebar.success("CT and RTSTRUCT files loaded successfully.")
            except Exception as e:
                st.error(f"Error loading CT or RTSTRUCT data: {e}")
                st.stop()
        else:
            st.error("RTSTRUCT file path does not exist.")
            st.stop()
    else:
        st.error("DICOM directory path does not exist.")
        st.stop()
else:
    st.info("Please enter both DICOM directory and RTSTRUCT file paths.")
    st.stop()

# Extract Z-coordinates from CT headers
z_coords = [header["ipp"][2] for header in ct_headers]

# Load RTDOSE if provided and path exists
dose_map = {}
dose_units = ""
dose_X = {}
dose_Y = {}
if rtdose_file:
    if pathlib.Path(rtdose_file).exists():
        try:
            dose_map, dose_units, dose_X, dose_Y = load_rt_dose(
                pathlib.Path(rtdose_file), _ct_headers=ct_headers
            )
            st.sidebar.success("RTDOSE loaded successfully.")
        except Exception as e:
            st.sidebar.error(f"Error loading RTDOSE: {e}")
            dose_map = {}
            dose_units = ""
            dose_X = {}
            dose_Y = {}
    else:
        st.sidebar.error("Invalid RTDOSE file path.")

num_slices, height, width = ct_image.shape

# Sidebar controls for dynamic updates
with st.sidebar:
    st.header("Controls")

    # Slider to select slice index
    slice_idx = st.slider(
        "Slice Index",
        min_value=0,
        max_value=num_slices - 1,
        value=st.session_state.get("slice_idx", num_slices // 2),
        step=1,
        key="slice_slider",
    )

    # Display Z-coordinate based on selected slice
    try:
        st.write(f"**Z-Coordinate:** {z_coords[slice_idx]:.2f} mm (Slice {slice_idx})")
    except IndexError:
        st.error(f"Slice index {slice_idx} is out of bounds.")
    except Exception as e:
        st.error(f"Error displaying Z-coordinate: {e}")

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
    try:
        initial_slice_idx = num_slices // 2
        st.session_state.base_figure = initialize_base_figure(
            ct_image,
            ct_headers,
            X,
            Y,
            initial_slice_idx,
            wl_default,
            ww_default,
        )
    except Exception as e:
        st.error(f"Error initializing base figure: {e}")
        st.stop()

# Update the figure based on user inputs, including selected structures and dose
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
    dose_map,
    show_dose,
    dose_units,
    dose_X,
    dose_Y,
)

# Display the updated figure
st.plotly_chart(updated_fig, use_container_width=True, height=800)
